from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys,time
r=Path(__file__).resolve().parent
runner=str(r/'runner/run_local.py')
profiles=json.loads((r/'case-manifest-v2.json').read_text())
plan={'source':json.loads((r/'request-guard-source-frozen.json').read_text()),'budget_standard_cpu_seconds':120,
      'baseline':'official python-pro byte copy','candidate':'agent','api':'off',
      'primary':'final official total points, complete seasons only','controls':'same inputs, scorer, public interface and requested fair CPU budget',
      'limits':'real-time adaptive search can choose different paths; no single-switch causality claim',
      'cases':[x['name'] for x in profiles]}
(r/'experiments/request-guard-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
results=[]
for c in profiles:
 for family in ('request-guard-frozen',):
  out=r/'experiments'/f"v2-{family}-{c['name']}"; start=datetime.now(timezone.utc).isoformat(); t=time.monotonic()
  command=[sys.executable,runner,'--inherit-env','--card',str(r/'cases-v2'/c['name']),
   '--agent',f'{sys.executable} -u agent.py','--agent-cwd',str(r/family),'--out',str(out),'--wallclock','120','--quiet']
  p=subprocess.run(command,env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},text=True,capture_output=True,timeout=280)
  (out/'runner.stdout').write_text(p.stdout);(out/'runner.stderr').write_text(p.stderr)
  w=json.loads((out/'workflow_result.json').read_text()) if (out/'workflow_result.json').exists() else {}
  score=w.get('score_report',{}); count=score.get('counts',{}); row={'case':c['name'],'split':c['split'],'family':family,
   'started_at':start,'ended_at':datetime.now(timezone.utc).isoformat(),'runner_elapsed_seconds':time.monotonic()-t,
   'exit_code':p.returncode,'termination':w.get('termination_reason'),'total':score.get('total'),
   'components':score.get('components'),'counts':count,'fair_clock':w.get('fair_clock'),
   'actions_sha256':hashlib.sha256((out/'actions.jsonl').read_bytes()).hexdigest() if (out/'actions.jsonl').exists() else None}
  results.append(row);(r/'experiments/request-guard-results.json').write_text(json.dumps(results,indent=2)+'\n')
  print(c['name'],family,row['termination'],row['total'],flush=True)
