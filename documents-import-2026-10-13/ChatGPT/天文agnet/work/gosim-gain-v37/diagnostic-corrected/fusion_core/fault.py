"""Exposure change-point and program-band anomaly detector, adapted from supplied source.
Thresholds are inherited heuristics, not certified measurements. Shared-weather band
bounds are model dependent. The empirical earthquake recovery curve is disabled by
default; during known earthquakes only relative drops can support bound probes.
"""
from __future__ import annotations

import os

WEATHER_KINDS = {"rain", "storm", "overcast", "haze", "cold_snap"}
DROP_KINDS = {"rain", "storm"}
COVER_KINDS = {"overcast", "haze"}
COLD_R, COLD_HI, COLD_LO = 0.92, 0.89, 0.95     # cold snap: typical multiplier, its floor and ceiling


def _env(name, default):
    return type(default)(os.environ.get(f"V5_{name}", default))


FREE_STEP = _env("FAULT_FREE_STEP", 0.82)
FREE_STEP_LAST = _env("FAULT_FREE_STEP_LAST", 0.78)   # the last free probe needs more
PAID_STEP = _env("FAULT_PAID_STEP", 0.76)          # a strong step: may use the last free probe
PAID_STEP_REAL = _env("FAULT_PAID_STEP_REAL", 0.60)   # a step for a paid probe (the bounds catch most faults first)
POST_MAX = _env("FAULT_POST_MAX", 0.90)        # every post exposure but one below this x pre median
FREE_POST_ROWS = _env("FAULT_FREE_POST", 3)
FREE_POST_HOURS = _env("FAULT_FREE_HOURS", 0.6)
PAID_POST_ROWS = _env("FAULT_PAID_POST", 4)
PAID_POST_HOURS = _env("FAULT_PAID_HOURS", 1.2)
PRE_ROWS = _env("FAULT_PRE_ROWS", 4)
MIN_PRE_ROWS = 3
SCAN_ROWS = 30                                  # change points searched among the last exposures
PERSIST_LEVEL = _env("FAULT_PERSIST_LEVEL", 0.80)   # median of the low nights below this x the level before
PERSIST_MAX = _env("FAULT_PERSIST_MAX", 0.88)       # ... and every one of them below this
PERSIST_FREE = _env("FAULT_PERSIST_FREE", 3)
PERSIST_LAST = _env("FAULT_PERSIST_LAST", 0.75)     # the last free probe: median of the low nights below this
PERSIST_NIGHTS = _env("FAULT_PERSIST_NIGHTS", 99)
CARRY_FREE = _env("FAULT_CARRY_FREE", 0.78)
CARRY_LAST = _env("FAULT_CARRY_LAST", 0.74)
CARRY_PAID = _env("FAULT_CARRY_PAID", 0.0)
REF_NIGHTS = 5
MIN_NIGHT_ROWS = 4
MAX_PAID = _env("FAULT_MAX_PAID", 3)
QUAKE_SETTLE_HOURS = _env("FAULT_QUAKE_SETTLE", 2.0)
BOUNDS = _env("FAULT_BOUNDS", 1)
BOUND_ABS = _env("FAULT_BOUND_ABS", 0.87)
BOUND_REL = _env("FAULT_BOUND_REL", 0.86)
BOUND_VETO = _env("FAULT_BOUND_VETO", 0.80)
BOUND_HOURS = _env("FAULT_BOUND_HOURS", 24.0)     # bound evidence counts while this recent
BOUND_PAID_ROWS = _env("FAULT_BOUND_PAID_ROWS", 2)
BOUND_PAID_DEEP = _env("FAULT_BOUND_PAID_DEEP", 0.80)   # ... or one exposure with hi below this
BOUND_MAX_PAID = _env("FAULT_BOUND_MAX_PAID", 2)
STEP_RESERVE = _env("FAULT_STEP_RESERVE", 1)     # free probes the r rules leave to the bound evidence
QUAKE_D0 = _env("FAULT_QUAKE_D0", 0.96)          # the deepest earthquake degradation assumed
QUAKE_RHO = _env("FAULT_QUAKE_RHO", 0.78)        # ... and its per-night healing factor
QUAKE_TRACK = int(os.environ.get("FUSION_QUAKE_CURVE", "0"))
CLOSED_MARGIN = _env("FAULT_CLOSED_MARGIN", 0.55)  # hours (exposure mid times) around a closed run left out


