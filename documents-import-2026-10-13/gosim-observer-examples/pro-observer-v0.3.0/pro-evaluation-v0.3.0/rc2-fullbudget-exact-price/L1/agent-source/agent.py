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
   report the model confirms or vetoes. Calls run in the background; without an API key, or when the platform
   sets OBSERVER_MODEL_DISABLED=1 (an evaluation without a model), the agent runs on rules only.
"""
from __future__ import annotations

import bisect
import json
import os
import sys
import hashlib
import math
from pathlib import Path
import time
import switches as v7
from datetime import timedelta

from advisor import Advisor, canonical_weather
from decision_log import DecisionLogger, sanitize
from fault import FaultDetector, FREE_STEP
from llm_client import LLMClient, api_key, load_dotenv
from planner import MONITOR_T, Planner, DIAG, LP_WEATHER, LP_EVENTS, DESI_HA
from skymath import format_utc, parse_utc
from walltime import WallBudget
from fault_mh import quality_bounds

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
# Reserve is expressed in official normalized CPU seconds, then calibrated per turn.
CPU_RESERVE_NORMALIZED = max(0.0, _env("CPU_RESERVE_NORMALIZED", 20.0))
SEARCH_ALLOWANCE_FACTOR = max(1.0, _env("SEARCH_ALLOWANCE_FACTOR", 1.5))
SEARCH_WIDTH_MAX = max(1.0, min(20.0, _env("SEARCH_WIDTH_MAX", 5.0)))
FIRST_LEGAL_CPU_SECONDS = max(.001, min(.25, _env("FIRST_LEGAL_CPU_SECONDS", .05)))
WALL_RESERVE_SECONDS = 100.0             # 1800s hard cap minus the 1700s acceptance limit
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
# development only (benchmarks of the planner on dev cards): report exactly at these UTC times (comma separated)
ORACLE_REPORTS = sorted(parse_utc(s) for s in os.environ.get("V5_ORACLE_REPORTS", "").split(",") if s.strip())


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

    def set_context(self, *_args):
        pass

    def plan_is_current(self):
        return True

    def fault_is_current(self):
        return True

    def invalidate_fault(self):
        pass


def model_disabled() -> bool:
    """The platform sets OBSERVER_MODEL_DISABLED=1 for an evaluation started with 「本次不提供模型」 / --no-model."""
    return os.environ.get("OBSERVER_MODEL_DISABLED") == "1"


class ObserverAgent:
    def __init__(self, init: dict, rules_only: bool = False):
        started = time.monotonic()
        v7.announce(log)
        self.wall = WallBudget() if v7.WALL or v7.ASYNC else None
        self.planner = Planner(init, log=log)
        rules_only = rules_only or model_disabled() or not api_key()
        self.rules_only = rules_only
        self.current_sequence = None
        self.state_revision = 0
        self.pending_record = None
        self.search_base_cpu_ema = 0.0
        self.reserve_process_seconds = 0.0
        self.state_log_cpu_ema = 0.0
        source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(Path(__file__).resolve().parent.glob("*.py"))}
        settings = {k:v for k,v in os.environ.items() if k.startswith(("PRO_", "V5_", "V6_", "V7_"))}
        self.logger = DecisionLogger({"source_hashes": source_hashes, "public_initialize": init,
                                      "configuration": settings, "rules_only": rules_only})
        self.init_hash = hashlib.sha256(json.dumps(init, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.client = None if rules_only else LLMClient(log=log)
        self.advisor = RulesOnly() if rules_only else Advisor(self.client, log=log)
        self.model_wait = 0.0                    # wall seconds spent waiting for the model (not planning cost)
        self.fault_likely = None                 # tonight's model estimate that an instrument fault is active
        self.advice_revision = 0
        self.advice_applications = 0
        self.model_valid_responses = 0
        self.model_state_changes = 0
        self.model_vetoes = 0
        self.model_plan_active = False
        self.model_plan_baseline = None
        self.model_plan_changed = False
        self.model_veto_this_turn = False
        self.audit_action_token = None
        self.start = parse_utc(init["survey"]["start_utc"])
        self.forecast_notices: list = []
        self.night_seen = None
        self.observes = 0
        self.monitors = 0
        self.last_exposure_hours = -1e9          # when the last observe (planned or monitoring) was sent
        self.last_valid_exposure_hours = -1e9
        self.monitor_turn = False
        # fault reporting state
        reporting = init["scoring"].get("reporting", {})
        self.free_allowance = int(reporting.get("false_report_free_allowance", 0))
        self.detector = FaultDetector(self.free_allowance, log=log)
        self.reports = 0
        self.dutylog_report_key = None
        self.dutylog_report_receipt = None
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
        self.night_value = None
        self.night_skipped = None
        self.level_counts = {}
        self.no_plan_waits = 0
        self.action_counts = {}
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
        self.monitor_turn = False
        self._turn_cpu_started = cpu_started
        self._turn_wall_started = started
        cpu_left, wall_left, fair = self._clock(payload)
        self.reserve_process_seconds = CPU_RESERVE_NORMALIZED * self._cpu_speed_factor(payload) if fair else 0.01
        self.planner.cpu_deadline = cpu_started + max(0.0, cpu_left - self.reserve_process_seconds)
        self.planner.wall_deadline = started + max(0.0, wall_left - 0.01)
        self._global_cpu_deadline = self.planner.cpu_deadline
        self._global_wall_deadline = self.planner.wall_deadline
        self.planner.decision_record = {}
        self.planner.cpu_components = {}
        skipped = min(cpu_left - self.reserve_process_seconds, wall_left - 0.01) <= 0.002
        if skipped:
            action = {"action": "finish", "reason": "computation budget reserve"}
        else:
            action = self._respond(payload)
        self._log_outcome(payload, skipped)
        if self.wall is not None:
            self.wall.action = ('wait_until' if action.get('until_utc') else action.get('action','wait'))
        # _respond calls _pace before searching: charge the level actually used this turn.
        level = self.planner.fast_level
        self.level_counts[level] = self.level_counts.get(level,0)+1
        kind=action.get('action','?')
        self.action_counts[kind] = self.action_counts.get(kind,0)+1
        deep = self.planner.deep and level == 0
        token = (self.night_seen, self.advice_revision)
        if not self.rules_only and self.model_influence_current() and token != self.audit_action_token:
            log('v6audit ' + json.dumps({'stage': 'action', 'now': payload['now_utc'],
                'advice_revision': self.advice_revision, 'action': action.get('action'),
                'pointing': action.get('pointing'), 'bad_forecast': self.planner.bad_forecast,
                'avoid': sorted(self.planner.extra_avoid), 'fault_likely': self.fault_likely}, separators=(',', ':')))
            self.audit_action_token = token
        # the platform charges CPU time inside our turns; waiting for the model is free of CPU, so keep it
        # out of the real-time estimate as well
        cpu = time.process_time() - cpu_started
        if DIAG:
            self.planner.diag['cpu'] += cpu
        wall = time.monotonic() - started - (self.model_wait - model_before)
        self.turns += 1
        if action.get("action") != "observe" or self.monitor_turn:   # a monitoring exposure costs no search
            self.other_cpu += cpu
            self.other_wall += wall
        elif deep:
            for k, cost in enumerate((cpu, wall)):
                c = self.deep_ema[k]
                self.deep_ema[k] = cost if c == 0.0 else 0.9 * c + 0.1 * cost
        elif level < 4:
            for ema, cost in ((self.cost_ema, cpu), (self.wall_ema, wall)):
                c = ema[level]
                ema[level] = cost if c == 0.0 else 0.9 * c + 0.1 * cost
                for k in range(level + 1, 4):   # cheaper levels not measured yet: a third of the level above
                    if ema[k] == 0.0 or ema[k] > ema[k - 1]:
                        ema[k] = ema[k - 1] / 3.0
        used_width = max(1.0, getattr(self.planner, "search_width_multiplier", 1.0))
        if kind == "observe" and not self.monitor_turn:
            base_cost = cpu / used_width
            self.search_base_cpu_ema = base_cost if not self.search_base_cpu_ema else .9*self.search_base_cpu_ema + .1*base_cost
        self.turn_end = time.monotonic()
        self._log_decision(payload, action, cpu, wall, self.model_wait - model_before)
        self.turn_end = time.monotonic()
        state_log_cost = self.planner.cpu_components.get("state_update", 0.0) + self.logger.last_cpu_seconds
        self.state_log_cpu_ema = state_log_cost if not self.state_log_cpu_ema else .9*self.state_log_cpu_ema + .1*state_log_cost
        return action

    def _target_evidence(self, target_ids):
        planner = self.planner
        rows = {}
        for target_id in target_ids:
            i = planner.index_of.get(str(target_id))
            if i is not None:
                rows[str(target_id)] = {"required": planner.required[i], "required_status": planner.required_status[i],
                                        "raw_factor_lower": planner.factor_lower[i], "raw_factor_upper": planner.factor_upper[i]}
        return rows

    def _log_outcome(self, payload, state_processing_skipped=False):
        if self.pending_record is None:
            return
        previous = self.pending_record
        current_total = payload.get("running_total")
        old_total = previous.get("running_total")
        delta = current_total - old_total if isinstance(current_total, (float,int)) and isinstance(old_total, (float,int)) else None
        messages = [m for m in payload.get("new_messages", []) if m.get("record_type") in ("state_resync", "observation_request_result", "report_result")]
        # A science delta can include correction; preserve both result and resync evidence.
        self.state_revision += 1
        old_evidence = previous.get("target_evidence", {})
        new_evidence = self._target_evidence(old_evidence)
        transitions = [{"target_id": key, "old": old_evidence[key], "new": new_evidence.get(key),
                        "source": "public_hit_factor_bounds_and_resync"} for key in old_evidence]
        self.logger.emit({"record_type": "outcome", "step": previous["step"], "time": payload.get("now_utc"),
                          "state_id": f"{self.init_hash}:{self.state_revision}", "result": payload.get("last_result"),
                          "realized": {"science_delta_including_corrections": delta, "quality": None,
                                       "required_truth": None, "required_evidence_transitions": transitions, "state_changes": messages},
                          "state_processing_skipped": state_processing_skipped,
                          "previous_decision_log_cost": previous.get("log_cost"),
                          "active_requests": payload.get("active_requests", []), "wallclock": payload.get("wallclock", {})})
        self.pending_record = None

    def _log_decision(self, payload, action, cpu, wall, model_seconds):
        step = self.current_sequence if self.current_sequence is not None else self.decisions
        detail = dict(getattr(self.planner, "decision_record", {}) or {})
        detail.update({"record_type": "decision", "step": step, "time": payload.get("now_utc"),
                       "state_id": f"{self.init_hash}:{self.state_revision}", "initialize_hash": self.init_hash,
                       "selected": dict(action), "observe_index": payload.get("observe_action_index") if action.get("action") == "observe" else None,
                       "cpu": {"process_seconds": cpu, "wall_seconds_excluding_model_wait": wall,
                               "components": getattr(self.planner, "cpu_components", {}), "fast_level": self.planner.fast_level,
                               "previous_log_emit_cpu_seconds": getattr(self.logger, "last_cpu_seconds", 0.0),
                               "process_seconds_scope": "turn_until_current_decision_log",
                               "reserve_process_seconds": self.reserve_process_seconds,
                               "reserve_normalized_seconds": CPU_RESERVE_NORMALIZED,
                               "search_width_multiplier": getattr(self.planner,"search_width_multiplier",1.0), **(payload.get("wallclock") or {})},
                       "model": {"wait_wall_seconds": model_seconds, "rules_only": self.rules_only}})
        self.logger.emit(detail)
        assigned_ids = list(action.get("assignments", {}).values())
        self.pending_record = {"step": step, "running_total": payload.get("running_total"),
                               "target_evidence": self._target_evidence(assigned_ids),
                               "log_cost": {"cpu_seconds": getattr(self.logger, "last_cpu_seconds", 0.0),
                                            "wall_seconds": getattr(self.logger, "last_wall_seconds", 0.0)}}

    def finalize_log(self, reason):
        if self.pending_record is not None:
            self.logger.emit({"record_type": "outcome", "step": self.pending_record["step"],
                              "status": "pending", "termination_reason": reason, "realized": None})
            self.pending_record = None

    def _respond(self, payload: dict) -> dict:
        now = parse_utc(payload["now_utc"])
        if v7.ASYNC:
            self.model_veto_this_turn = False
        if self.last_now is not None and self.planner.current_night(now) is not None:
            step = (now - self.last_now).total_seconds()
            if 0 < step <= 3600:
                self.sim_step_ema = step if self.sim_step_ema is None else 0.95 * self.sim_step_ema + 0.05 * step
        self.last_now = now
        hours = (now - self.start).total_seconds() / 3600.0
        planner = self.planner
        current_night = planner.current_night(now)
        if self.wall is not None:
            self.wall.update(payload, now, current_night[0] if current_night else None)
        if v7.ASYNC:
            if self.client is not None:
                self.client.allow_submit = self._remaining_model_budget() > 0.
        for message in payload.get("new_messages", []):
            if message.get("record_type") == "forecast":
                if planner.weather is not None:
                    if planner.weather.on_forecast(message, now):
                        self.forecast_notices = message.get("notices", [])
                        planner.long_dirty = True
                else:
                    self.forecast_notices = message.get("notices", [])
                    if LP_EVENTS or DESI_HA:
                        planner.long_dirty = True
        if v7.ASYNC:
            self._refresh_model_context(hours, current_night, now, payload)
        last = payload.get("last_result") or {}
        if last.get("action") == "report":
            self._on_report_result(last, hours)
        state_started = time.process_time()
        planner.set_result_context(payload)
        quake = self.quake_on  # Outcome learning uses the state of the preceding exposure.
        known_flat = bool(v7.FLAT and planner.dutylog and planner.pending_duration > 0
                          and planner.dutylog.overlaps_flat(now-timedelta(seconds=planner.pending_duration),now))
        if last.get('action')=='observe' and not known_flat and any(float(h.get('score',0))>0 for h in last.get('hits',[])):
            self.last_valid_exposure_hours=hours
        if v7.FAULT and last.get('action') == 'observe' and planner.pending_duration>0:
            lower,upper=[],[]
            for hit in last.get('hits',[]):
                index=planner.index_of.get(hit.get('target_id'))
                if index is None:
                    lower.append(0.);upper.append(float('inf'));continue
                lo,hi=quality_bounds(float(hit['score']),planner.weight[index],planner.flux[index],
                    planner.pending_duration,planner.f0t0,planner.multipliers[planner.pending_program],planner.mismatch)
                lower.append(lo);upper.append(hi)
            beginning=now-timedelta(seconds=planner.pending_duration)
            excluded=bool(v7.FLAT and planner.dutylog and planner.dutylog.overlaps_flat(beginning,now))
            self.detector.add_measurement(hours-planner.pending_duration/3600.,hours,planner.pending_night,
                upper,sum(float(h['score']) for h in last.get('hits',[])),planner.pending_notices,planner.notices,
                excluded=excluded,lower_qualities=lower)
        planner.on_result(payload.get("last_result"), now, hours)
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
        if planner.weather_sample is not None:
            ni, notices, lo, hi = planner.weather_sample
            notice_rows = [{'event_kind': k, 'direction': d} for k, d in notices]
            start_s=(now - parse_utc(planner.weather.nights[ni]['observing_start_utc'])).total_seconds()-planner.pending_duration
            slot=int(start_s // planner.slot_seconds)
            end_slot=int((start_s+planner.pending_duration-1e-6)//planner.slot_seconds)
            suspect = bounds is not None and bounds[1] < .87
            weather_clean = not quake and hours-self.quake_onset_hours >= 14*24 and not suspect and not planner.exposure_closed
            if slot==end_slot and weather_clean:
                planner.weather.observe_open(ni, slot, True, notice_rows, planner.pending_duration)
                planner.weather.observe_quality(ni, slot, lo, hi, notice_rows)
        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))
        quake = any(kind == "earthquake" for kind, _ in planner.notices)
        if quake and not self.quake_on:
            self.quake_onset_hours = hours
            log(f"v5: earthquake notice at {payload['now_utc']}")
        self.quake_on = quake
        planner.on_requests(payload.get("active_requests", []), now)
        if any(m.get("record_type") == "state_resync" for m in payload.get("new_messages", [])):
            # Fault/quality summaries cannot retain observations removed by a correction.
            self.detector.reset(hours, "state correction")
            self.r_hours.clear(); self.b_hours.clear()
            self.advisor.invalidate_fault()
            if planner.weather is not None:
                previous = planner.weather
                planner.weather = type(previous)(previous.nights)
                planner.weather.forecast = previous.forecast
                planner.weather.revision = previous.revision + 1
                planner.long_dirty = True
        planner.cpu_components["state_update"] = time.process_time() - state_started
        self._pace(payload, now)
        if planner.budget_expired():
            cpu_now, wall_now = time.process_time(), time.monotonic()
            if cpu_now >= self._global_cpu_deadline or wall_now >= self._global_wall_deadline:
                return {"action": "finish", "reason": "computation budget reserve"}
            # Reconciliation can cost more than the soft per-turn search share.
            # Give the planner bounded work to obtain its first legal option.
            planner.cpu_deadline = min(self._global_cpu_deadline, cpu_now + FIRST_LEGAL_CPU_SECONDS)
            planner.wall_deadline = min(self._global_wall_deadline, wall_now + max(.05, FIRST_LEGAL_CPU_SECONDS))

        night = planner.current_night(now)
        if night is None:
            nxt = planner.next_night_start(now)
            if nxt is None:
                return {"action": "finish", "reason": "no observing night left"}
            return {"action": "wait", "until_utc": format_utc(nxt), "reason": "daytime: sleep until the next night"}
        night_index, night_start, night_end = night
        if self.night_seen != night_index:
            self.night_seen = night_index
            self.night_value = None
            self.night_skipped = None
            self._night_advice(night_start, payload, hours)
        else:
            self._apply_advice(*self.advisor.poll())
        if (night_end - now).total_seconds() <= 0:
            nxt = planner.next_night_start(now)
            if nxt is None:
                return {"action": "finish", "reason": "survey over"}
            return {"action": "wait", "until_utc": format_utc(nxt), "reason": "night ending"}
        if planner.site_closed():
            if v7.WALL:
                end=self.wall.wait_until(now,night_end,planner.slot_seconds,planner.requests)
                if planner.weather is not None:
                    b=payload.get('latest_bulletin') or {}
                    planner.weather.observe_open(night_index,int((now-night_start).total_seconds()//planner.slot_seconds),
                        False,b.get('notices',[]),(end-now).total_seconds())
                return {'action':'wait','until_utc':format_utc(end),'reason':'v7 closed: next public event'}
            if planner.weather is not None:
                b = payload.get('latest_bulletin') or {}
                planner.weather.observe_open(night_index, int((now-night_start).total_seconds()//planner.slot_seconds), False,
                    b.get('notices', []), self._to_next_slot(now,night_start))
            return {"action": "wait", "duration_seconds": self._to_next_slot(now, night_start),
                    "reason": "bulletin: rain/storm over the whole sky"}
        report = self._maybe_report(hours, payload)
        if report is not None:
            return report
        if v7.FLAT and planner.dutylog is not None:
            flat_end=planner.dutylog.flat_end(now)
            if flat_end is not None:
                return {'action':'wait','until_utc':format_utc(min(flat_end,night_end)), 'reason':'v7 announced flat field'}
        if v7.WALL and self._low_value_night(now,night_end):
            if self._monitor_due(hours) and not planner.all_sky_weather() and not planner.budget_expired():
                action=planner.monitor(now,night_end,night_index,hours)
                if action is not None:
                    self.monitor_turn=True
                    self.monitors+=1
                    self.last_exposure_hours=hours
                    action['reason']='v7 monitoring before low-value wait'
                    return action
            self.night_skipped=night_index
            log('v7 low night: '+json.dumps({'night':night_index,'value_per_hour':self.night_value,
                'lambda_wall':self.wall.lambda_wall,'turn_cost':self.wall.predicted_turn}))
            end=self.wall.wait_until(now,night_end,planner.slot_seconds,planner.requests,
                skip_bulletins=v7.WAIT_SKIP and not self._fault_candidate(hours))
            return {'action':'wait','until_utc':format_utc(end),'reason':'v7 low night value: next public event'}
        action = planner.plan(now, night_end, night_index, hours)
        if v7.WALL and self.night_value is None and action is not None:
            self.night_value=planner.last_plan_gain*3600./max(1.,action['duration_seconds'])
        if action is None:
            wait = self._to_next_slot(now, night_start)
            if planner.next_up is not None:
                wait = max(planner.min_exposure, min(planner.max_exposure, wait, int(planner.next_up)))
            if v7.WALL:
                wait=(self.wall.wait_until(now,night_end,planner.slot_seconds,planner.requests,planner.next_up,
                    skip_bulletins=v7.WAIT_SKIP and not self._fault_candidate(hours))-now).total_seconds()
            monitor_gate = ((planner.fast_level <= 1) if not v7.WALL else self._monitor_due(hours)) and not planner.budget_expired()
            monitor_gap = MONITOR_GAP*(2 if v7.WALL and self.wall.escalation>=2 else 1)
            if (MONITOR_GAP > 0 and hours - self.last_exposure_hours >= monitor_gap and monitor_gate
                    and wait > MONITOR_T + 120 and not planner.all_sky_weather()):
                action = planner.monitor(now, night_end, night_index, hours)
                if action is not None:
                    self.monitor_turn = True
                    self.monitors += 1
                    self.last_exposure_hours = hours
                    action["reason"] = f"monitoring the instrument: {len(action['assignments'])} fibres, nothing has value up"
                    return action
            if v7.WALL:
                self.no_plan_waits += 1
                return {'action':'wait','until_utc':format_utc(now+timedelta(seconds=wait)), 'reason':'v7 nothing useful: next event'}
            self.no_plan_waits += 1
            return {"action": "wait", "duration_seconds": int(max(planner.min_exposure, min(planner.max_exposure, wait))), "reason": "nothing useful is up"}
        self.observes += 1
        self.last_exposure_hours = hours
        action["reason"] = f"{len(action['assignments'])} fibres, program {action['program']}"
        return action

    def _to_next_slot(self, now, night_start) -> int:
        slot = self.planner.slot_seconds
        into = (now - night_start).total_seconds() % slot
        return int(max(self.planner.min_exposure, min(self.planner.max_exposure, slot - into)))

    def _low_value_night(self, now, night_end):
        """Use the first executed plan's hourly value; never discard an unexecuted plan's state."""
        if not v7.THETA_SCALE or not self.wall.pressure or self.night_value is None:
            return False
        p=self.planner
        if any(req and factor<.5 and p.last_night[i]>=self.night_seen and p.hmax[i]>0
               for i,(req,factor) in enumerate(zip(p.required,p.factor))):
            return False
        if any(float(r.get('completion_reward',0))>0 for r in p.requests) or self.detector.pending:
            return False
        seconds=max(1.,(night_end-now).total_seconds())
        turns=max(1.,seconds/max(p.min_exposure,self.sim_step_ema or p.slot_seconds))
        theta=self.wall.lambda_wall*turns*self.wall.predicted_turn*3600./seconds
        theta*=v7.THETA_SCALE*(2 if self.wall.escalation>=4 else 1)
        return self.night_value<theta

    def _monitor_due(self,hours):
        if not MONITOR_GAP or self.monitors+1>v7.MONITOR_CAP*max(10,self.turns+1):
            return False
        gap=hours-self.last_valid_exposure_hours
        minimum=MONITOR_GAP*(2 if self.wall and self.wall.escalation>=2 else 1)
        if gap<minimum or hours-self.last_exposure_hours<minimum:
            return False
        det=self.detector
        return self._fault_candidate(hours) or gap>=24.

    def _fault_candidate(self,hours):
        det=self.detector
        if (det.deep.count>0 and not det.deep.blocked) or det.bound_evidence(hours) is not None:
            return True
        step=det.best_step(hours,2,0.)
        return step is not None and step[0]<FREE_STEP

    # --- pace ---------------------------------------------------------------------------------------

    def _clock(self, payload: dict):
        """(CPU seconds left, real seconds left, fair clock?) from the request's wallclock block.

        Fair clock (current platform): the budget is normalized CPU time inside our turns, and
        remaining_real_cpu_seconds converts it to this machine's CPU seconds; a separate real-time cap
        (wall_remaining_seconds) guards against runaway runs. Reserve the 100s gap between the
        1800s hard cap and 1700s acceptance limit for pacing and model waits. Older runners count real time only."""
        wall = payload.get("wallclock") or {}
        if "remaining_real_cpu_seconds" in wall:
            return (float(wall["remaining_real_cpu_seconds"]),
                    max(0.0, float(wall.get("wall_remaining_seconds", 1e9)) -
                        (self.wall.reserve if v7.WALL else WALL_RESERVE_SECONDS)), True)
        remaining = float(wall.get("remaining_seconds", 1e9))
        return remaining, remaining, False

    def _cpu_speed_factor(self, payload):
        clock = payload.get("wallclock") or {}
        normalized = clock.get("remaining_seconds")
        real = clock.get("remaining_real_cpu_seconds")
        if isinstance(normalized, (int,float)) and isinstance(real, (int,float)) and normalized > 0:
            factor = real / normalized
        else:
            factor = clock.get("speed_factor", 1.0)
        return factor if isinstance(factor, (int,float)) and math.isfinite(factor) and factor > 0 else 1.0

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
        pace_window = 120. if v7.WALL else PACE_WINDOW_H
        if pace_window > 0:
            marks = self.rate_marks
            if not marks or elapsed - marks[-1][0] >= 4 * 3600.0:
                marks.append((elapsed, self.observes))
            k = bisect.bisect_right(marks, (elapsed - pace_window * 3600.0, float("inf"))) - 1
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
        future_state_log = 1.2 * self.state_log_cpu_ema * decisions_left
        spendable = cpu_left - self.reserve_process_seconds - other - future_state_log
        cpu_budget = PACE_SAFETY * max(0.0, spendable) / decisions_left if fair else 1e9
        # real time: the other turns, and the engine's time on every turn (several turns per observe decision)
        other_wall = 1.2 * self.other_wall * night_left / elapsed
        turns_per_decision = max(1.0, self.turns / self.observes) if self.observes >= 30 else 1.5
        wall_budget = PACE_SAFETY * max(0.0, wall_left - other_wall) / decisions_left - engine * turns_per_decision
        if v7.WALL:
            turns_per_decision=self.wall.turns_per_decision(elapsed,self.observes)
            predicted=self.wall.predict(decisions_left)
            remaining_turns=decisions_left*turns_per_decision
            self.wall.pressure = remaining_turns*predicted>wall_left
            self.wall.escalation = min(4,self.wall.escalation+1) if self.wall.pressure else max(0,self.wall.escalation-1)
            outside=self.wall.outside if self.wall.outside is not None else engine
            model_share=self._remaining_model_budget()
            wall_spendable=max(0.,wall_left-other_wall-remaining_turns*outside-model_share)
            cpu_budget=min(cpu_budget,PACE_SAFETY*wall_spendable/decisions_left)
            wall_budget=PACE_SAFETY*wall_spendable/decisions_left
            if self.client is not None and self.wall.escalation>=1:
                self.client.allow_submit=False
            # Expected remaining science is a conservative proxy; obligations stay separately protected.
            remaining_value=sum(w*max(0.,1.-c) for w,c in zip(self.planner.weight,self.planner.cur))
            self.wall.lambda_wall=remaining_value/max(1.,wall_left)
            self.planner.wall_action_cost=(self.wall.lambda_wall*predicted*(2 if self.wall.escalation>=3 else 1)
                                           if self.wall.pressure else 0.)
        available = max(0.0, cpu_left - self.reserve_process_seconds)
        # Fixed tiers stay deterministic; adaptive turns get an anytime effort allowance.
        allowance = available if FIXED_LEVEL >= 0 else min(available, max(.02, SEARCH_ALLOWANCE_FACTOR * max(0.0,cpu_budget)))
        self.planner.cpu_deadline = min(self.planner.cpu_deadline, self._turn_cpu_started + allowance)
        measured = self.search_base_cpu_ema or self.deep_ema[0] or self.cost_ema[0]
        width = min(SEARCH_WIDTH_MAX, max(1.0, max(0.0,cpu_budget)/measured)) if measured > 0 else 1.0
        self.planner.search_width_multiplier = 1.0 if FIXED_LEVEL >= 0 else width
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
        while level < 3 and (self.cost_ema[level] > cpu_budget or self.wall_ema[level] > wall_budget):
            level += 1
        if v7.WALL and min(cpu_left,wall_left)>=15.:
            old=min(self.planner.fast_level,3)
            if level>old:
                saved=max(0.,self.wall_ema[old]-self.wall_ema[level])*decisions_left
                # CPU exhaustion remains a hard constraint even if engine time dominates.
                cpu_over=self.cost_ema[old]>cpu_budget and self.cost_ema[old]*decisions_left>max(0.,spendable)
                if not cpu_over and saved<=v7.DOWNGRADE_FRAC*wall_left and self.wall.escalation<4:
                    level=old
            elif level<old and self.wall_ema[level]>(1-v7.UPGRADE_MARGIN)*max(0.,wall_budget):
                level=old
        if min(cpu_left, wall_left) < 15.0:
            level = 4
        # spare budget at level 0: search wider (its cost before measuring: DEEP_COST x level 0); once on, it
        # stays on up to DEEP_HYST x the budget, so a cost near the budget does not flip it every few decisions
        deep_cpu = self.deep_ema[0] or DEEP_COST * self.cost_ema[0]
        deep_wall = self.deep_ema[1] or DEEP_COST * self.wall_ema[0]
        slack = DEEP_HYST if self.planner.deep else 1.0
        deep = (bool(DEEP) and level == 0 and self.cost_ema[0] > 0.0 and deep_cpu <= slack * cpu_budget
                and deep_wall <= wall_budget)
        if deep != self.planner.deep:
            log(f"v5: deep search {'on' if deep else 'off'} (cpu budget {min(cpu_budget, 99) * 1000:.0f} ms, deep cost {deep_cpu * 1000:.0f} ms)")
            self.planner.deep = deep
        if level != self.planner.fast_level:
            log(f"v5: pace level {level} (cpu budget {min(cpu_budget, 99) * 1000:.0f} ms, wall budget {wall_budget * 1000:.0f} ms, "
                f"cpu costs {[round(c * 1000) for c in self.cost_ema]} ms, {decisions_left:.0f} decisions left)")
            self.planner.fast_level = level

    # --- model stages (advisor.py): night plan and fault review at every night start --------------------

    def _tonight_forecast(self, night, now):
        if night is None:
            return []
        date = (self.planner.weather.nights[night[0]]['night_date'] if LP_WEATHER else
                (night[1] - timedelta(hours=12)).date().isoformat())
        if self.planner.weather is not None and self.planner.weather.key_for(
                self.planner.weather.nights[night[0]], now) is None:
            return []
        return [n for n in self.forecast_notices if date in n.get('nights', [])]

    def _refresh_model_context(self, hours, night, now, payload):
        weather = [self.forecast_notices, (payload.get('latest_bulletin') or {}).get('notices', [])]
        if v7.TIERED:
            weather = canonical_weather(self._tonight_forecast(night, now), weather[1])
        self.advisor.set_context(hours, night[0] if night else None,
            json.dumps(weather, sort_keys=True, separators=(',', ':')))
        if self.model_plan_active and not self.advisor.plan_is_current():
            before = [self.planner.bad_forecast, sorted(self.planner.extra_avoid)]
            tonight = []
            if night is not None:
                date = (self.planner.weather.nights[night[0]]['night_date'] if LP_WEATHER else
                        (night[1] - timedelta(hours=12)).date().isoformat())
                tonight = [n for n in self.forecast_notices if date in n.get('nights', [])]
                if self.planner.weather is not None and self.planner.weather.key_for(
                        self.planner.weather.nights[night[0]], now) is None:
                    tonight = []
            self.planner.bad_forecast = any(n.get('direction') == 'ALL' and
                n.get('event_kind') in BAD_KINDS for n in tonight)
            self.planner.extra_avoid = set()
            self.model_plan_active = self.model_plan_changed = False
            log('v7model_revoke ' + json.dumps({'stage':'night_plan', 'before':before,
                'after':[self.planner.bad_forecast, []], 'reason':'night/weather changed'}, separators=(',', ':')))
        if not self.advisor.fault_is_current():
            self.fault_likely = None

    def model_influence_current(self):
        """Active model policy or this turn's veto; not a claim of counterfactual action gain."""
        if not v7.ASYNC:
            return bool(self.advice_revision)
        return bool(self.model_veto_this_turn or
                    (self.model_plan_changed and self.advisor.plan_is_current()) or
                    (self.fault_likely is not None and self.fault_likely <= MODEL_FAULT_LOW and
                     self.advisor.fault_is_current()))

    def _night_advice(self, night_start, payload: dict, hours: float) -> None:
        """Night start: rule defaults first, then the two model calls (night plan, fault review)."""
        night_date = (self.planner.weather.nights[self.night_seen]['night_date'] if LP_WEATHER
                      else (night_start - timedelta(hours=12)).date().isoformat())
        if self.planner.weather is not None:
            self.planner.weather.start_night(self.night_seen,parse_utc(payload['now_utc']))
        tonight = [n for n in self.forecast_notices if night_date in n.get("nights", [])]
        if self.planner.weather is not None and self.planner.weather.key_for(
                self.planner.weather.nights[self.night_seen], parse_utc(payload['now_utc'])) is None:
            tonight = []
        if v7.TIERED:
            tonight = self._tonight_forecast((self.night_seen, night_start), parse_utc(payload['now_utc']))
        bulletin = (payload.get("latest_bulletin") or {}).get("notices", [])
        # rule defaults, kept when the model gives no valid answer
        self.planner.bad_forecast = any(n.get("direction") == "ALL" and n.get("event_kind") in BAD_KINDS for n in tonight)
        self.planner.extra_avoid = set()
        self.fault_likely = None
        self.advice_revision = 0
        if v7.ASYNC:
            self.model_plan_active = self.model_plan_changed = False
        left = self._clock(payload)[1]
        started = time.monotonic()
        answers = self.advisor.start_night(night_date, tonight, bulletin, self._fault_table(hours), left,
                                           self._model_wait_budget(payload, night=True) if v7.TIERED else self._model_wait_budget(payload))
        self.model_wait += time.monotonic() - started
        self._apply_advice(*answers)

    def _remaining_model_budget(self):
        if not v7.ASYNC or self.rules_only or self.client is None:
            return 0.
        return max(0., v7.MODEL_SHARE * (self.wall.limit or 0.) - self.model_wait)

    def _model_wait_budget(self, payload: dict, night: bool = False) -> float:
        """How long a night start may wait for the model. Waiting costs no CPU budget, only real time: use half
        of the real time the planner and the engine will not need, spread over the nights left."""
        if v7.ASYNC:
            return max(0.,min(v7.NIGHT_WAIT if v7.TIERED and night else 5.,self._remaining_model_budget(),
                self._clock(payload)[1])) if not (v7.WALL and self.wall.escalation>=1) else 0.
        _, wall_left, _ = self._clock(payload)
        now = self.last_now
        nights_left = max(1, sum(1 for _, end in self.planner.nights if end > now))
        # Level 4 is the emergency search mode; the cost arrays have levels 0..3.
        per_decision = max(self.wall_ema[min(self.planner.fast_level, 3)], 0.05) + (self.engine_ema or 0.02)
        spare = wall_left - 1.5 * self._decisions_left(now) * per_decision - 60.0
        return max(0.0, min(MODEL_WAIT_MAX, 0.5 * spare / nights_left))

    def _apply_advice(self, plan, fault) -> None:
        if v7.ASYNC:
            self.model_valid_responses += int(plan is not None) + int(fault is not None)
        if plan is not None and v7.NIGHTPLAN != 'on':
            log('v7 night_plan '+v7.NIGHTPLAN+': '+json.dumps(plan,separators=(',',':')))
            plan=None
        if plan is not None:
            before = [self.planner.bad_forecast, sorted(self.planner.extra_avoid)]
            self.planner.bad_forecast = plan["bad_night"]
            self.planner.extra_avoid = set(plan["avoid_directions"])
            log(f"llm night plan {self.advisor.night_date}: bad_night={plan['bad_night']} avoid={plan['avoid_directions']} ({plan['reason']})")
            changed = before != [self.planner.bad_forecast, sorted(self.planner.extra_avoid)]
            if v7.ASYNC:
                if not self.model_plan_active:
                    self.model_plan_baseline = before
                self.model_plan_active = True
                self.model_plan_changed = self.model_plan_baseline != [self.planner.bad_forecast, sorted(self.planner.extra_avoid)]
                self.model_state_changes += int(changed)
            if not v7.ASYNC or changed:
                self.advice_revision += 1
                self.advice_applications += 1
            log('v6audit ' + json.dumps({'stage': 'night_plan', 'night': self.advisor.night_date,
                'before': before, 'after': [self.planner.bad_forecast, sorted(self.planner.extra_avoid)]}, separators=(',', ':')))
        if fault is not None:
            before_fault = self.fault_likely
            self.fault_likely = fault["fault_likely"]
            log(f"llm fault review {self.advisor.night_date}: fault_likely={fault['fault_likely']:.2f} ({fault['reason']})")
            changed = before_fault != self.fault_likely
            if v7.ASYNC:
                self.model_state_changes += int(changed)
                log('v7model_state ' + json.dumps({'stage':'fault_review', 'before':before_fault,
                    'after':self.fault_likely, 'state_changed':changed, 'action_causality':'not_established'}, separators=(',', ':')))
            if not v7.ASYNC or changed:
                self.advice_revision += 1
                self.advice_applications += 1

    def _fault_table(self, hours: float) -> dict:
        """The evidence the fault review reads: hourly medians of r over the last ~30 observed hours, with the
        weather-free efficiency bounds of each hour (lowest upper / highest lower bound, bandfit.py)."""
        rows = []
        for hour in sorted(h for h in set(self.r_hours) | set(self.b_hours) if h >= self.ref_from_hours)[-30:]:
            v = sorted(self.r_hours.get(hour, []))
            b = self.b_hours.get(hour)
            stamp = (self.start + timedelta(hours=hour)).strftime("%m-%dT%H")
            rows.append([stamp, round(v[len(v) // 2], 3) if v else None, len(v),
                         round(b[0], 2) if b and b[0] < 9 else None, round(b[1], 2) if b and b[1] > 0 else None])
        notices = sorted({f"{kind} {direction}" for kind, direction in self.planner.notices})
        det = self.detector
        return {"columns": ["utc_hour", "r", "exposures", "eff_upper_bound", "eff_lower_bound"], "rows": rows,
                "rule_evidence": det.last_evidence or None, "notices_now": notices,
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
        if ORACLE_REPORTS:
            now = parse_utc(payload["now_utc"])
            if self.reports < len(ORACLE_REPORTS) and now >= ORACLE_REPORTS[self.reports]:
                self.reports += 1
                return {"action": "report", "reason": "oracle benchmark"}
            return None
        if v7.VALUES['V6_DL_FAULT'] == '1' and det.free_left() > 0 and self.planner.dutylog is not None:
            event = self.planner.dutylog.due_fault(parse_utc(payload['now_utc']))
            if event is not None:
                # Log confidence describes parsing, never a calibrated fault posterior.
                # No detector evidence was probed; false receipts must not train its bounds.
                det.pending = None
                self.dutylog_report_key = event['event_key']
                self.reports += 1
                log(f"v7: free duty-log report at {payload['now_utc']} event={event['event_key']}")
                return {'action':'report','reason':'public duty log: scheduled guider work (free probe)'}
        likely = None if v7.TIERED else self.fault_likely
        allow_paid = not (likely is not None and likely <= MODEL_FAULT_LOW)
        if not det.should_report(hours, self.planner.notices, allow_paid=allow_paid):
            return None
        if not self._model_agrees(hours, payload):
            self._shadow(hours,'veto')
            det.veto(hours)
            return None
        self.reports += 1
        self._shadow(hours,'report')
        log(f"v5: report at {payload['now_utc']} ({det.last_evidence}), free left {det.free_left()}")
        return {"action": "report", "reason": det.last_evidence[:120]}

    def _shadow(self,hours,actual):
        if v7.VALUES['V7_SHADOW']=='1':
            log('v7 shadow: '+json.dumps({'hours':hours,'candidate':True,'evidence':self.detector.last_evidence,
                'free_left':self.detector.free_left(),'paid_policy':v7.VALUES['V7_PAID'],
                'actual_action':actual,'p':None,'V':None,'threshold':None,'calibration':'uncalibrated'},separators=(',',':')))

    def _model_agrees(self, hours: float, payload: dict) -> bool:
        """Paid probes only: the model looks at the evidence first and may veto. Free probes cost nothing, so they
        never wait for it. No answer in time: the rule's decision stands."""
        if self.detector.free_left() > 0:
            return True
        evidence = {"fault_table": self._fault_table(hours), "rule_evidence": self.detector.last_evidence,
                    "paid_false_reports_so_far": self.detector.paid_false, "correct_reports_so_far": self.detector.correct}
        started = time.monotonic()
        left = self._clock(payload)[1]
        budget=self._model_wait_budget(payload)
        verdict = self.advisor.confirm_report(evidence, left, budget if v7.ASYNC else min(30.0,2.*budget))
        log('v6audit ' + json.dumps({'stage': 'confirm_report', 'now': payload['now_utc'],
            'verdict': verdict, 'rule_evidence': self.detector.last_evidence[:120]}, separators=(',', ':')))
        self.model_wait += time.monotonic() - started
        if v7.ASYNC and verdict is not None:
            self.model_valid_responses += 1
        if verdict is False:
            if v7.ASYNC:
                self.model_vetoes += 1
                self.model_veto_this_turn = True
                self.advice_revision += 1
                self.advice_applications += 1
            log(f"v5: model vetoed a paid report at {payload['now_utc']}")
            return False
        if verdict is not None and not v7.ASYNC:
            self.advice_revision += 1
            self.advice_applications += 1
        return True

    def _on_report_result(self, result: dict, hours: float) -> None:
        correct = bool(result.get("correct"))
        if v7.VALUES['V6_DL_FAULT'] == '1':
            receipt = (hours, correct)
            if self.dutylog_report_receipt == receipt:
                return
            self.dutylog_report_receipt = receipt
            if self.planner.dutylog is not None:
                self.planner.dutylog.mark_report(result, self.start+timedelta(hours=hours), self.dutylog_report_key)
            self.dutylog_report_key = None
        self.detector.on_report_result(hours, correct)
        if correct:
            if v7.ASYNC:
                self.advisor.invalidate_fault()
                self.fault_likely=None
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
        log("v6: no API key (OPENAI_API_KEY / DEEPSEEK_API_KEY / KIMI_API_KEY); running rules only")
        rules_only = True
    agent = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            log("v0.3: unreadable JSON line skipped")
            continue
        kind = message.get("message_type")
        if message.get("protocol_version") != PROTOCOL:
            log(f"v5: unexpected protocol {message.get('protocol_version')!r}")
        if kind == "initialize":
            try:
                agent = ObserverAgent(message["payload"], rules_only=rules_only)
            except Exception as exc:  # noqa: BLE001 - answer every request even if setup failed
                log(f"v0.3: initialize failed {type(exc).__name__}")
                agent = None
        elif kind == "decision_request":
            try:
                if agent is None:
                    raise RuntimeError("agent not initialized")
                agent.current_sequence = message["decision_sequence"]
                action = agent.respond(message["payload"])
            except Exception as exc:  # noqa: BLE001 - never crash the run: wait one slot instead
                log(f"v0.3: error {type(exc).__name__}; finishing safely")
                action = {"action": "finish", "reason": "internal error"}
                if agent is not None:
                    try:
                        agent._log_outcome(message["payload"], True)
                        agent.planner.decision_record = {"constraints": {"feasible": None, "reason": "INTERNAL_ERROR"}}
                        agent._log_decision(message["payload"], action, None, None, None)
                    except Exception:
                        log("v0.3: diagnostic logging unavailable")
            action.setdefault("decision_source", "llm-advised" if agent is not None and agent.model_influence_current() else "rules")
            print(json.dumps({"protocol_version": PROTOCOL, "message_type": "decision_response",
                              "decision_sequence": message["decision_sequence"], **action}, separators=(",", ":")), flush=True)
        elif kind == "finish":
            payload = message.get("payload", {})
            if agent is not None:
                agent.finalize_log(payload.get("termination_reason"))
                log('v7model '+json.dumps({'model_blocking_seconds':agent.model_wait,
                    'wall_limit_seconds':agent.wall.limit if agent.wall is not None else None,
                    'advice_applications':agent.advice_applications,'valid_model_responses':agent.model_valid_responses,
                    'model_state_changes':agent.model_state_changes,'model_report_vetoes':agent.model_vetoes,
                    'night_plan_cache_hits':getattr(agent.advisor,'cache_hits',0),
                    'application_note':'state changes and vetoes; not counterfactual action gain','level_counts':agent.level_counts,
                    'no_plan_waits':agent.no_plan_waits,'action_counts':agent.action_counts,
                    'monitors':agent.monitors,'observes':agent.observes}))
                agent.planner.flush_diagnostics()
                if agent.client is not None:
                    log('v6model ' + json.dumps({'calls': len(agent.client.calls), 'transport_ok': agent.client.ok,
                        'transport_failed': agent.client.failed, 'applications': agent.advice_applications,
                        'in_flight': agent.client.in_flight()}))
            log(f"v5 finished: termination_reason={payload.get('termination_reason')} "
                f"observes={agent.observes if agent else 0} monitors={agent.monitors if agent else 0} reports={agent.reports if agent else 0}")
    if agent is not None: agent.finalize_log("stdin_closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
