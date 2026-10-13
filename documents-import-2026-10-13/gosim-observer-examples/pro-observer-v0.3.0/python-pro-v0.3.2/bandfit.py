"""Instrument efficiency bounds from the program-band outcome of one exposure.

The engine decides each target's program band from q_band = W x m (W: weather of the exposure, m: public sky
model of the target, airmass + Moon) without the instrument efficiency, and scores the quality q = eff x W x m.
All targets of an exposure share W and eff, so:
  * the unsaturated hits give R = q / m = eff x W (the same for every target), read with the multiplier of
    its band outcome (declared if matched, 1.0 if not);
  * matched targets form one run of the targets sorted by m (DARK: the top, BACKUP: the bottom, BRIGHT: a
    middle run), and the cut between matched and mismatched targets brackets W between band edges / m;
  * so eff = R / W lies in [R / W_hi, R / W_lo], with no assumption on the weather.
When the hits do not decide the cut, every consistent cut is kept and the bounds are their union.
"""
from __future__ import annotations

INF = float("inf")
EDGES = {"DARK": (0.65, INF), "BRIGHT": (0.40, 0.65), "BACKUP": (0.0, 0.40)}
MULT = {"DARK": 1.20, "BRIGHT": 1.12, "BACKUP": 1.06}
MISMATCH = 1.0
SPREAD = 0.03          # unsaturated hits of one exposure agree on R within this (they agree to ~1e-4 normally)


def configure(bands: dict, multipliers: dict, mismatch: float) -> None:
    """Use the card's band edges and multipliers (score config)."""
    dark, bright = float(bands["DARK"]), float(bands["BRIGHT"])
    EDGES.update({"DARK": (dark, INF), "BRIGHT": (bright, dark), "BACKUP": (0.0, bright)})
    MULT.update({k: float(v) for k, v in multipliers.items()})
    global MISMATCH
    MISMATCH = float(mismatch)


def exposure_bounds(program: str, hits):
    """(eff_lo, eff_hi, kind) or None.

    hits: [model, ratio_if_matched, saturated, multiplier_seen_if_saturated, direction_clean] per hit, where
    ratio_if_matched = score / (weight x declared multiplier) x f0T0 / (flux x T x model)."""
    a, b = EDGES[program]
    d = MULT[program] / MISMATCH
    tol = min(SPREAD, 0.3 * (d - 1.0))
    rows = sorted(hits, key=lambda h: h[0])
    n = len(rows)
    clean_unsat = sorted(h[1] for h in rows if not h[2] and h[4] and h[1] > 0)
    if not clean_unsat:
        return None
    mid = clean_unsat[len(clean_unsat) // 2]
    m = [h[0] for h in rows]
    need = [0] * n           # +1 must be matched, -1 must be mismatched, 0 free
    val = [0.0] * n          # ratio if matched (clean unsaturated hits only), else 0
    for k, h in enumerate(rows):
        if h[2]:
            if abs(h[3] - MULT[program]) < 2e-4:
                need[k] = 1
            elif abs(h[3] - MISMATCH) < 2e-4:
                # factor 1 at the mismatch multiplier, or an unsaturated match with factor = mismatch / declared
                if h[4] and abs(h[1] / mid - 1.0) < tol:
                    val[k] = h[1]
                else:
                    need[k] = -1
        elif h[4] and h[1] > 0:
            val[k] = h[1]
    # prefix counts of the constraints, prefix/suffix extremes of the mismatched reading (val x d)
    pos = [0] * (n + 1)
    neg = [0] * (n + 1)
    pre_lo, pre_hi = [INF] * (n + 1), [0.0] * (n + 1)
    for k in range(n):
        pos[k + 1] = pos[k] + (need[k] == 1)
        neg[k + 1] = neg[k] + (need[k] == -1)
        v = val[k] * d
        pre_lo[k + 1] = min(pre_lo[k], v) if v > 0 else pre_lo[k]
        pre_hi[k + 1] = max(pre_hi[k], v)
    suf_lo, suf_hi = [INF] * (n + 1), [0.0] * (n + 1)
    for k in range(n - 1, -1, -1):
        v = val[k] * d
        suf_lo[k] = min(suf_lo[k + 1], v) if v > 0 else suf_lo[k + 1]
        suf_hi[k] = max(suf_hi[k + 1], v)
    lo_all, hi_all = INF, 0.0
    found = False
    for i in (range(n + 1) if program != "BACKUP" else (0,)):
        if pos[i] > 0:
            break                                   # a hit below i must be matched
        run_lo, run_hi = INF, 0.0                   # extremes of val over the matched run [i, j)
        j_from = i if program != "DARK" else n
        if program == "DARK":
            for k in range(i, n):
                if val[k] > 0:
                    run_lo, run_hi = min(run_lo, val[k]), max(run_hi, val[k])
        for j in range(j_from, n + 1):
            if j > j_from:
                k = j - 1
                if val[k] > 0:
                    run_lo, run_hi = min(run_lo, val[k]), max(run_hi, val[k])
            if neg[j] - neg[i] > 0:
                break                               # a hit inside the run must be mismatched
            if pos[n] - pos[j] > 0:
                continue                            # a hit above j must be matched
            u_lo = min(run_lo, pre_lo[i], suf_lo[j])
            u_hi = max(run_hi, pre_hi[i], suf_hi[j])
            if u_hi <= 0 or u_hi > u_lo * (1.0 + tol):
                continue
            w_lo, w_hi = 0.0, INF
            if j > i:
                w_lo = a / m[i]
                if b < INF:
                    w_hi = b / m[j - 1]
            if i > 0:
                w_hi = min(w_hi, a / m[i - 1])
            if j < n and b < INF:
                w_lo = max(w_lo, b / m[j])
            if w_lo >= w_hi * 1.002:
                continue
            found = True
            lo_all = min(lo_all, u_lo / w_hi if w_hi < INF else 0.0)
            hi_all = max(hi_all, u_hi / w_lo if w_lo > 0 else INF)
    if not found:
        return None
    kind = "both" if lo_all > 0 and hi_all < INF else "upper" if hi_all < INF else "lower" if lo_all > 0 else "none"
    return lo_all, hi_all, kind
