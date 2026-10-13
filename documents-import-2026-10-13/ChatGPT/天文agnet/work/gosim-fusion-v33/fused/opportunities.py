"""Public geometry windows, independent of unknown weather and future requests."""
import bisect
from skymath import SIDEREAL_DEG_PER_SECOND as SPEED, local_sidereal_deg, wrap180


class Opportunities:
    def __init__(self, planner):
        self.p = planner
        self.starts = [(s.timestamp(), e.timestamp(), local_sidereal_deg(s, planner.lon))
                       for s, e in planner.nights]
        self.cache = {}

    def intervals(self, i):
        if i in self.cache:
            return self.cache[i]
        h = self.p.hmax[i]
        result = []
        if h > 0:
            for start, end, lst in self.starts:
                if h >= 180:
                    result.append((start, end))
                    continue
                ha = wrap180(lst - self.p.ra[i])
                for turn in (-360, 0, 360):
                    lo = max(start, start + (-h - ha + turn) / SPEED)
                    hi = min(end, self.p.survey_end.timestamp(), start + (h - ha + turn) / SPEED)
                    if hi - lo >= self.p.min_exposure:
                        result.append((lo, hi))
        result.sort()
        self.cache[i] = result
        return result

    def remaining(self, i, now, deadline=None, duration=None):
        """Total open seconds, number of usable windows, final legal exposure start.

        A window contributes only if one complete exposure of duration fits. Weather
        feasibility must be assessed separately; geometric opportunity is not a promise.
        """
        duration = self.p.min_exposure if duration is None else duration
        stop = self.p.survey_end.timestamp() if deadline is None else deadline
        intervals = self.intervals(i)
        first = bisect.bisect_left(intervals, (now, float('-inf')))
        total = count = 0
        last = None
        for lo, hi in intervals[max(0, first - 1):]:
            if lo > stop:
                break
            lo, hi = max(lo, now), min(hi, stop)
            if hi - lo >= duration:
                total += hi - lo
                count += 1
                last = hi - duration
        return total, count, last


def request_gain(legs, now, duration, raw, opportunities, i):
    total = 0.0
    for leg in legs:
        if now < leg['start'] or now + duration > leg['end']:
            continue
        threshold = leg['threshold']
        if raw < threshold:
            continue
        _, count, _ = opportunities.remaining(i, now, leg['end'], duration)
        # Deadline pressure is per request, never tied to an expired overlapping leg.
        # Single-exposure completion is uncertain under coarse weather feedback.
        # Reward confidence must rise past the threshold; a just-sufficient
        # prediction cannot receive the entire all-or-nothing bonus.
        confidence = min(1.0, max(0.0, (raw / max(1e-8, threshold) - 1.0) / .35))
        total += leg['value'] * confidence * (1.0 + 1.0 / max(1, count))
    return total
