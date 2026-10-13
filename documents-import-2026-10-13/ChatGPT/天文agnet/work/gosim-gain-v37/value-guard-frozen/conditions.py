"""Identifiable sky constraints and an independent, epoch-local health watch."""
from collections import deque
from statistics import median


def sky_interval(observations, bands):
    lo, hi, count = 0., float('inf'), 0
    for _, model, program, matched, clean in observations:
        # A score at the mismatch multiplier can be an unsaturated match.
        if not clean or not matched or model <= 0:
            continue
        count += 1
        a, b = {'DARK': (bands['DARK'], float('inf')),
                'BRIGHT': (bands['BRIGHT'], bands['DARK']),
                'BACKUP': (0., bands['BRIGHT'])}[program]
        lo, hi = max(lo, a/model), min(hi, b/model)
    status = 'inconsistent' if lo >= hi else 'identified' if count >= 4 and lo > 0 else 'inconclusive'
    return {'status': status, 'sky_bounds': (lo, hi), 'samples': count}


class HealthWatch:
    def __init__(self, planner):
        self.p = planner
        self.rows = deque(maxlen=32)
        self.healthy = deque(maxlen=32)
        self.seen = set()
        self.epoch = 0
        self.state = 'unknown'
        self.last_probe = -1e30
        self.last_report = -1e30
        self.blocked_until = -1e30
        self.recovery_pending = False
        self.zero_run = 0

    def observe(self, result, now, notices):
        p = self.p
        if not result or result.get('action') != 'observe' or not p.pending:
            return
        index = result.get('observe_index')
        if index in self.seen:
            return
        self.seen.add(index)
        confounded = any(k == 'earthquake' or (d == 'ALL' and k in
            {'rain','storm','overcast','haze','cold_snap'}) for k, d in notices)
        hits = {h['target_id']: h['score'] for h in result.get('hits', [])}
        intervals = [];saturation_lowers=[]
        for target, prediction in p.pending.items():
            score = hits.get(target)
            if score is None or not prediction.get('dir_clean', False):
                continue
            i = p.index_of[target]
            public = p.flux[i]*p.pending_duration*prediction.get('model', 0.)/p.f0t0
            declared = p.multipliers[p.pending_program]
            if public <= 0:continue
            if score/p.weight[i] >= min(declared,p.mismatch)-2e-4:
                saturation_lowers.append(score/(p.weight[i]*max(declared,p.mismatch))/public)
                continue  # a one-sided bound, never an exact ratio
            intervals.append((score/(p.weight[i]*max(declared,p.mismatch))/public,
                              score/(p.weight[i]*min(declared,p.mismatch))/public))
        all_zero = bool(hits) and all(s == 0 for s in hits.values())
        self.zero_run = self.zero_run+1 if all_zero else 0
        bounds = (median(a for a,b in intervals),median(b for a,b in intervals)) if intervals else None
        row = {'id': index, 'utc': now.timestamp(), 'epoch': self.epoch,
               'bounds': bounds, 'zero': all_zero, 'confounded': confounded,
               'samples': len(intervals)}
        self.rows.append(row)
        if confounded:
            self.state = 'weather_confounded'
            return
        if all_zero:
            self.state = 'unavailable_candidate'
            return
        if saturation_lowers and max(saturation_lowers)>=.1 and (bounds is None or bounds[1]>=.1):
            self.healthy.append(max(saturation_lowers))
            self.state='normal';self.recovery_pending=False
            return
        recent = [r for r in list(self.rows)[-3:] if not r['confounded'] and r['bounds'] and r['samples'] >= 1]
        reference = median(self.healthy) if self.healthy else None
        # Absolute depth only requests diagnosis. A frozen independent reference
        # or operator engineering event is needed to authorize a fault probe.
        low = bounds and (bounds[1] < .025 or (reference and bounds[1] < .2*reference))
        if low:
            self.state = 'throughput_candidate' if len(recent) >= 3 else 'gather_evidence'
        elif bounds and bounds[0] >= .1:
            self.healthy.append(bounds[0])
            self.state = 'normal'
            self.recovery_pending = False
        else:
            self.state = 'inconclusive'

    def diagnostic_due(self, stamp):
        # Keep repair validation pending until a non-confounded exposure. An
        # extended weather/earthquake episode must not force repeated probes.
        if self.state=='weather_confounded':return False
        return (self.recovery_pending or self.state in {'throughput_candidate','gather_evidence','unavailable_candidate'}) and stamp-self.last_probe >= 900

    def report_due(self, stamp, free_left):
        if stamp < self.blocked_until or stamp-self.last_report < 7200:
            return False
        recent = [r for r in self.rows if r['epoch'] == self.epoch and not r['confounded'] and
                  r['bounds'] and r['samples'] >= 1 and stamp-r['utc'] <= 7200][-3:]
        reference = median(self.healthy) if self.healthy else None
        return (free_left > 0 and reference is not None and len(recent) == 3 and
                all(r['bounds'][1] < .15*reference for r in recent) and
                all(not r['zero'] for r in recent))

    def report_result(self, result, stamp):
        self.last_report = stamp
        if result.get('correct') and result.get('repaired'):
            self.epoch += 1
            self.rows.clear();self.healthy.clear();self.zero_run = 0
            self.state = 'repaired_pending_validation';self.recovery_pending = True
        else:
            self.blocked_until = stamp+86400

    def resync(self, messages):
        for m in messages:
            if m.get('record_type') == 'state_resync':
                w=m.get('invalidated_window',{})
                a,b=w.get('action_index_start',0),w.get('action_index_end_exclusive',0)
                self.rows=deque((r for r in self.rows if isinstance(r['id'],int) and not a<=r['id']<b),maxlen=32)
                self.healthy.clear();self.state='inconclusive';self.zero_run=0

    def summary(self):
        return {'state':self.state,'epoch':self.epoch,'zero_run':self.zero_run,
                'healthy_reference':median(self.healthy) if self.healthy else None,
                'recent':list(self.rows)[-6:], 'recovery_pending':self.recovery_pending,
                'scope':'own unsaturated score bounds; low throughput alone is not a fault certificate'}
