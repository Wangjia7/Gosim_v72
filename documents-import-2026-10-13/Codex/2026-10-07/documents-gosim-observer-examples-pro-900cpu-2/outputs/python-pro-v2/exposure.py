"""Bounded breakpoint search; integer seconds on both sides of each transition."""
import math


def duration_candidates(lower, upper, thresholds, factor_at, endpoints):
    if upper < lower:
        return set()
    points = {int(lower), int(math.floor(upper))}

    def add(value):
        for t in (math.floor(value) - 1, math.floor(value), math.ceil(value), math.ceil(value) + 1):
            if lower <= t <= upper:
                points.add(int(t))

    for value in endpoints:
        add(value)
    # Subintervals allow rising then setting curves; every bracket is refined independently.
    xs = [lower + (upper - lower) * k / 12 for k in range(13)]
    ys = [factor_at(x) for x in xs]
    for threshold in thresholds:
        for a, b, ya, yb in zip(xs, xs[1:], ys, ys[1:]):
            if ya == threshold:
                add(a)
            if yb == threshold:
                add(b)
            if (ya - threshold) * (yb - threshold) >= 0:
                continue
            for _ in range(20):
                mid = (a + b) / 2
                ym = factor_at(mid)
                if (ya - threshold) * (ym - threshold) <= 0:
                    b = mid
                else:
                    a, ya = mid, ym
            add((a + b) / 2)
    return points