def _median(values):
    s = sorted(values)
    n = len(s)
    return 0.0 if n == 0 else (s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]))


class FaultDetector:
    def __init__(self, free_allowance: int, log=lambda text: None):
        self.log = log
        self.free_allowance = int(free_allowance)
        self.rows: list = []          # (hours, night, r) since the last reset
        self.quake_seen = False
        self.quake_night = None       # the first observed night of the current earthquake notice
        self.settle_until = -1e9
        self.false_since_correct = 0
        self.paid_false = 0
        self.correct = 0
        self.last_report = -1e9
        self.weather_before = -1e9        # change points up to this time were probed already (weather)
        self.persist_block_night = None   # the low-night run that was probed already
        self.pending = None               # what the last positive should_report was based on
        self.last_evidence = ""
        self.brows: list = []             # (hours, night, lo, hi, nights since the earthquake onset or None)
        self.bound_before = -1e9          # bound evidence up to this time was probed already (false)
        self.bound_abs = BOUND_ABS
        self.bound_rel = BOUND_REL
        self.bound_paid_false = 0
        self.closed_until = -1e9          # end of the last exposure that scored zero everywhere

    # --- signal ---------------------------------------------------------------------------------

    def reset(self, hours: float, why: str) -> None:
        self.rows = []
        self.brows = []
        self.weather_before = -1e9
        self.persist_block_night = None
        self.log(f"fault: reference reset at h{hours:.1f} ({why})")

    def closed(self, start: float, end: float, night=None) -> None:
        """An exposure from start to end scored zero everywhere: the dome was shut in unannounced closed slots
        (15 min each, in runs). Exposures that overlap part of such a run score at the open share of their time,
        a fake step (card b: two closed runs inside one night read as a step 0.26, a paid false report). Drop
        the exposures that may reach into the run before it, and skip those that may reach into it after. The
        sky after a closure is often worse than before it (dev card d: a step 0.54 across one), so a step is
        never measured across a closure: tonight's exposures before it leave the signal."""
        cut = start - CLOSED_MARGIN
        self.rows = [row for row in self.rows if row[0] < cut and (night is None or row[1] != night)]
        self.brows = [row for row in self.brows if row[0] < cut]
        self.closed_until = max(self.closed_until, end)

    def add_exposure(self, hours: float, night, r, notices, bounds=None, current=None) -> None:
        """notices: the bulletin notices when the exposure began; current: those now, or None if unknown (an
        earthquake during the exposure lowered its efficiency already, but only the bulletin after it says so)."""
        now = list(notices) if current is None else list(current)
        quake = any(kind == "earthquake" for kind, _ in list(notices) + now)
        if quake and not self.quake_seen:
            self.reset(hours, "earthquake onset")
            self.settle_until = hours + QUAKE_SETTLE_HOURS
            self.quake_night = None
        self.quake_seen = quake
        if quake and self.quake_night is None and night is not None:
            self.quake_night = night   # an onset by day counts from the next night: a threshold on the safe side
        sky = {kind for kind, direction in notices if direction == "ALL" and kind in WEATHER_KINDS}
        sky_now = {kind for kind, direction in now if direction == "ALL" and kind in WEATHER_KINDS}
        if sky != sky_now or sky & DROP_KINDS or hours < self.settle_until or hours - self.closed_until < CLOSED_MARGIN:
            return   # weather that began or ended during the exposure, rain, or next to a closed run
        covered = bool(sky & COVER_KINDS)
        cold = "cold_snap" in sky
        if bounds is not None and BOUNDS:
            lo, hi = bounds[0], bounds[1]
            if cold:
                lo, hi = lo / COLD_LO, hi / COLD_HI
            if covered:
                hi = float("inf")
            since = None
            if quake:
                since = max(0, night - self.quake_night) if QUAKE_TRACK and night is not None and self.quake_night is not None else 0
            if lo > 0 or hi < float("inf"):
                self.brows.append((hours, night, lo, hi, since))
            if len(self.brows) > 3000:
                self.brows = self.brows[-2000:]
        if r is None or r <= 0 or covered:
            return
        self.rows.append((hours, night, float(r) / (COLD_R if cold else 1.0)))
        if len(self.rows) > 3000:
            self.rows = self.rows[-2000:]

    def free_left(self) -> int:
        return max(0, self.free_allowance - self.false_since_correct)

    # --- evidence -------------------------------------------------------------------------------

    def best_step(self, hours: float, min_rows: int, min_hours: float, carry: bool = False):
        """(ratio, change-point time, post rows, post hours) of the deepest lasting step, or None.

        carry=False: change point and post window inside tonight. carry=True: the change point late in the
        previous observed night (post rows there >= 1) and the post window running on through tonight."""
        rows = self.rows
        n = len(rows)
        if n < min_rows + 2 or hours - rows[-1][0] > 1.5:
            return None
        tonight = rows[-1][1]
        best = None
        for j in range(n - min_rows, max(2, n - SCAN_ROWS) - 1, -1):
            night = rows[j][1]
            if rows[j - 1][1] != night or rows[j][0] <= self.weather_before:
                continue
            if (night == tonight) == carry:
                continue
            post = rows[j:]
            if carry:
                nights = {row[1] for row in post}
                own = sum(1 for row in post if row[1] == tonight)
                if len(nights) != 2 or own < 3 or rows[-1][0] - next(row[0] for row in post if row[1] == tonight) < FREE_POST_HOURS:
                    continue
            pre = [row for row in rows[max(0, j - PRE_ROWS):j] if row[1] == night]
            if len(pre) < MIN_PRE_ROWS and not (len(pre) >= 2 and post[0][0] - pre[0][0] >= 0.5):
                continue
            span = post[-1][0] - post[0][0]
            if span < min_hours:
                continue
            base = _median([row[2] for row in pre])
            values = sorted(row[2] / base for row in post)
            ratio = _median(values)
            if len(values) >= 2 and values[-2] > POST_MAX:
                continue   # the post window does not stay low
            if values[-1] > POST_MAX + 0.08:
                continue
            if best is None or ratio < best[0]:
                best = (ratio, rows[j][0], len(post), span)
        return best

    def persistence(self):
        """(nights in a row below the level before them, median ratio of those nights, first low night)."""
        nights: dict = {}
        for _, n, r in self.rows:
            nights.setdefault(n, []).append(r)
        levels = [(n, _median(v)) for n, v in nights.items() if len(v) >= MIN_NIGHT_ROWS]
        found = (0, 1.0, None)
        for k in range(len(levels) - 1, -1, -1):
            ref_levels = [lv for _, lv in levels[max(0, k - REF_NIGHTS):k]]
            if len(ref_levels) < 3:
                break
            ref = _median(ref_levels)
            low = [lv / ref for _, lv in levels[k:]]
            if max(low) >= PERSIST_MAX:
                break
            if _median(low) < PERSIST_LEVEL:
                found = (len(low), _median(low), levels[k][0])
        return found

    def bound_evidence(self, hours: float):
        """(exposures whose upper bound says the efficiency is low, their lowest upper bound) over the recent
        unprobed window, or None."""
        found = []
        los: list = []                    # lower bounds so far since the last reset, for the relative test
        for h, _, lo, hi, since in self.brows:
            ref = sorted(los)[-2] if len(los) >= 2 else 0.0   # the second highest: one stray bound is not enough
            if h > self.bound_before and hours - h <= BOUND_HOURS:
                limit = self.bound_abs if since is None else (self.bound_abs * (1.0 - QUAKE_D0 * QUAKE_RHO ** since) if QUAKE_TRACK else 0.0)
                if hi < limit or (ref > 0 and hi < self.bound_rel * ref):
                    found.append((hi, hi * self.bound_abs / max(limit, 1e-6)))
            if lo > 0:
                los.append(lo)
        if not found:
            return None
        return len(found), min(f[0] for f in found), min(f[1] for f in found)

    def bound_clears(self, since: float, night=None) -> bool:
        """Some exposure since then (or of that night on) bounds the efficiency above BOUND_VETO: no fault."""
        for h, n, lo, _, _ in self.brows:
            if (h >= since if night is None else n >= night) and lo > BOUND_VETO:
                return True
        return False

    # --- decision -------------------------------------------------------------------------------

    def should_report(self, hours: float, notices=(), allow_paid: bool = True) -> bool:
        if hours - self.last_report < 1.0:
            return False
        paid_ok = allow_paid and self.paid_false < MAX_PAID
        evidence = None
        bound = self.bound_evidence(hours) if BOUNDS else None
        if bound:
            count, low, norm = bound
            if self.free_left() > 0 or (allow_paid and self.bound_paid_false < BOUND_MAX_PAID
                                        and (count >= BOUND_PAID_ROWS or norm < BOUND_PAID_DEEP)):
                evidence = ("bound", hours, f"{count} exposures bound the efficiency below {self.bound_abs:.2f} "
                            f"(lowest upper bound {low:.2f})")
        # the r rules keep STEP_RESERVE free probes for the bound evidence, which is rarely wrong
        free = self.free_left() > STEP_RESERVE
        last = self.free_left() == STEP_RESERVE + 1
        step_free = FREE_STEP_LAST if last else FREE_STEP
        carry_free = CARRY_LAST if last else CARRY_FREE
        persist_free = PERSIST_LAST if last else PERSIST_LEVEL
        step = self.best_step(hours, FREE_POST_ROWS, FREE_POST_HOURS) if evidence is None else None
        if step and self.bound_clears(step[1] + 0.3):
            step = None
        if step:
            if free and step[0] < step_free:
                evidence = ("step", step[1], f"step {step[0]:.2f} over {step[2]} exposures / {step[3]:.1f} h")
            elif (paid_ok or self.free_left() > 0) and step[0] < (PAID_STEP if self.free_left() > 0 else PAID_STEP_REAL):
                strong = self.best_step(hours, PAID_POST_ROWS, PAID_POST_HOURS)
                if strong and strong[0] < (PAID_STEP if self.free_left() > 0 else PAID_STEP_REAL):
                    evidence = ("step", strong[1], f"step {strong[0]:.2f} over {strong[2]} exposures / {strong[3]:.1f} h")
        if evidence is None:
            carry = self.best_step(hours, FREE_POST_ROWS + 1, FREE_POST_HOURS, carry=True)
            if carry and self.bound_clears(carry[1] + 0.3):
                carry = None
            if carry and ((free and carry[0] < carry_free) or (paid_ok and carry[0] < CARRY_PAID and carry[2] >= 5)):
                evidence = ("step", carry[1], f"step {carry[0]:.2f} from late last night over {carry[2]} exposures")
        if evidence is None:
            count, ratio, first = self.persistence()
            if first is not None and first != self.persist_block_night and not self.bound_clears(0.0, first):
                if (free and count >= PERSIST_FREE and ratio < persist_free) or (paid_ok and count >= PERSIST_NIGHTS):
                    evidence = ("persist", first, f"{count} nights at {ratio:.2f} of the level before")
        if evidence:
            self.pending = evidence
            self.last_evidence = evidence[2]
            self.log(f"fault: report at h{hours:.1f}: {evidence[2]} ({'free' if self.free_left() > 0 else 'paid'})")
            return True
        return False

    def _probed(self, hours: float, paid: bool) -> None:
        """The pending evidence turned out to be no fault: never probe it again."""
        kind = self.pending[0]
        if kind == "step":
            self.weather_before = hours
        elif kind == "persist":
            self.persist_block_night = self.pending[1]
        else:
            # the bounds were wrong here: only lower upper bounds than these count from now on
            bound = self.bound_evidence(hours)
            self.bound_before = hours
            if bound:
                self.bound_abs = min(self.bound_abs, 0.97 * bound[2])   # in no-earthquake terms
            self.bound_rel *= 0.95
            self.bound_paid_false += paid

    def veto(self, hours: float) -> None:
        """The report was not sent (the model vetoed it): treat its evidence as weather."""
        self.last_report = hours
        if self.pending:
            self._probed(hours, False)
        self.pending = None

    def on_report_result(self, hours: float, correct: bool) -> None:
        self.last_report = hours
        if correct:
            self.correct += 1
            self.false_since_correct = 0
            self.reset(hours, "correct report: instrument repaired")
        else:
            paid = self.free_left() <= 0
            self.paid_false += paid
            self.false_since_correct += 1
            if self.pending:
                self._probed(hours, paid)
        self.pending = None
