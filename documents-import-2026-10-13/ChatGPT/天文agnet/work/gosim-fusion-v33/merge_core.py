from pathlib import Path
import shutil
R=Path(__file__).resolve().parent
D=R/'fused';shutil.rmtree(D) if D.exists() else None
shutil.copytree(R/'local-baseline',D,ignore=shutil.ignore_patterns('__pycache__','*.so','*.pyc'))
C=D/'fusion_core';C.mkdir();(C/'__init__.py').write_text('')
for name in ['planner','season','fault','skymath','agent']:
 s=(R/'incoming'/f'{name}.py').read_text()
 for mod in ['season','bandfit','fault','planner','skymath']:
  s=s.replace(f'from {mod} import ',f'from .{mod} import ')
  s=s.replace(f'import {mod}\n',f'from . import {mod}\n')
 if name=='planner':
  s=s.replace('from . import bandfit','from .bandfit import BandFit')
  s=s.replace('bandfit.configure(self.bands, self.multipliers, self.mismatch)','self.bandfit = BandFit(self.bands, self.multipliers, self.mismatch)')
  s=s.replace('bandfit.exposure_bounds(self.pending_program, rows)','self.bandfit.exposure_bounds(self.pending_program, rows)')
  # Runtime score/exposure limits; preserve the incoming heuristic at its default threshold.
  s=s.replace('self.factor[i] < 0.5','self.factor[i] < self.required_threshold')
  s=s.replace('f >= REQUIRED_SAFE_FACTOR','f >= self.required_safe').replace('f < 0.5','f < self.required_threshold')
  s=s.replace('/ 0.5 * self.req_calib','/ self.required_threshold * self.req_calib').replace('/ 0.5\n','/ self.required_threshold\n')
  s=s.replace('bonus = REQUIRED_BONUS *','bonus = self.required_bonus *').replace('+ REQUIRED_BONUS *','+ self.required_bonus *')
  s=s.replace('if T <= seconds_left and T >= MIN_T','if self.min_exposure <= T <= min(seconds_left,self.max_exposure) and T >= MIN_T')
  s=s.replace('if not durations:\n            durations = [int(seconds_left)]','if not durations:\n            durations = [int(min(seconds_left,self.max_exposure))]')
  s=s.replace('DUMP_HITS = os.environ.get("V5_DUMP_HITS", "")','DUMP_HITS = ""')
  start=s.index('        if DUMP_HITS:\n');end=s.index('\n',s.index('self._dump_exposure',start))
  s=s[:start]+s[end:]
  start=s.index('    def _dump_exposure(');end=s.index('\n    def ',start+10);s=s[:start]+s[end:]
  s=s.replace('Moon(now + timedelta(seconds=600), lst,', 'Moon(now + timedelta(seconds=600), local_sidereal_deg(now + timedelta(seconds=600), self.lon),')
 if name=='season':
  s=s.replace('t + 1800.0','t + min(3600.0, span - t) / 2.0')
 if name=='agent':
  s=s.replace('from .planner import MONITOR_T, Planner','from .planner import MONITOR_T\nfrom .guarded import Planner')
  start=s.index('# development only (benchmarks of the planner');end=s.index('\n\n',start);s=s[:start]+s[end:]
  start=s.index('        if ORACLE_REPORTS:');end=s.index('\n        ',s.index('return {"action": "report"',start)+8);s=s[:start]+s[end:]
  # Record cost at the level actually selected in this turn.
  s=s.replace('        action = self._respond(payload)\n','        action = self._respond(payload)\n        level = self.planner.fast_level\n        deep = self.planner.deep and level == 0\n')
  s=s.replace('        self.rules_only = rules_only','        self.preference_until = 0\n        self.rules_only = rules_only')
  s=s.replace('        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))','''        # Process the in-flight exposure before loss messages invalidate its action index.
        planner.on_result(payload.get("last_result"), now, hours)
        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))
        if any(m.get("record_type")=="state_resync" for m in payload.get("new_messages", [])):
            self.detector.reset(hours,"state resync")
            self.detector.brows.clear()
            self.r_hours.clear();self.b_hours.clear()
            self.ref_from_hours=hours
            self.fault_likely=None''')
  s=s.replace('        planner.on_result(payload.get("last_result"), now, hours)\n        bounds','        bounds')
  s=s.replace('        self._pace(payload, now)\n','''        self._pace(payload, now)
        if not self.rules_only:self.advisor.ingest(payload,planner)
        if now.timestamp()>self.preference_until:
            planner.operator_priorities=set();planner.extra_avoid=set()
''')
  s=s.replace('        if (night_end - now).total_seconds() < planner.min_exposure:', '''            if not self.rules_only:
                signature=(tuple(str(x) for x in self.advisor.texts),int(hours))
                if signature!=getattr(self,"_advice_signature",None):
                    self._advice_signature=signature
                    self._night_advice(night_start,payload,hours)
        if (night_end - now).total_seconds() < planner.min_exposure:''')
  # Share the bounded, evidence-validated operator preferences and model wait allocation.
  local=(D/'official_pro/agent.py').read_text()
  for method,nextmethod in [('_model_wait_budget','_apply_advice'),('_apply_advice','_scale_ref')]:
   start=s.index(f'    def {method}(');end=s.index('\n    def ',start+10)
   a=local.index(f'    def {method}(');b=local.index(f'    def {nextmethod}(',a)
   replacement=local[a:b].rstrip()+'\n'
   s=s[:start]+replacement+s[end:]
  s=s.replace('the\n        weather-free efficiency bounds','the\n        model-dependent efficiency bounds')
  s=s.replace('"rule_evidence": det.last_evidence or None,','"rule_evidence": det.last_evidence or None, "bound_assumptions": "shared weather and accurate sky model; never certify raw completion",')
 (C/f'{name}.py').write_text(s)
shutil.copy2(R/'agent/official_pro/bandfit.py',C/'bandfit.py')
# Keep the public compatibility router, substituting the fused normal core.
p=D/'routing.py';s=p.read_text().replace("else 'official_pro'","else 'fusion_core'");p.write_text(s)
p=D/'agent.py';s=p.read_text().replace("if family=='official_pro':\n                from official_pro.agent import ObserverAgent","if family=='fusion_core':\n                from fusion_core.agent import ObserverAgent");p.write_text(s)
p=R/'run_cpu.py';s=p.read_text().replace("if family=='official_pro':from official_pro.agent import ObserverAgent","if family=='fusion_core':from fusion_core.agent import ObserverAgent\n            elif family=='official_pro':from official_pro.agent import ObserverAgent");p.write_text(s)
