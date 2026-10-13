"""R-I1 deep-quality evidence. Times and exposure durations are in hours."""
from math import isfinite
from statistics import median

CAT1 = 1  # unusable exposure: neither counts nor interrupts a run
CAT2 = 2  # weather/earthquake coupling; does not veto absolute deep quality
CAT3 = 4  # this run has already produced a false report


def quality_bounds(score, weight, flux, duration_seconds, f0t0, declared, mismatch):
    """Conservative q interval from the public six-decimal score, including saturation."""
    values = (score, weight, flux, duration_seconds, f0t0, declared, mismatch)
    if any(not isfinite(v) for v in values) or score < 0 or min(values[1:]) <= 0:
        return 0.0, float("inf")
    scale = f0t0 / (weight * flux * duration_seconds)
    low = max(0.0, score - .5e-6) * scale / max(declared, mismatch)
    upper_score = score + .5e-6
    high = upper_score * scale / min(declared, mismatch) if upper_score < weight * min(declared, mismatch) else float("inf")
    return low, high


def exposure_flags(score, notices=(), current=(), excluded=False):
    flags = CAT1 if excluded or score <= 0 else 0
    for kind, direction in list(notices) + list(current):
        if kind in {"rain", "storm"} and direction == "ALL":
            flags |= CAT1
        if kind == "earthquake" or (kind in {"overcast", "haze", "cold_snap"} and direction == "ALL"):
            flags |= CAT2
    return flags


class FaultMH:
    """Only the final-plan R-I1 channel; no uncalibrated posterior or type-II rule."""

    def __init__(self, threshold=0.05, min_exposures=2, min_hours=1.0):
        self.threshold = threshold
        self.min_exposures = min_exposures
        self.min_hours = min_hours
        self.last_end = float("-inf")
        self.reset()

    def reset(self):
        self.count = 0
        self.hours = 0.0
        self.start = None
        self.blocked = False
        self.paid_used = False

    def add_exposure(self, start, end, qualities, score, notices=(), current=(), excluded=False, lower_qualities=None):
        """Reject invalid/repeated intervals; keep CAT1 exposures out of all evidence."""
        if (not isfinite(start) or not isfinite(end) or end <= start
                or end <= self.last_end or start < self.last_end - 1e-9):
            return None
        start = max(start, self.last_end)
        self.last_end = end
        flags = exposure_flags(score, notices, current, excluded)
        values = [float(q) for q in qualities]
        if not values or any(q != q or q < 0 for q in values) or not isfinite(score):
            return None
        q = median(values)
        lows = values if lower_qualities is None else list(lower_qualities)
        if len(lows) != len(values) or any(not isfinite(v) or v < 0 or v > hi for v, hi in zip(lows, values)):
            return None
        lower = median(lows)
        if flags & CAT1:
            return q, flags
        if q >= self.threshold:
            if lower >= self.threshold:
                self.reset()
            else:
                # An uncertain exposure breaks accumulation but cannot prove recovery after a false report.
                self.count, self.hours, self.start = 0, 0.0, None
        else:
            if self.start is None:
                self.start = start
            self.count += 1
            self.hours += end - start
        return q, flags | (CAT3 if self.blocked else 0)

    def evidence(self):
        if not self.blocked and self.count >= self.min_exposures and self.hours + 1e-9 >= self.min_hours:
            return ("deep", self.start, f"R-I1: {self.count} clean exposures / {self.hours:.2f} h below q={self.threshold}")
        return None

    def on_report_result(self, correct):
        if correct:
            self.reset()
        else:
            self.blocked = True
