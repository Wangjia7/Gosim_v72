"""Coarse future slot opportunity prices, adapted from the supplied participant project.
A planning heuristic from public geometry only; not a completion certificate.
Best-single-exposure scoring requires a full new exposure when upgrading a target.
"""
from __future__ import annotations
import math
import os
from .skymath import SIDEREAL_DEG_PER_SECOND, local_sidereal_deg

def _env(name, default):
    return type(default)(os.environ.get("FUSION_" + name, default))

RA_STEP=15.0
DEC_STEP=10.0
BLOCK_NIGHTS=4
SUPPLY_SHARE=.7
MULT_MIN=.5
DONE=.95
OPT_CLASSES = int(_env("OPTION_CLASSES", 4))     # efficiency groups per region
OPT_ITERS_FIRST = 30
OPT_ITERS = int(_env("OPTION_ITERS", 6))          # auction steps per re-pricing after the first
OPT_BETA = _env("OPTION_BETA", 12.0)              # softness of a group's choice among slots (on its surplus share)
OPT_STEP = 0.5
OPT_HEDGE = _env("OPTION_HEDGE", 0.9)             # later nights may be cloudy: their value counts this much
OPT_REPRICE = int(_env("OPTION_REPRICE", 2))      # re-price every this many nights


class OptionPrices:
    def __init__(self, ra, dec, flux, nights, lon, lat, min_alt, n_fibres, glass_deg, t_need, airmass_exponent, value):
        self.value = value                         # per target: full science value (weight x best program)
        self.n_fibres = n_fibres
        self.glass_area = glass_deg * glass_deg
        self.t_need = t_need
        self.lon = lon
        self.weight_exp = airmass_exponent
        keys = {}
        self.region_of = []
        members: list = []
        for i, (r, d) in enumerate(zip(ra, dec)):
            key = (int(r // RA_STEP), int((d + 90.0) // DEC_STEP))
            k = keys.get(key)
            if k is None:
                k = keys[key] = len(members)
                members.append([])
            members[k].append(i)
            self.region_of.append(k)
        self.members = members
        self.sin_lat, self.cos_lat = math.sin(math.radians(lat)), math.cos(math.radians(lat))
        self.sin_lim = math.sin(math.radians(min_alt + 3.0))
        self.centre = []
        self.area = []
        for mem in members:
            c_ra = sum(ra[i] for i in mem) / len(mem)
            c_dec = sum(dec[i] for i in mem) / len(mem)
            self.centre.append((c_ra, math.sin(math.radians(c_dec)), math.cos(math.radians(c_dec))))
            self.area.append(RA_STEP * max(0.05, math.cos(math.radians(c_dec))) * DEC_STEP)
        slot_seconds: dict = {}
        for k, (start, end) in enumerate(nights):
            span = (end - start).total_seconds()
            l0 = local_sidereal_deg(start, lon)
            t = 0.0
            while t < span:
                lst = (l0 + (t + min(3600.0, span - t) / 2.0) * SIDEREAL_DEG_PER_SECOND) % 360.0
                key = (k // BLOCK_NIGHTS, int(lst // 15.0))
                slot_seconds[key] = slot_seconds.get(key, 0.0) + min(3600.0, span - t)
                t += 3600.0
        self.slot_block = []
        self.slot_hour = []
        self.slot_supply = []
        self.slot_index = {}
        self.region_slots = [[] for _ in members]   # per region: (slot, w) for the slots it is up in
        for (block, hour), seconds in sorted(slot_seconds.items()):
            s = len(self.slot_block)
            self.slot_index[(block, hour)] = s
            self.slot_block.append(block)
            self.slot_hour.append(hour)
            self.slot_supply.append(seconds * SUPPLY_SHARE)
            for r in range(len(members)):
                w = self.weight(r, hour * 15.0 + 7.5)
                if w > 0.0:
                    self.region_slots[r].append((s, w))
        self.price = None
        self.best_later = [0.0] * len(members)
        self.block_now = -1
        self.night = -1
        self.ratio = 0.0
        self.units = 0

    def weight(self, r: int, lst: float) -> float:
        c_ra, sd, cd = self.centre[r]
        sin_alt = self.sin_lat * sd + self.cos_lat * cd * math.cos(math.radians(lst - c_ra))
        return sin_alt ** self.weight_exp if sin_alt >= self.sin_lim else 0.0

    def update(self, factor, night_index: int) -> None:
        """Re-price the slots from tonight on (factor: best estimated factor per target)."""
        if self.price is not None and night_index - self.night < OPT_REPRICE:
            return
        self.night = night_index
        block_now, done_share = divmod(night_index, BLOCK_NIGHTS)
        self.block_now = block_now
        keep_now = 1.0 - done_share / BLOCK_NIGHTS
        # groups: (region, efficiency, telescope seconds still needed at w = 1)
        units = []
        for r, mem in enumerate(self.members):
            open_ = [i for i in mem if factor[i] < DONE]
            if not open_:
                continue
            per_field = self.n_fibres * (1.0 - math.exp(-len(open_) * self.glass_area / self.area[r]))
            if per_field <= 1e-9:
                continue
            # efficiency of a target = 1.2 x weight per telescope second (the share of a field it takes)
            items = sorted(((self.value[i] * max(0.0, 1.0 - factor[i]) * per_field / self.t_need[i], self.t_need[i] / per_field)
                            for i in open_), reverse=True)
            size = max(1, -(-len(items) // OPT_CLASSES))
            for k in range(0, len(items), size):
                chunk = items[k:k + size]
                cost = sum(c for _, c in chunk)
                if cost > 0.0:
                    units.append((r, sum(e * c for e, c in chunk) / cost, cost))
        self.units = len(units)
        n_slots = len(self.slot_block)
        supply = [0.0] * n_slots
        for s in range(n_slots):
            b = self.slot_block[s]
            if b >= block_now:
                supply[s] = self.slot_supply[s] * (keep_now if b == block_now else 1.0)
        live = [[(s, w) for s, w in self.region_slots[r] if supply[s] > 0.0] for r in range(len(self.members))]
        iters = OPT_ITERS
        if self.price is None:
            ordered = sorted(e for _, e, _ in units)
            start = 0.5 * ordered[len(ordered) // 2] if ordered else 1.0
            self.price = [start] * n_slots
            iters = OPT_ITERS_FIRST
        price = self.price
        floor = 1e-6 * max([e for _, e, _ in units] or [1.0])
        exp = math.exp
        for _ in range(iters):
            demand = [0.0] * n_slots
            for r, e, cost in units:
                slots = live[r]
                if not slots:
                    continue
                inv_e = 1.0 / e
                # surplus share of slot s: 1 - price x seconds needed (cost / w) / value = 1 - price / (e w)
                gains = [(s, w, 1.0 - price[s] * inv_e / w) for s, w in slots]
                g_max = max(g for _, _, g in gains)
                if g_max <= 0.0:
                    continue                      # no slot pays this group: it drops out
                share = min(1.0, g_max / 0.05)
                ws = [(s, w, exp(OPT_BETA * (g - g_max))) for s, w, g in gains if g > 0.0]
                total = sum(x for _, _, x in ws)
                scale = share * cost / total
                for s, w, x in ws:
                    demand[s] += x * scale / w
            for s in range(n_slots):
                if supply[s] > 0.0:
                    step = (max(demand[s], 1e-9) / supply[s]) ** OPT_STEP
                    p = price[s] * (0.5 if step < 0.5 else (2.0 if step > 2.0 else step))
                    price[s] = floor if p < floor else p
        # the best later value of each region (blocks after this one)
        for r, slots in enumerate(live):
            best = 0.0
            for s, w in slots:
                if self.slot_block[s] > block_now:
                    v = w / price[s]
                    if v > best:
                        best = v
            self.best_later[r] = best * OPT_HEDGE
        total_need = sum(c for _, _, c in units)
        self.ratio = total_need / max(1e-9, sum(supply))

    def mult_now(self, lst: float):
        """Per region: value of observing it now relative to its best later block, scaled so the region up now
        with the best ratio gets 1 (a whole slot priced high or low is the time price's job, not this one)."""
        s = self.slot_index.get((self.block_now, int((lst % 360.0) // 15.0)))
        if s is None:
            return [1.0] * len(self.members)
        ratio = []
        for r in range(len(self.members)):
            later = self.best_later[r]
            c_ra, sd, cd = self.centre[r]
            sin_alt = self.sin_lat * sd + self.cos_lat * cd * math.cos(math.radians(lst - c_ra))
            if sin_alt <= 0.0:
                ratio.append(None)                # below the horizon: none of its targets is up
            elif later <= 0.0:
                ratio.append(math.inf)            # no later chance: now is the best
            else:
                ratio.append(sin_alt ** self.weight_exp / self.price[s] / later)
        top = min(1.0, max((x for x in ratio if x is not None), default=1.0))
        return [1.0 if x is None or x >= top else max(MULT_MIN, x / top) for x in ratio]

    def invalidate(self):
        self.price = None
        self.night = -1

    def summary(self) -> str:
        ordered = sorted(self.price[s] for s in range(len(self.price)) if self.slot_block[s] >= self.block_now)
        if not ordered:
            return "-"
        q = lambda f: ordered[min(len(ordered) - 1, int(f * len(ordered)))]
        return f"slot price q10 {q(0.1):.3g} q50 {q(0.5):.3g} q90 {q(0.9):.3g}, groups {self.units}"
