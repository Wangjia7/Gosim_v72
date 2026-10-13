"""Season-level shadow prices of sky regions: where will telescope time be scarce?

The planner values one exposure at a time. On its own it spends the first weeks of a season on regions that
stay visible for months, and the regions that set early end up starved: on the dev cards the regions with
the shortest windows finished at 50-60% of their science while the rest reached 80-85%.

Here the catalogue is cut into sky regions (RA x Dec boxes) and the rest of the season into time slots (a
block of nights x one hour of local sidereal time). Each slot's telescope time is shared among the regions up
in it in proportion to demand x price; a region's price rises while its share of the remaining season falls
short of its demand and falls while the share exceeds it (multiplicative steps, warm-started every night).
The planner multiplies a target's gain by (price of its region / demand-weighted mean price) ** SEASON_GAMMA.

Demand of a region (telescope seconds) = sum over its unfinished targets of (1 - factor) x the exposure that
saturates the target under a typical sky, divided by the targets one field holds there (fibres x (1 -
exp(-open targets per glass))). Supply = a slot's night seconds x sin(alt) ** airmass exponent of the region
centre (time at a poor airmass buys less). Geometry and the public night list only. Standard library only.
"""
from __future__ import annotations

import math
import os
from datetime import timedelta

from skymath import SIDEREAL_DEG_PER_SECOND, local_sidereal_deg, Moon


def _env(name: str, default):
    return type(default)(os.environ.get(f"V5_{name}", default))


RA_STEP = _env("SEASON_RA_STEP", 15.0)       # region size (deg)
DEC_STEP = _env("SEASON_DEC_STEP", 10.0)
BLOCK_NIGHTS = int(_env("SEASON_BLOCK", 4))   # nights per time slot block (the sky drifts ~1 deg a night)
ITERS_FIRST = 40
ITERS = int(_env("SEASON_ITERS", 8))          # price steps per night after the first
STEP_POWER = 0.5
P_MIN, P_MAX = 0.05, 20.0                     # relative to the demand-weighted geometric mean
SUPPLY_SHARE = _env("SEASON_SUPPLY", 0.7)     # share of night time that becomes useful exposure (weather, losses)
MULT_MIN = _env("SEASON_MULT_MIN", 0.5)
MULT_MAX = _env("SEASON_MULT_MAX", 2.5)
DONE = 0.95


