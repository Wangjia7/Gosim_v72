from pathlib import Path
import json
R=Path(__file__).resolve().parent;D=R/'agent'
for rel in ('fusion_core/agent.py','enhanced_agent.py'):
 p=D/rel;s=p.read_text();core=rel.startswith('fusion')
 s=s.replace('import time\n','import time\nfrom budget import AgentClock, near_wall_cap\nfrom log_review import ObservationReview\n')
 s=s.replace('        self.planner = Planner(init, log=log)','''        self.planner = Planner(init, log=log)
        self.clock = AgentClock(init)
        self.log_review = ObservationReview(self.planner) if os.environ.get("OBSERVER_LOG_REVIEW","1")=="1" else None''')
 s=s.replace('        cpu = time.process_time() - cpu_started','        cpu = time.process_time() - cpu_started\n        self.clock.account(cpu)')
 # Every search cost estimate refers to unit search breadth.
 s=s.replace('for k, cost in enumerate((cpu, wall)):', 'for k, cost in enumerate((cpu, wall)):\n                cost /= max(1.,self.planner.search_scale)')
 if not core:
  s=s.replace('        action = self._respond(payload)\n','        action = self._respond(payload)\n        level = self.planner.fast_level\n')
  s=s.replace('for ema, cost in ((self.cost_ema, cpu), (self.wall_ema, wall)):', 'for ema, cost in ((self.cost_ema, cpu), (self.wall_ema, wall)):\n                cost /= max(1.,self.planner.search_scale)')
 start=s.index('        wall = payload.get("wallclock") or {}',s.index('    def _clock('));end=s.index('\n    def ',start)
 s=s[:start]+'        return self.clock.read(payload)\n'+s[end:]
 before='        planner.on_result(payload.get("last_result"), now, hours)'
 s=s.replace(before,'''        if self.log_review:
            notices={(n.get("event_kind",""),n.get("direction",""))
                for n in (payload.get("latest_bulletin") or {}).get("notices",[])}
            self.log_review.record(payload.get("last_result"),now,notices)
'''+before)
 needle='        self._pace(payload, now)'
 s=s.replace(needle,'''        checkpoint=False
        if self.log_review:
            changed=self.log_review.invalidate(payload.get("new_messages",[]))
            checkpoint=self.log_review.checkpoint(now,force=changed)
            if checkpoint:log("exposure review: "+json.dumps(self.log_review.summary(),separators=(",",":")))
'''+needle)
 # With a valid CPU snapshot, engine gaps / model waits do not price down search.
 s=s.replace('while level < 3 and (self.cost_ema[level] > cpu_budget or self.wall_ema[level] > wall_budget):',
             'while level < 3 and (self.cost_ema[level] > cpu_budget or (not fair and self.wall_ema[level] > wall_budget)):')
 s=s.replace('if min(cpu_left, wall_left) < 15.0:', 'if cpu_left < 15.0 or near_wall_cap(wall_left):')
 s=s.replace('and deep_wall <= wall_budget)', 'and (not near_wall_cap(wall_left,deep_wall) if fair else deep_wall <= wall_budget))')
 if core:
  marker='        if deep != self.planner.deep:'
  s=s.replace(marker,'''        self.planner.cpu_turn_budget=max(.003,min(.02*cpu_left,cpu_budget)) if fair else max(.003,wall_budget)
        self.planner.search_scale=min(3.,max(1.,.65*cpu_budget/max(deep_cpu,.02))) if deep and fair else 1.
'''+marker)
 else:
  marker='        if level != self.planner.fast_level:'
  s=s.replace(marker,'''        self.planner.search_scale=min(3.,max(1.,.65*cpu_budget/max(self.cost_ema[0],.02))) if level==0 and fair else 1.
'''+marker)
 # Anomaly checks on compact log checkpoints; call quotas are spread over the season.
 s=s.replace('signature = (tuple(str(x) for x in self.advisor.texts), int(hours))','signature = (tuple(str(x) for x in self.advisor.texts), int(hours), checkpoint)')
 s=s.replace('signature=(tuple(str(x) for x in self.advisor.texts),int(hours))','signature=(tuple(str(x) for x in self.advisor.texts),int(hours), checkpoint)')
 if not core:
  marker='        if (night_end - now).total_seconds() < planner.min_exposure:'
  s=s.replace(marker,'''            if checkpoint and not self.rules_only:
                self._night_advice(night_start,payload,hours)
'''+marker)
 # Attach audit history to the LLM's bounded evidence rather than only the latest ratio.
 s=s.replace('return {"columns":', 'return {"log_review":self.log_review.summary() if self.log_review else {}, "columns":')
 marker='        if result.get("correct"):'
 if marker not in s:marker='        if result.get("is_correct"):'
 if marker not in s:
  # Existing report contract uses fault_detected.
  marker='        if correct:'
 if marker in s:
  s=s.replace(marker,marker+'\n            if self.log_review:self.log_review.repaired()')
 p.write_text(s)
