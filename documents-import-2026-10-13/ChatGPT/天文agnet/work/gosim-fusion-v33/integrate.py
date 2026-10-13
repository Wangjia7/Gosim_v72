from pathlib import Path
import shutil
R=Path(__file__).resolve().parent
A=R/'agent'/'official_pro'
# The incoming option-price algorithm, isolated from its alternative market implementation.
s=(R/'incoming/season.py').read_text(); s=s[s.index('OPT_CLASSES ='):]
header='''"""Coarse future slot opportunity prices, adapted from the supplied participant project.
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
'''
s=s.replace('t + 1800.0','t + min(3600.0, span - t) / 2.0')
s=s.replace('(1.0 - factor[i]) * self.t_need[i] / per_field','self.t_need[i] / per_field')
s=s.replace('self.value[i] * per_field / self.t_need[i]','self.value[i] * max(0.0, 1.0 - factor[i]) * per_field / self.t_need[i]')
s=s.replace('    def summary(self)', '''    def invalidate(self):
        self.price = None
        self.night = -1

    def summary(self)''')
(A/'season.py').write_text(header+s)
# Instance-scoped band fit: several agents/cards must never share score configuration.
s=(R/'incoming/bandfit.py').read_text(); s=s[s.index('def exposure_bounds'):]
s=s.replace('def exposure_bounds(program: str, hits):','def exposure_bounds(self, program: str, hits):')
for old,new in [('EDGES','self.edges'),('MULT','self.mult'),('MISMATCH','self.mismatch')]:s=s.replace(old,new)
header='''"""Exposure-local band constraints adapted from the supplied participant project.
These bounds assume a shared weather factor and accurate public sky predictions.
They are diagnostic estimates and never certify raw target completion.
"""
INF=float("inf")
SPREAD=.03
class BandFit:
    def __init__(self, bands, multipliers, mismatch):
        dark,bright=float(bands["DARK"]),float(bands["BRIGHT"])
        self.edges={"DARK":(dark,INF),"BRIGHT":(bright,dark),"BACKUP":(0.,bright)}
        self.mult={k:float(v) for k,v in multipliers.items()}
        self.mismatch=float(mismatch)
'''
(A/'bandfit.py').write_text(header+'\n'.join('    '+l if l else '' for l in s.splitlines())+'\n')
p=A/'planner.py';s=p.read_text()
s=s.replace('from .opportunities import Opportunities','from .opportunities import Opportunities\nfrom .season import OptionPrices\nfrom .bandfit import BandFit\n\nSEASON_ENABLED = int(os.environ.get("FUSION_SEASON", "1"))')
s=s.replace('        self.factor_lower =', '        self.exposure_evidence = deque(maxlen=256)\n        self.bandfit = BandFit(self.bands, self.multipliers, self.mismatch)\n        self.factor_lower =',1)
needle='        self.lambda_frac = LAMBDA_FRAC'
pos=s.index('\n',s.index(needle))
s=s[:pos]+'''
        self.season = OptionPrices(self.ra, self.dec, self.flux, self.nights, self.lon,
            self.lat, self.min_alt, self.grid.n, self.grid.fov,
            [min(self.max_exposure, self.f0t0 / max(1e-8, f * PLAN_Q)) for f in self.flux],
            self.airmass_exponent, [max(self.multipliers.values()) * w for w in self.weight]) if SEASON_ENABLED else None
        self.season_night = -1
'''+s[pos:]
s=s.replace('        self.vcache = None\n        self.log(f"state_resync:', '        self.vcache = None\n        self.exposure_evidence.clear()\n        self.season_night = -1\n        if self.season is not None: self.season.invalidate()\n        self.log(f"state_resync:')
s=s.replace('        if learn:\n            self._offset_evidence(hits)', '''        if learn:
            clean_rows=[]
            for target_id, prediction in self.pending.items():
                score=hits.get(target_id, 0.)
                i=self.index_of[target_id]
                if score <= 0 or not prediction["dir_clean"]: continue
                seen=score / self.weight[i]
                ratio=seen / declared * self.f0t0 / (self.flux[i] * self.pending_duration * prediction["model"])
                saturated=(abs(seen-declared)<2e-4 or abs(seen-self.mismatch)<2e-4)
                clean_rows.append([prediction["model"], ratio, saturated, seen, True])
            # Zero recorded hits imply geometry failure, not a closed sky.
            closed=bool(hits) and not any_positive
            bounds=None if closed or self.all_sky_notice() else self.bandfit.exposure_bounds(self.pending_program,clean_rows)
            self.exposure_evidence.append({"index":index,"hours":hours,"night":self.pending_night,
                "bounds":bounds,"closed":closed,"clean_hits":len(clean_rows)})
            self._offset_evidence(hits)''')
s=s.replace('        lst = local_sidereal_deg(now, self.lon)\n        horizon', '''        lst = local_sidereal_deg(now, self.lon)
        season_mult = None
        if self.season is not None and self.fast_level < 3:
            if self.season_night != night_index:
                self.season.update(self.factor, night_index)
                self.season_night = night_index
            season_mult = self.season.mult_now(lst)
        def opportunity_mult(i):
            # Keep request rewards and unfinished required targets outside coarse region discounts.
            if season_mult is None or i in request_legs or (self.required[i] and self.factor_lower[i] < self.required_threshold):
                return 1.0
            return season_mult[self.season.region_of[i]]
        horizon''')
s=s.replace('proxy.append((v * (sin_alt ** 0.6)', 'proxy.append((v * opportunity_mult(i) * (sin_alt ** 0.6)')
s=s.replace('dense_val = self.weight[i] * max', 'dense_val = opportunity_mult(i) * self.weight[i] * max')
s=s.replace('(1.0 + URGENCY / nights_left) * damp * dirf)', '(1.0 + URGENCY / nights_left) * damp * dirf * opportunity_mult(i))')
p.write_text(s)
p=A/'agent.py';s=p.read_text()
s=s.replace('        self.last_now = None','        self.last_now = None\n        self.pace_measured = int(os.environ.get("FUSION_PACE", "1"))\n        self.initial_cpu = None\n        self.night_total = sum((b-a).total_seconds() for a,b in self.planner.nights)')
s=s.replace('        return max(1.0, night_seconds / (self.sim_step_ema or 900.0))', '''        bound=max(1.0, night_seconds / (self.sim_step_ema or 900.0))
        elapsed=self.night_total-night_seconds
        if self.pace_measured and self.observes >= 30 and elapsed >= 3*8*3600:
            measured=1.15*night_seconds*self.observes/max(1.,elapsed)
            return min(bound,max(.2*bound,measured))
        return bound''')
s=s.replace('        cpu_budget = PACE_SAFETY * cpu_left', '''        if self.initial_cpu is None: self.initial_cpu=cpu_left
        spendable=max(0.,cpu_left-(.04*self.initial_cpu if self.pace_measured else 0.))
        cpu_budget = PACE_SAFETY * spendable''')
s=s.replace('                "notices_now": notices,','''                "exposure_band_evidence": [{**r,"bounds":None if r["bounds"] is None else
                    [x if not isinstance(x,float) or math.isfinite(x) else None for x in r["bounds"]]}
                    for r in list(self.planner.exposure_evidence)[-12:]],
                "band_evidence_assumptions": "shared weather, accurate model; not raw-factor certification",
                "notices_now": notices,''')
# math already imported?
if 'import math\n' not in s:s=s.replace('import os\n','import os\nimport math\n')
p.write_text(s)
for p in (R.parent/'gosim-pro-normal-v32/tests').glob('test*.py'):shutil.copy2(p,R/'tests'/p.name)
