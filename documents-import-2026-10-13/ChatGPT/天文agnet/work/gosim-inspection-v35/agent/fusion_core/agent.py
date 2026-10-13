#!/usr/bin/env python3
"""Agent Observer v4 reference agent ("pro"). Standard library only, participant-agent-protocol-v4.

One JSON object per line on stdin, one per line on stdout, logs on stderr.

What it does (details in README.md and planner.py):

1. Planning: every decision picks pointing, fibre assignment, duration and program together, maximising
   expected gain minus a price for telescope time (gain - lambda * T). Required targets and observation
   requests enter as probability-weighted bonuses.
2. Program: the band level is fitted to saturated hits, which show the program multiplier exactly.
3. Instrument faults: E = (quality level) / (band level). Weather moves both, a fault only the first;
   when E stays low the agent reports. Free false reports are spent early; each low episode is probed
   once; paid probes need two low nights.
4. Pace: the search level adapts to the measured cost per decision so a 4-month card fits the wall clock.
5. Model (advisor.py): at every night start a night plan (forecast + bulletin -> bad night, sectors to avoid)
   and a fault review (own quality table -> how likely a fault is, which gates paid reports); before a paid
   report the model confirms or vetoes. Calls run in the background; without an API key the agent exits,
   except when the platform sets OBSERVER_MODEL_DISABLED=1 (an evaluation without a model): then rules only.
"""
from __future__ import annotations

import bisect
import json
import os
import sys
import time
from budget import AgentClock, near_wall_cap
from log_review import ObservationReview
from inspection import Inspection
from datetime import timedelta

from advisor import Advisor
from .fault import FaultDetector
from llm_client import LLMClient, api_key, load_dotenv
from .planner import MONITOR_T
from .guarded import Planner
from .skymath import format_utc, parse_utc

WEATHER_KINDS = {"rain", "storm", "overcast", "haze", "cold_snap"}
BAD_KINDS = {"rain", "storm", "overcast", "haze"}
PROTOCOL = "participant-agent-protocol-v4"


def _env(name: str, default: float) -> float:
    return type(default)(os.environ.get(f"V5_{name}", os.environ.get(f"PRO_{name}", default)))


# --- fault reporting: fault.py (step detector on the per-exposure efficiency signal) ---
MODEL_FAULT_LOW = _env("MODEL_FAULT_LOW", 0.15)   # fault review at or below this: no paid report tonight
# --- pace ---
PACE_SAFETY = _env("PACE_SAFETY", 0.9)      # spend at most this share of the CPU left after the reserve
PACE_RESERVE = _env("PACE_RESERVE", 0.04)   # share of the whole CPU budget kept back to the very end
PACE_RATE_MARGIN = _env("PACE_RATE_MARGIN", 1.15)   # future observe decisions = this x the measured rate so far
PACE_WINDOW_H = _env("PACE_WINDOW_H", 0.0)   # measure that rate over the last this many night hours (0 = whole season):
                                             # exposures get longer through a season, so the season rate overstates
# --- model ---
MODEL_WAIT_MAX = _env("MODEL_WAIT_MAX", 20.0)   # longest wait for the night's model answers (s)
DEEP = _env("DEEP", 1)                     # the wider level-0 search when the CPU budget allows it
DEEP_COST = _env("DEEP_COST", 1.8)          # its cost before it is measured: this x level 0
DEEP_HYST = _env("DEEP_HYST", 1.2)          # deep search stays on while its cost is below this x the budget
FIXED_LEVEL = _env("FIXED_LEVEL", -1)     # development only: pin the search level (deterministic runs)
NO_REPORT = _env("NO_REPORT", 0)          # development only: never report (collects the uncorrected fault signal)
MONITOR_GAP = _env("MONITOR_GAP", 0.75)   # hours without an exposure before a monitoring one (0 = never)