class SeasonPrices:
    def __init__(self, ra, dec, flux, nights, lon, lat, min_alt, n_fibres, glass_deg, t_need, airmass_exponent):
        self.n_fibres = n_fibres
        self.glass_area = glass_deg * glass_deg
        self.t_need = t_need                       # per target: exposure that saturates it under a typical sky
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
        n = len(members)
        sin_lat, cos_lat = math.sin(math.radians(lat)), math.cos(math.radians(lat))
        sin_lim = math.sin(math.radians(min_alt + 3.0))
        centre = []
        self.area = []
        for mem in members:
            c_ra = sum(ra[i] for i in mem) / len(mem)
            c_dec = sum(dec[i] for i in mem) / len(mem)
            centre.append((c_ra, c_dec))
            self.area.append(RA_STEP * max(0.05, math.cos(math.radians(c_dec))) * DEC_STEP)
        # slots: (block, LST hour) -> night seconds; then the regions up in each slot with their quality weight
        slot_seconds: dict = {}
        for k, (start, end) in enumerate(nights):
            span = (end - start).total_seconds()
            l0 = local_sidereal_deg(start, lon)
            t = 0.0
            while t < span:
                lst = (l0 + (t + 1800.0) * SIDEREAL_DEG_PER_SECOND) % 360.0
                key = (k // BLOCK_NIGHTS, int(lst // 15.0))
                slot_seconds[key] = slot_seconds.get(key, 0.0) + min(3600.0, span - t)
                t += 3600.0
        self.slots = []                            # (block, seconds, [(region, weight)])
        for (block, hour), seconds in sorted(slot_seconds.items()):
            lst = hour * 15.0 + 7.5
            pairs = []
            for r, (c_ra, c_dec) in enumerate(centre):
                sd, cd = math.sin(math.radians(c_dec)), math.cos(math.radians(c_dec))
                sin_alt = sin_lat * sd + cos_lat * cd * math.cos(math.radians(lst - c_ra))
                if sin_alt >= sin_lim:
                    pairs.append((r, sin_alt ** airmass_exponent))
            if pairs:
                self.slots.append((block, seconds * SUPPLY_SHARE, pairs))
        self.price = [1.0] * n
        self.mult = [1.0] * n
        self.demand = [0.0] * n
        self.updated = False

    def update(self, factor, night_index: int) -> None:
        """Re-price for the rest of the season from tonight on (factor: best estimated factor per target)."""
        block_now, done_share = divmod(night_index, BLOCK_NIGHTS)
        keep_now = 1.0 - done_share / BLOCK_NIGHTS
        demand = self.demand
        for r, mem in enumerate(self.members):
            need = 0.0
            open_n = 0
            for i in mem:
                f = factor[i]
                if f < DONE:
                    need += (1.0 - f) * self.t_need[i]
                    open_n += 1
            per_field = self.n_fibres * (1.0 - math.exp(-open_n * self.glass_area / self.area[r]))
            demand[r] = need / per_field if per_field > 1e-9 else 0.0
        slots = [(seconds * (keep_now if block == block_now else 1.0), pairs)
                 for block, seconds, pairs in self.slots if block >= block_now]
        price = self.price
        for _ in range(ITERS if self.updated else ITERS_FIRST):
            supply = [0.0] * len(price)
            for seconds, pairs in slots:
                total = 0.0
                for r, w in pairs:
                    total += demand[r] * price[r] * w
                if total <= 0.0:
                    continue
                scale = seconds / total
                for r, w in pairs:
                    supply[r] += demand[r] * price[r] * w * w * scale
            for r, d in enumerate(demand):
                if d > 0.0:
                    price[r] *= (d / max(supply[r], 1e-9)) ** STEP_POWER
            # only relative prices share a slot: keep the demand-weighted geometric mean at 1
            weight = sum(demand)
            if weight <= 0.0:
                break
            mean_log = sum(d * math.log(price[r]) for r, d in enumerate(demand) if d > 0.0) / weight
            for r in range(len(price)):
                p = price[r] / math.exp(mean_log)
                price[r] = P_MIN if p < P_MIN else (P_MAX if p > P_MAX else p)
        self.updated = True
        self.mult = [1.0 if demand[r] <= 0.0 else min(MULT_MAX, max(MULT_MIN, price[r])) for r in range(len(price))]
        self.ratio = sum(demand) / max(1e-9, sum(seconds for seconds, _ in slots))

    def summary(self, top: int = 6) -> str:
        ranked = sorted((r for r in range(len(self.price)) if self.demand[r] > 0.0), key=lambda r: -self.mult[r])
        return " ".join(f"{self.mult[r]:.2f}" for r in ranked[:top]) + " .. " + " ".join(f"{self.mult[r]:.2f}" for r in ranked[-3:])


# --- option prices: is now the best remaining time to observe a region? ------------------------------------
#
# SeasonPrices above balances each region's demand against its share of the season. Near the end of a
# region's window its supply goes to zero while its demand stays, the price hits the cap and the planner chases
# low, setting targets at a poor airmass (card b: November time moved from RA 0-30 to RA 300-330 low in the
# west, about -1000 science). Here time itself has the price: every slot (block of nights x LST hour) gets a
# price per telescope second from an auction in which the unfinished targets of each region, grouped by
# efficiency (science per telescope second), buy the slots that pay them best; a group that no slot pays drops
# out, so sparse or faint regions do not drive prices. A region's multiplier now is
#     min(1, (w_now / price_now) / (HEDGE x max over later blocks of w / price))
# with w = sin(alt) ** airmass exponent: 1 when tonight is as good as anything later, lower when a later block
# of nights will observe the region at a better airmass or in less crowded hours. Never above 1, so a region at
# the end of its window keeps its plain value. Standard library only.

OPT_CLASSES = int(_env("OPTION_CLASSES", 4))     # efficiency groups per region
OPT_ITERS_FIRST = 30
OPT_ITERS = int(_env("OPTION_ITERS", 6))          # auction steps per re-pricing after the first
OPT_BETA = _env("OPTION_BETA", 12.0)              # softness of a group's choice among slots (on its surplus share)
OPT_STEP = 0.5
OPT_HEDGE = _env("OPTION_HEDGE", 0.9)             # later nights may be cloudy: their value counts this much
OPT_REPRICE = int(_env("OPTION_REPRICE", 2))      # re-price every this many nights


class OptionPrices:
    def __init__(self, ra, dec, flux, nights, lon, lat, min_alt, n_fibres, glass_deg, t_need, airmass_exponent, value,
                 night_factors=None, lunar_model=None, quality_ref=.7, desi_design=False):
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
        self.v6_weather = night_factors is not None
        self.desi_design = desi_design
        self.design_ha = [None] * len(members)
        self.quality_ref = quality_ref
        self.v6_enabled = self.v6_weather or lunar_model is not None or desi_design
        self.pieces = []
        slot_seconds: dict = {}
        for k, (start, end) in enumerate(nights):
            span = (end - start).total_seconds()
            l0 = local_sidereal_deg(start, lon)
            t = 0.0
            while t < span:
                lst = (l0 + (t + 1800.0) * SIDEREAL_DEG_PER_SECOND) % 360.0
                key = (k // BLOCK_NIGHTS, int(lst // 15.0))
                slot_seconds[key] = slot_seconds.get(key, 0.0) + min(3600.0, span - t)
                if self.v6_enabled:
                    seconds = min(3600.0, span - t)
                    a, b = start + timedelta(seconds=t), start + timedelta(seconds=t + seconds)
                    moment = a + (b - a) / 2
                    actual_lst = local_sidereal_deg(moment, lon)
                    moon = Moon(moment, actual_lst, lat, lunar_model) if lunar_model is not None else None
                    weights = []
                    for r, (r_ra, sd, cd) in enumerate(self.centre):
                        w = self.weight(r, actual_lst if desi_design else key[1] * 15.0 + 7.5)
                        if w > 0:
                            if moon is not None:
                                w *= moon.lunar_factor(r_ra, math.degrees(math.atan2(sd, cd)))
                            weights.append((r, w))
                    self.pieces.append((key, k, a, b, weights))
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
        if self.v6_enabled:
            self.configure_slots(night_factors, nights[0][0])

    def configure_slots(self, predictions, now):
        """Rebuild live aggregated slots from cached PUBLIC ephemerides and causal estimates."""
        seconds = [0.0] * len(self.slot_block)
        hedge = [0.0] * len(self.slot_block)
        weights = [{} for _ in self.slot_block]
        for key, k, a, b, ws in self.pieces:
            duration = (b - max(a, now)).total_seconds() if self.v6_weather or self.desi_design else (b - a).total_seconds()
            if duration <= 0:
                continue
            opening, quality = predictions[k][:2] if self.v6_weather else (1.0, 1.0)
            if self.v6_weather:
                quality /= self.quality_ref
            s = self.slot_index[key]
            live = duration * opening
            seconds[s] += live
            evidence = predictions[k][2] if self.v6_weather else 0.0
            hedge[s] += live * (OPT_HEDGE + (1-OPT_HEDGE)*evidence/(evidence+4))
            for r, w in ws:
                weights[s][r] = weights[s].get(r, 0.0) + live * quality * w
        if self.v6_weather:
            # Preserve the old 0.7 supply at the weak climate prior open=0.85.
            self.slot_supply = [t * SUPPLY_SHARE / .85 for t in seconds]
        elif self.desi_design:
            self.slot_supply = [t * SUPPLY_SHARE for t in seconds]
        self.region_slots = [[] for _ in self.members]
        self.slot_hedge = [h/t if t>0 else OPT_HEDGE for h,t in zip(hedge,seconds)]
        self.slot_region_weight = [{} for _ in self.slot_block]
        for s, regions in enumerate(weights):
            for r, w in regions.items():
                if seconds[s] > 0 and w > 0:
                    self.region_slots[r].append((s, w / seconds[s]))
                    self.slot_region_weight[s][r] = w / seconds[s]

    def weight(self, r: int, lst: float) -> float:
        c_ra, sd, cd = self.centre[r]
        sin_alt = self.sin_lat * sd + self.cos_lat * cd * math.cos(math.radians(lst - c_ra))
        return sin_alt ** self.weight_exp if sin_alt >= self.sin_lim else 0.0

    def update(self, factor, night_index: int, force=False) -> None:
        """Re-price the slots from tonight on (factor: best estimated factor per target)."""
        if not force and self.price is not None and night_index - self.night < OPT_REPRICE:
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
            # This competition keeps the best exposure, not accumulated integration.
            # A replacement still costs a full exposure; its marginal value falls with progress.
            items = sorted((((self.value[i] * (1.0-factor[i]) if self.desi_design else self.value[i]) * per_field / self.t_need[i],
                             (1.0 if self.desi_design else 1.0-factor[i]) * self.t_need[i] / per_field)
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
                supply[s] = self.slot_supply[s] * (1.0 if self.v6_weather or self.desi_design else (keep_now if b == block_now else 1.0))
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
                    if self.v6_weather:
                        v *= self.slot_hedge[s] / max(1e-12, OPT_HEDGE)
                    if v > best:
                        best = v
            self.best_later[r] = best * OPT_HEDGE
        total_need = sum(c for _, _, c in units)
        self.ratio = total_need / max(1e-9, sum(supply))
        if self.desi_design:
            # DESI-inspired: the existing auction balances LST demand/supply;
            # take its best remaining priced hour as a soft design hour angle.
            # ponytail: region/hour discretization; refine only if four-card gains justify finer slots.
            for r, slots in enumerate(live):
                s = max(slots, key=lambda sw:(sw[1]/price[sw[0]], -sw[0]), default=None)
                self.design_ha[r] = ((self.slot_hour[s[0]]*15+7.5-self.centre[r][0]+180)%360-180) if s else None

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
                current_weight = sin_alt ** self.weight_exp
                if self.v6_enabled:
                    slot_weight = self.slot_region_weight[s].get(r, 0.0)
                    base_weight = self.weight(r, self.slot_hour[s] * 15.0 + 7.5)
                    current_weight *= slot_weight / base_weight if base_weight > 0 else 0.0
                ratio.append(current_weight / self.price[s] / later)
        top = min(1.0, max((x for x in ratio if x is not None), default=1.0))
        return [1.0 if x is None or x >= top else max(MULT_MIN, x / max(1e-12, top)) for x in ratio]

    def summary(self) -> str:
        ordered = sorted(self.price[s] for s in range(len(self.price)) if self.slot_block[s] >= self.block_now)
        if not ordered:
            return "-"
        q = lambda f: ordered[min(len(ordered) - 1, int(f * len(ordered)))]
        return f"slot price q10 {q(0.1):.3g} q50 {q(0.5):.3g} q90 {q(0.9):.3g}, groups {self.units}"