# Replay must preserve the actual CPU search parameters after data loss.
p=D/'fusion_core/guarded.py';s=p.read_text().replace("'fast_level','deep','bad_forecast'","'fast_level','deep','search_scale','cpu_turn_budget','bad_forecast'");p.write_text(s)
for rel in ('fusion_core/planner.py','planner.py'):
 p=D/rel;s=p.read_text();core=rel.startswith('fusion')
 s=s.replace('        self.fast_level = 0','        self.search_scale = 1.0\n        self.fast_level = 0')
 if core:
  s=s.replace('        self.deep = False','        self.cpu_turn_budget = None\n        self.deep = False')
  s=s.replace('        self.next_up = None\n        if PARTIAL_DISCOUNT','        self.next_up = None\n        cpu_started=time.process_time()\n        if PARTIAL_DISCOUNT')
  s=s.replace('pool_size = DEEP_POOL if deep else','pool_size = int(DEEP_POOL*self.search_scale) if deep else')
  s=s.replace('n_anchors = DEEP_ANCHORS if deep else','n_anchors = int(DEEP_ANCHORS*self.search_scale) if deep else')
  s=s.replace('(DEEP_DENSE if deep else N_DENSE)','(int(DEEP_DENSE*self.search_scale) if deep else N_DENSE)')
  s=s.replace('        for rank, anchor in enumerate(anchors):','''        for rank, anchor in enumerate(anchors):
            if best is not None and self.cpu_turn_budget is not None and time.process_time()-cpu_started>=self.cpu_turn_budget:break''')
  s=s.replace('                for d_north, d_east in REFINE_STEPS:', '''                for d_north, d_east in REFINE_STEPS:
                    if self.cpu_turn_budget is not None and time.process_time()-cpu_started>=self.cpu_turn_budget:break''')
 else:
  s=s.replace('pool_size = (POOL,', 'pool_size = (int(POOL*self.search_scale),')
  s=s.replace('(N_ANCHORS, 3, 1, 1)', '(int(N_ANCHORS*self.search_scale), 3, 1, 1)')
  s=s.replace('N_DENSE if level == 0 else 2','int(N_DENSE*self.search_scale) if level == 0 else 2')
 p.write_text(s)
p=D/'advisor.py';s=p.read_text().replace('import math\n','import math\n')
s=s.replace('        self.last_review_version = -1','        self.last_review_version = -1\n        self.last_review_exposures = -1\n        self.last_review_cue = None\n        self.remaining_exposures = 1\n        self.observes_seen = 0')
s=s.replace('        self.known_targets = set(planner.ids)','''        self.observes_seen=len(planner.history)
        night_seconds=sum(max(0.,end.timestamp()-max(start.timestamp(),self.now)) for start,end in planner.nights if end.timestamp()>self.now)
        self.remaining_exposures=max(1.,night_seconds/max(planner.min_exposure,900.))
        self.known_targets = set(planner.ids)''')
s=s.replace("        if (self.anomaly_count < 32 and self.fault_applied and",'''        review=fault_table.get('log_review',{})
        cue=review.get('cue','retain')
        interval=max(8,math.ceil(self.remaining_exposures/max(1,32-self.anomaly_count)))
        urgent=cue in {'geometry_candidate','throughput_candidate'} and cue!=self.last_review_cue and self.observes_seen-self.last_review_exposures>=8
        review_due=self.last_review_version<0 or self.observes_seen-self.last_review_exposures>=interval or urgent
        if (review_due and self.anomaly_count < 32 and self.fault_applied and''')
s=s.replace('                self.last_review_version = self.ledger_version','                self.last_review_version = self.ledger_version\n                self.last_review_exposures = self.observes_seen\n                self.last_review_cue = cue')
p.write_text(s)
p=D/'observer.project.json';d=json.loads(p.read_text());d['environment']['OBSERVER_LOG_REVIEW']='1';p.write_text(json.dumps(d,indent=2)+'\n')