def log(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


class RulesOnly:
    """The advisor's interface without a model (OBSERVER_MODEL_DISABLED=1): every rule default stands."""
    night_date = None

    def start_night(self, night_date, *_args):
        self.night_date = night_date
        return None, None

    def poll(self):
        return None, None

    def confirm_report(self, *_args):
        return None


def model_disabled() -> bool:
    """The platform sets OBSERVER_MODEL_DISABLED=1 for an evaluation started with 「本次不提供模型」 / --no-model."""
    return os.environ.get("OBSERVER_MODEL_DISABLED") == "1"


class ObserverAgent:
    def __init__(self, init: dict, rules_only: bool = False):
        started = time.monotonic()
        self.planner = Planner(init, log=log)
        self.clock = AgentClock(init)
        self.max_breadth=max(1.,min(3.,float(os.environ.get("FUSION_MAX_BREADTH","1"))))
        self.log_review = ObservationReview(self.planner) if os.environ.get("FUSION_LOG_REVIEW","1")=="1" else None
        self.planner.log_review = self.log_review
        self.inspection = Inspection(self.planner)
        if self.log_review:self.log_review.inspection = self.inspection
        self.preference_until = 0
        self.rules_only = rules_only
        self.client = None if rules_only else LLMClient(log=log)
        self.advisor = RulesOnly() if rules_only else Advisor(self.client, log=log)
        self.model_wait = 0.0                    # wall seconds spent waiting for the model (not planning cost)
        self.fault_likely = None                 # tonight's model estimate that an instrument fault is active
        self.start = parse_utc(init["survey"]["start_utc"])
        self.forecast_notices: list = []
        self.night_seen = None
        self.observes = 0
        self.monitors = 0
        self.last_exposure_hours = -1e9          # when the last observe (planned or monitoring) was sent
        self.monitor_turn = False
        # fault reporting state
        reporting = init["scoring"].get("reporting", {})
        self.free_allowance = int(reporting.get("false_report_free_allowance", 0))
        self.detector = FaultDetector(self.free_allowance, log=log)
        self.reports = 0
        self.correct_reports = 0
        self.r_hours: dict = {}                  # hour -> [exposure fault signal r] (for the model's fault table)
        self.b_hours: dict = {}                  # hour -> [lowest upper, highest lower efficiency bound] (bandfit)
        self.ref_from_hours = -1e9
        self.quake_onset_hours = -1e9
        self.quake_on = False
        # pace state
        self.cost_ema = [0.0, 0.0, 0.0, 0.0]     # CPU seconds per observe decision at each search level
        self.wall_ema = [0.0, 0.0, 0.0, 0.0]     # real seconds per observe decision (own turn, model waits excluded)
        self.deep_ema = [0.0, 0.0]               # CPU and real seconds per observe decision of the deep search
        self.turn_end = None
        self.decisions = 0
        self.engine_ema = None
        self.sim_step_ema = None
        self.last_now = None
        self.other_cpu = 0.0                     # CPU spent in turns that were not observe decisions
        self.other_wall = 0.0                    # ... and their real time
        self.rate_marks: list = []               # (night seconds elapsed, observes so far) every few night hours
        self.turns = 0
        self.cpu_total = None                    # CPU budget at the start (this machine's seconds)
        self.night_total = sum((end - start).total_seconds() for start, end in self.planner.nights)
        log(f"v5: {len(self.planner.ids)} targets, {sum(self.planner.required)} required, "
            f"{len(self.planner.nights)} nights; init {time.monotonic() - started:.2f}s; model {self.client.model if self.client else 'none (rules only)'}")

    # --- decision loop ------------------------------------------------------------------------------

    def respond(self, payload: dict) -> dict:
        started = time.monotonic()
        cpu_started = time.process_time()
        if self.turn_end is not None:   # engine time between our turns (charged only by the old real-time clock)
            gap = started - self.turn_end
            if 0.0 <= gap < 5.0:
                self.engine_ema = gap if self.engine_ema is None else 0.95 * self.engine_ema + 0.05 * gap
        model_before = self.model_wait
        level = self.planner.fast_level
        deep = self.planner.deep and level == 0
        self.monitor_turn = False
        action = self._respond(payload)
        level = self.planner.fast_level
        deep = self.planner.deep and level == 0
        # the platform charges CPU time inside our turns; waiting for the model is free of CPU, so keep it
        # out of the real-time estimate as well
        cpu = time.process_time() - cpu_started
        self.clock.account(cpu)
        wall = time.monotonic() - started - (self.model_wait - model_before)
        self.turns += 1
        if action.get("action") != "observe" or self.monitor_turn:   # a monitoring exposure costs no search
            self.other_cpu += cpu
            self.other_wall += wall
        elif deep:
            for k, cost in enumerate((cpu, wall)):
                cost /= max(1.,self.planner.search_scale)
                c = self.deep_ema[k]
                self.deep_ema[k] = cost if c == 0.0 else 0.9 * c + 0.1 * cost
        elif level < 4:
            for ema, cost in ((self.cost_ema, cpu), (self.wall_ema, wall)):
                c = ema[level]
                ema[level] = cost if c == 0.0 else 0.9 * c + 0.1 * cost
                for k in range(level + 1, 4):   # cheaper levels not measured yet: a third of the level above
                    if ema[k] == 0.0 or ema[k] > ema[k - 1]:
                        ema[k] = ema[k - 1] / 3.0
        self.turn_end = time.monotonic()
        return action

    def _respond(self, payload: dict) -> dict:
        now = parse_utc(payload["now_utc"])
        if self.last_now is not None and self.planner.current_night(now) is not None:
            step = (now - self.last_now).total_seconds()
            if 0 < step <= 3600:
                self.sim_step_ema = step if self.sim_step_ema is None else 0.95 * self.sim_step_ema + 0.05 * step
        self.last_now = now
        hours = (now - self.start).total_seconds() / 3600.0
        planner = self.planner
        for message in payload.get("new_messages", []):
            if message.get("record_type") == "forecast":
                self.forecast_notices = message.get("notices", [])
        last = payload.get("last_result") or {}
        if last.get("action") == "report":
            self._on_report_result(last, hours)
        # A weather notice received at the end can explain contamination during the exposure.
        from .planner import DIRECTION_AZ, _az_distance
        for message in payload.get("new_messages",[]):
            if message.get("record_type")!="bulletin":continue
            for notice in message.get("notices",[]):
                if notice.get("event_kind") not in WEATHER_KINDS | {"rocket_launch","terrain_obstruction"}:continue
                direction=notice.get("direction")
                if (notice.get("event_kind"),direction) in planner.pending_notices:continue
                for prediction in planner.pending.values():
                    if direction=="ALL" or (direction in DIRECTION_AZ and
                        _az_distance(prediction["az"],DIRECTION_AZ[direction])<=75.):
                        prediction["dir_clean"]=False;prediction["clean"]=False
        # Process the in-flight exposure before loss messages invalidate its action index.
        result=self.inspection.gate(payload.get("last_result"))
        notices={(n.get("event_kind",""),n.get("direction",""))
            for n in (payload.get("latest_bulletin") or {}).get("notices",[])}
        if result and result.get("action")=="observe" and planner.pending:
            self.inspection.record(result,now,sorted(set(getattr(planner,'pending_notices',()))|notices))
        if self.log_review:self.log_review.record(result,now,notices)
        pending=planner.pending
        planner.on_result(result, now, hours)
        if result is None and payload.get("last_result"):
            planner.pending=pending  # rejected/duplicate feedback cannot consume a new plan
        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))
        if any(m.get("record_type")=="state_resync" for m in payload.get("new_messages", [])):
            self.detector.reset(hours,"state resync")
            self.detector.brows.clear()
            self.r_hours.clear();self.b_hours.clear()
            self.ref_from_hours=hours
            self.fault_likely=None
        quake = any(kind == "earthquake" for kind, _ in planner.notices)
        if quake and not self.quake_on:
            self.quake_onset_hours = hours
            log(f"v5: earthquake notice at {payload['now_utc']}")
        self.quake_on = quake
        planner.on_requests(payload.get("active_requests", []), now)
        bounds = planner.exposure_bounds
        if planner.exposure_closed and planner.exposure_meta is not None:
            self.detector.closed(hours - planner.exposure_meta[2] / 3600.0, hours, planner.exposure_meta[0])
        if (planner.exposure_r is not None or bounds is not None) and planner.exposure_meta is not None:
            night_index, notices, duration = planner.exposure_meta
            mid = hours - 0.5 * duration / 3600.0
            self.detector.add_exposure(mid, night_index, planner.exposure_r, notices, bounds, planner.notices)
            if planner.exposure_r is not None:
                self.r_hours.setdefault(int(mid), []).append(planner.exposure_r)
            if bounds is not None:
                cell = self.b_hours.setdefault(int(mid), [9.9, 0.0])
                cell[0], cell[1] = min(cell[0], bounds[1]), max(cell[1], bounds[0])
        else:
            self.detector.add_exposure(hours, None, None, planner.notices)
        checkpoint=False
        self.inspection.resync(payload.get("new_messages",[]))
        if self.log_review:
            changed=self.log_review.invalidate(payload.get("new_messages",[]))
            checkpoint=self.log_review.checkpoint(now,force=changed)
            if checkpoint:log("exposure review: "+json.dumps(self.log_review.summary(),separators=(",",":")))
        self._pace(payload, now)
        if not self.rules_only:
            self.advisor.ingest(payload,planner)
            if getattr(self,"fault_review_version",None)!=self.advisor.ledger_version:
                self.fault_likely=None
        if now.timestamp()>self.preference_until:
            
            if planner.operator_priorities:planner.vcache=None
            planner.operator_priorities=set();planner.extra_avoid=set()

        night = planner.current_night(now)
        if night is None:
            nxt = planner.next_night_start(now)
            if nxt is None:
                return {"action": "finish", "reason": "no observing night left"}
            return {"action": "wait", "until_utc": format_utc(nxt), "reason": "daytime: sleep until the next night"}
        night_index, night_start, night_end = night
        if self.night_seen != night_index:
            self.night_seen = night_index
            self._night_advice(night_start, payload, hours)
        else:
            self._apply_advice(*self.advisor.poll())
            if not self.rules_only:
                signature=(tuple(str(x) for x in self.advisor.texts),int(hours), checkpoint)
                if signature!=getattr(self,"_advice_signature",None):
                    self._advice_signature=signature
                    self._night_advice(night_start,payload,hours)
        if (night_end - now).total_seconds() < planner.min_exposure:
            nxt = planner.next_night_start(now)
            if nxt is None:
                return {"action": "finish", "reason": "survey over"}
            return {"action": "wait", "until_utc": format_utc(nxt), "reason": "night ending"}
        if planner.site_closed():
            return {"action": "wait", "duration_seconds": self._to_next_slot(now, night_start),
                    "reason": "bulletin: rain/storm over the whole sky"}
        report = self._maybe_report(hours, payload)
        if report is not None:
            return report
        action = planner.plan(now, night_end, night_index, hours)
        if action is None:
            wait = self._to_next_slot(now, night_start)
            if planner.next_up is not None:
                wait = max(60, min(wait, int(planner.next_up)))
            if (MONITOR_GAP > 0 and hours - self.last_exposure_hours >= MONITOR_GAP and planner.fast_level <= 1
                    and wait > MONITOR_T + 120 and not planner.all_sky_weather()):
                action = planner.monitor(now, night_end, night_index, hours)
                if action is not None:
                    self.monitor_turn = True
                    self.monitors += 1
                    self.last_exposure_hours = hours
                    action["reason"] = f"monitoring the instrument: {len(action['assignments'])} fibres, nothing has value up"
                    return action
            return {"action": "wait", "duration_seconds": wait, "reason": "nothing useful is up"}
        self.observes += 1
        self.last_exposure_hours = hours
        action["reason"] = f"{len(action['assignments'])} fibres, program {action['program']}"
        return action

    def _to_next_slot(self, now, night_start) -> int:
        slot = self.planner.slot_seconds
        into = (now - night_start).total_seconds() % slot
        return int(max(60, min(3600, slot - into)))

    # --- pace ---------------------------------------------------------------------------------------

    def _clock(self, payload: dict):
        """(CPU seconds left, real seconds left, fair clock?) from the request's wallclock block.

        Fair clock (current platform): the budget is normalized CPU time inside our turns, and
        remaining_real_cpu_seconds converts it to this machine's CPU seconds; a separate real-time cap
        (wall_remaining_seconds) only guards against runaway runs. Older runners count real time only."""
        return self.clock.read(payload)

    def _night_left(self, now) -> float:
        return sum(max(0.0, (end - max(start, now)).total_seconds()) for start, end in self.planner.nights if end > now)

    def _decisions_left(self, now) -> float:
        """Observe decisions still to come. Upper bound: one per simulator step of night time. Once a few nights
        are behind us, the measured observe rate per night-second (x a margin) replaces it: waits under bad
        weather and long exposures make the real count much smaller than the bound."""
        night_left = self._night_left(now)
        bound = max(1.0, night_left / (self.sim_step_ema or 900.0))
        elapsed = self.night_total - night_left
        if elapsed < 3 * 8 * 3600.0 or self.observes < 30:
            return bound
        measured = PACE_RATE_MARGIN * night_left * self.observes / elapsed
        if PACE_WINDOW_H > 0:
            marks = self.rate_marks
            if not marks or elapsed - marks[-1][0] >= 4 * 3600.0:
                marks.append((elapsed, self.observes))
            k = bisect.bisect_right(marks, (elapsed - PACE_WINDOW_H * 3600.0, float("inf"))) - 1
            since, count = marks[max(0, k)]
            if elapsed - since >= 24 * 3600.0:
                measured = PACE_RATE_MARGIN * night_left * (self.observes - count) / (elapsed - since)
        return max(1.0, min(bound, max(measured, 0.2 * bound)))

    def _pace(self, payload: dict, now) -> None:
        """Pick the search level from the measured cost per decision and the decisions still to come."""
        cpu_left, wall_left, fair = self._clock(payload)
        if self.cpu_total is None:
            self.cpu_total = cpu_left
        decisions_left = self._decisions_left(now)
        engine = self.engine_ema or 0.0
        # CPU the turns that are not observe decisions will still take (measured per night-second so far)
        night_left = self._night_left(now)
        elapsed = max(3600.0, self.night_total - night_left)
        other = 1.2 * self.other_cpu * night_left / elapsed
        spendable = cpu_left - PACE_RESERVE * self.cpu_total - other
        cpu_budget = PACE_SAFETY * max(0.0, spendable) / decisions_left if fair else 1e9
        # real time: the other turns, and the engine's time on every turn (several turns per observe decision)
        other_wall = 1.2 * self.other_wall * night_left / elapsed
        turns_per_decision = max(1.0, self.turns / self.observes) if self.observes >= 30 else 1.5
        wall_budget = PACE_SAFETY * max(0.0, wall_left - other_wall) / decisions_left - engine * turns_per_decision
        # estimates of levels not used for a while decay, so the agent climbs back up and re-measures them
        self.decisions += 1
        if self.decisions % 50 == 0:
            for k in range(4):
                if k != self.planner.fast_level:
                    self.cost_ema[k] *= 0.85
                    self.wall_ema[k] *= 0.85
            if not self.planner.deep:
                self.deep_ema = [0.85 * c for c in self.deep_ema]
        if FIXED_LEVEL >= 0:
            self.planner.fast_level = FIXED_LEVEL
            self.planner.deep = bool(DEEP) and FIXED_LEVEL == 0
            return
        level = 0
        while level < 3 and (self.cost_ema[level] > cpu_budget or (not fair and self.wall_ema[level] > wall_budget)):
            level += 1
        if cpu_left < 15.0 or near_wall_cap(wall_left):
            level = 4
        # spare budget at level 0: search wider (its cost before measuring: DEEP_COST x level 0); once on, it
        # stays on up to DEEP_HYST x the budget, so a cost near the budget does not flip it every few decisions
        deep_cpu = self.deep_ema[0] or DEEP_COST * self.cost_ema[0]
        deep_wall = self.deep_ema[1] or DEEP_COST * self.wall_ema[0]
        slack = DEEP_HYST if self.planner.deep else 1.0
        deep = (bool(DEEP) and level == 0 and self.cost_ema[0] > 0.0 and deep_cpu <= slack * cpu_budget
                and (not near_wall_cap(wall_left,deep_wall) if fair else deep_wall <= wall_budget))
        self.planner.cpu_turn_budget=max(.003,min(.02*cpu_left,cpu_budget)) if fair else max(.003,wall_budget)
        self.planner.search_scale=min(self.max_breadth,max(1.,.65*cpu_budget/max(deep_cpu,.02))) if deep and fair else 1.
        if deep != self.planner.deep:
            log(f"v5: deep search {'on' if deep else 'off'} (cpu budget {min(cpu_budget, 99) * 1000:.0f} ms, deep cost {deep_cpu * 1000:.0f} ms)")
            self.planner.deep = deep
        if level != self.planner.fast_level:
            log(f"v5: pace level {level} (cpu budget {min(cpu_budget, 99) * 1000:.0f} ms, wall budget {wall_budget * 1000:.0f} ms, "
                f"cpu costs {[round(c * 1000) for c in self.cost_ema]} ms, {decisions_left:.0f} decisions left)")
            self.planner.fast_level = level

    # --- model stages (advisor.py): night plan and fault review at every night start --------------------

    def _night_advice(self, night_start, payload: dict, hours: float) -> None:
        """Night start: rule defaults first, then the two model calls (night plan, fault review)."""
        night_date = (night_start - timedelta(hours=12)).date().isoformat()
        tonight = [n for n in self.forecast_notices if night_date in n.get("nights", [])]
        bulletin = (payload.get("latest_bulletin") or {}).get("notices", [])
        # rule defaults, kept when the model gives no valid answer
        self.planner.bad_forecast = any(n.get("direction") == "ALL" and n.get("event_kind") in BAD_KINDS for n in tonight)
        self.planner.extra_avoid = set()
        self.fault_likely = None
        left = self._clock(payload)[1]
        started = time.monotonic()
        answers = self.advisor.start_night(night_date, tonight, bulletin, self._fault_table(hours), left,
                                           self._model_wait_budget(payload))
        self.model_wait += time.monotonic() - started
        self._apply_advice(*answers)

    def _model_wait_budget(self, payload: dict) -> float:
        """How long a night start may wait for the model. Waiting costs no CPU budget, only real time: use half
        of the real time the planner and the engine will not need, spread over the nights left."""
        _,wall_left,_=self._clock(payload)
        # Waiting for a model consumes the separate protection deadline, not CPU.
        reserve=max(30.,2.*max(self.wall_ema))
        return max(0.,min(12.,wall_left-reserve))

    def _apply_advice(self, plan, fault) -> None:
        if plan is not None:
            self.planner.bad_forecast = plan["bad_night"]
            self.planner.extra_avoid = set(plan["avoid_directions"])
            ids = set(plan.get('prioritize_target_ids', []))
            for rid in plan.get('prioritize_request_ids', []):
                ids.update(self.advisor.active_requests[rid]['target_ids'])
            self.planner.operator_priorities = {self.planner.index_of[t] for t in ids}
            classes = set(plan.get('prioritize_classes', []))
            self.planner.operator_priorities.update(i for i,c in enumerate(self.planner.target_classes) if c in classes)
            self.planner.vcache = None
            self.preference_until = plan.get('valid_until', 0)
            log(f"llm night plan {self.advisor.night_date}: bad_night={plan['bad_night']} avoid={plan['avoid_directions']} ({plan['reason']})")
        if fault is not None:
            self.fault_likely = fault["fault_likely"]
            self.fault_review_version = self.advisor.ledger_version
            log(f"llm fault review {self.advisor.night_date}: fault_likely={fault['fault_likely']:.2f} ({fault['reason']})")

    def _fault_table(self, hours: float) -> dict:
        """The evidence the fault review reads: hourly medians of r over the last ~30 observed hours, with the
        model-dependent efficiency bounds of each hour (lowest upper / highest lower bound, bandfit.py)."""
        rows = []
        for hour in sorted(h for h in set(self.r_hours) | set(self.b_hours) if h >= self.ref_from_hours)[-30:]:
            v = sorted(self.r_hours.get(hour, []))
            b = self.b_hours.get(hour)
            stamp = (self.start + timedelta(hours=hour)).strftime("%m-%dT%H")
            rows.append([stamp, round(v[len(v) // 2], 3) if v else None, len(v),
                         round(b[0], 2) if b and b[0] < 9 else None, round(b[1], 2) if b and b[1] > 0 else None])
        notices = sorted({f"{kind} {direction}" for kind, direction in self.planner.notices})
        det = self.detector
        return {"log_review":self.log_review.summary() if self.log_review else {}, "columns": ["utc_hour", "r", "exposures", "eff_upper_bound", "eff_lower_bound"], "rows": rows,
                "rule_evidence": det.last_evidence or None, "bound_assumptions": "shared weather and accurate sky model; never certify raw completion", "notices_now": notices,
                "hours_since_earthquake_notice_began": None if self.quake_onset_hours < -1e8 else round(hours - self.quake_onset_hours, 1),
                "free_false_reports_left": det.free_left(), "paid_false_reports_so_far": det.paid_false,
                "correct_reports_so_far": det.correct,
                "hours_since_last_report": None if self.reports == 0 else round(hours - det.last_report, 1)}

    # --- instrument faults ---------------------------------------------------------------------------

    def _maybe_report(self, hours: float, payload: dict):
        """Report (probe) when the detector sees a lasting step in the efficiency signal (fault.py).

        A report costs no time, its answer arrives at once, and the first false reports after each correct
        one are free: free probes on a clear step, paid ones only on a deep, long step the model does not veto."""
        det = self.detector
        if NO_REPORT:
            return None

            return None
        likely = self.fault_likely
        allow_paid = not (likely is not None and likely <= MODEL_FAULT_LOW)
        if not det.should_report(hours, self.planner.notices, allow_paid=allow_paid):
            return None
        if not self._model_agrees(hours, payload):
            det.veto(hours)
            return None
        self.reports += 1
        log(f"v5: report at {payload['now_utc']} ({det.last_evidence}), free left {det.free_left()}")
        return {"action": "report", "reason": det.last_evidence[:120]}

    def _model_agrees(self, hours: float, payload: dict) -> bool:
        """Paid probes only: the model looks at the evidence first and may veto. Free probes cost nothing, so they
        never wait for it. No answer in time: the rule's decision stands."""
        if self.detector.free_left() > 0:
            return True
        evidence = {"fault_table": self._fault_table(hours), "rule_evidence": self.detector.last_evidence,
                    "paid_false_reports_so_far": self.detector.paid_false, "correct_reports_so_far": self.detector.correct}
        started = time.monotonic()
        left = self._clock(payload)[1]
        verdict = self.advisor.confirm_report(evidence, left, min(30.0, 2.0 * self._model_wait_budget(payload)))
        self.model_wait += time.monotonic() - started
        if verdict is False:
            log(f"v5: model vetoed a paid report at {payload['now_utc']}")
            return False
        return True

    def _on_report_result(self, result: dict, hours: float) -> None:
        correct = bool(result.get("correct"))
        self.detector.on_report_result(hours, correct)
        if correct:
            if self.log_review:self.log_review.repaired()
            log(f"v5: report correct, fault repaired (delta {result.get('score_delta')})")
            self.correct_reports += 1
            self.planner.forget_quality_history()
            self.ref_from_hours = hours
        else:
            log(f"v5: report false (delta {result.get('score_delta')}); free left {self.detector.free_left()}")


def main() -> int:
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    rules_only = model_disabled()
    if rules_only:
        log("v5: OBSERVER_MODEL_DISABLED=1, running rules only (no model calls)")
    elif not api_key():
        # a run without the model still scores: never exit before the first decision
        log("v5: no API key (set OPENAI_API_KEY); running rules only")
        rules_only = True
    agent = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            log(f"v5: unreadable line skipped: {line[:80]!r}")
            continue
        kind = message.get("message_type")
        if message.get("protocol_version") != PROTOCOL:
            log(f"v5: unexpected protocol {message.get('protocol_version')!r}")
        if kind == "initialize":
            try:
                agent = ObserverAgent(message["payload"], rules_only=rules_only)
            except Exception as exc:  # noqa: BLE001 - answer every request even if setup failed
                log(f"v5: initialize failed {type(exc).__name__}: {exc}")
                agent = None
        elif kind == "decision_request":
            try:
                if agent is None:
                    raise RuntimeError("agent not initialized")
                action = agent.respond(message["payload"])
            except Exception as exc:  # noqa: BLE001 - never crash the run: wait one slot instead
                log(f"v5: error {type(exc).__name__}: {exc}; waiting one slot")
                action = {"action": "wait", "duration_seconds": 900, "reason": "internal error"}
            action.setdefault("decision_source", "rules" if rules_only else "llm-advised")
            print(json.dumps({"protocol_version": PROTOCOL, "message_type": "decision_response",
                              "decision_sequence": message["decision_sequence"], **action}, separators=(",", ":")), flush=True)
        elif kind == "finish":
            payload = message.get("payload", {})
            log(f"v5 finished: termination_reason={payload.get('termination_reason')} "
                f"observes={agent.observes if agent else 0} monitors={agent.monitors if agent else 0} reports={agent.reports if agent else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
