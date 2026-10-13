"""Causal weather estimates from released messages and the agent's own results.

Quality means the atmospheric band scale (transparency * sky / seeing), NOT
transparency or instrument efficiency. Unknown availability remains unlabelled.
"""
from __future__ import annotations
import math
from collections import Counter
from skymath import parse_utc

WEATHER = {'rain', 'storm', 'overcast', 'haze'}

def kinds(notices):
    return frozenset(n.get('event_kind') for n in notices
                     if n.get('direction') == 'ALL' and n.get('event_kind') in WEATHER)

def prior(key):
    if key & {'rain', 'storm'}:
        # Rain already reduces availability. Do not penalise its closed fraction
        # a second time in quality conditioned on an OPEN exposure.
        return (0.6, .55 if key & {'overcast', 'haze'} else .7)
    if key & {'overcast', 'haze'}:
        return 0.95, .55
    return 0.85, .7

class WeatherModel:
    def __init__(self, nights):
        self.nights = nights
        self.forecast = None
        self.stats = {}
        self.seen_open = set()
        self.seen_quality = set()
        self.revision = 0
        self.labels = {}
        self.night_keys = {}
        self.finalised = set()

    def start_night(self, night_index, now):
        self.night_keys.setdefault(night_index, self.key_for(self.nights[night_index], now))

    def _finalise(self, now):
        for ni,key in self.night_keys.items():
            if ni in self.finalised or parse_utc(self.nights[ni]['observing_end_utc'])>now:
                continue
            self.finalised.add(ni)
            if key is None:
                continue
            labels=self.labels.get(ni,{})
            opened=sum(w for state,w in labels.values() if state)
            closed=sum(w for state,w in labels.values() if not state)
            lower,upper=min(1.,opened),max(0.,1-closed)
            if lower>upper:continue
            cell=self._cell(key)
            mean=cell[0]/(cell[0]+cell[1])
            # Selection is not random: closed bulletins are observed more readily
            # than open sky. A partly labelled night only supplies censored bounds.
            # Unknown fractions never become fabricated open/closed samples.
            if lower<=mean<=upper and upper-lower>.05:
                continue
            estimate=min(upper,max(lower,mean))
            evidence=min(1.,opened+closed) * (1. if upper-lower<=.05 else .25)
            cell[0]+=evidence*estimate;cell[1]+=evidence*(1-estimate);cell[4]+=evidence

    def _cell(self, key):
        if key not in self.stats:
            opening, q = prior(key)
            self.stats[key] = [4 * opening, 4 * (1 - opening), 4 * q, 4.0, 0.0]
        return self.stats[key]

    def on_forecast(self, message, now):
        issued = parse_utc(message['issued_at_utc'])
        if issued > now:
            return False
        if self.forecast and issued <= parse_utc(self.forecast['issued_at_utc']):
            return False
        self.forecast = message
        self.revision += 1
        return True

    def key_for(self, night, now):
        fc = self.forecast
        if fc is None:
            return None
        start, end = parse_utc(fc['coverage_start_utc']), parse_utc(fc['coverage_end_utc'])
        ns = parse_utc(night['observing_start_utc'])
        if now >= end or not start <= ns < end:
            return None
        return kinds(n for n in fc.get('notices', []) if night['night_date'] in n.get('nights', []))

    def observe_open(self, night_index, slot, state, notices, seconds=900):
        if state is None or not 0 <= night_index < len(self.nights):
            return
        token = (night_index, slot)
        if token in self.seen_open:
            return
        self.seen_open.add(token)
        night = self.nights[night_index]
        span = (parse_utc(night['observing_end_utc']) - parse_utc(night['observing_start_utc'])).total_seconds()
        weight = min(1.0, max(0.0, seconds / max(1, span)))
        self.start_night(night_index, parse_utc(night['observing_start_utc']))
        self.labels.setdefault(night_index,{})[slot]=(bool(state),weight)

    def observe_quality(self, night_index, slot, lo, hi, notices):
        token = (night_index, slot)
        if token in self.seen_quality or not all(math.isfinite(x) for x in (lo, hi)):
            return
        if lo <= 0 or hi <= lo or hi - lo > 0.6:
            return                         # an uninformative interval is not a measured scalar
        self.seen_quality.add(token)
        night = self.nights[night_index]
        key = self.key_for(night, parse_utc(night['observing_start_utc']))
        cell = self._cell(kinds(notices) if key is None else key)
        mean = cell[2] / cell[3]
        sample = min(hi, max(lo, mean))
        cell[2] += sample / 32.0             # at most one effective night of 15-min samples
        cell[3] += 1 / 32.0

    def predict(self, now):
        self._finalise(now)
        observed = sum(c[4] for c in self.stats.values())
        classes=Counter(self.night_keys[i] for i in self.finalised)
        climate_open=(3.4+sum(n*(self._cell(k)[0]/sum(self._cell(k)[:2]) if k is not None else .85)
                             for k,n in classes.items()))/(4+sum(classes.values()))
        q_weight = sum(c[3] - 4 for c in self.stats.values())
        climate_q = (4 * .7 + sum(c[2] - 4 * prior(k)[1] for k, c in self.stats.items())) / (4 + q_weight)
        out = []
        for night in self.nights:
            key = self.key_for(night, now)
            if key is None:
                opening, q, evidence = climate_open, climate_q, observed
            else:
                cell = self._cell(key)
                opening, q, evidence = cell[0] / (cell[0] + cell[1]), cell[2] / cell[3], cell[4]
            out.append((min(.999, max(.05, opening)), min(2.0, max(.05, q)), evidence))
        return out

    def summary(self):
        return {'revision': self.revision, 'labelled_slots': len(self.seen_open),
                'quality_slots': len(self.seen_quality), 'groups': len(self.stats),
                'finalised_nights':len(self.finalised)}

def quality_interval(program, hits, pending, weights, multipliers, mismatch, bands):
    """Use identifiable saturated program outcomes; never reinterpret eff bounds as weather."""
    lo, hi = 0.0, math.inf
    declared = multipliers[program]
    for hit in hits:
        tid = hit['target_id']
        p = pending.get(tid)
        if p is None or not p['dir_clean'] or p['model'] <= 0:
            continue
        value = float(hit['score']) / weights[tid]
        m = p['model']
        if abs(value - declared) < 2e-4:
            lower = bands['DARK'] if program == 'DARK' else bands['BRIGHT'] if program == 'BRIGHT' else 0.0
            upper = math.inf if program == 'DARK' else bands['DARK'] if program == 'BRIGHT' else bands['BRIGHT']
            lo, hi = max(lo, lower / m), min(hi, upper / m)
        elif abs(value - mismatch) < 2e-4:
            # A score equal to mismatch may also be a partially exposed matched target.
            # Do not turn this ambiguity into a weather measurement.
            continue
    return lo, hi
