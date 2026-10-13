import json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parent
env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],'OBSERVER_MODEL_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1'}
rows=[]
for family in ['baseline','diagnostic-corrected','value-guard-frozen']:
 subprocess.run([sys.executable,str(R/family/'build_native.py')],env=env,check=True,timeout=60)
 for tag,card in [('normal','normal-b'),('long',str(R.parent/'gosim-desi-v300/cases-v2/long-held')),('L1','L1')]:
  label='round2-'+tag+'-'+family;start=datetime.now(timezone.utc).isoformat()
  with (R/'experiments'/f'{label}.log').open('x') as f:q=subprocess.run([sys.executable,str(R/'run_cpu.py'),'--family',family,'--card',card,'--out',label,'--budget','900','--wall-cap','7200'],env=env,stdout=f,stderr=subprocess.STDOUT)
  row={'label':label,'start':start,'end':datetime.now(timezone.utc).isoformat(),'returncode':q.returncode}
  p=R/'experiments'/label/'workflow_result.json'
  if p.exists():
   d=json.loads(p.read_text());row.update(score=d['score_report'],clock=d['fair_clock'],termination=d['termination_reason'])
  rows.append(row);(R/'experiments/dev-round2-progress.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,row.get('score',{}).get('total'),flush=True)
  if q.returncode:raise SystemExit(q.returncode)
