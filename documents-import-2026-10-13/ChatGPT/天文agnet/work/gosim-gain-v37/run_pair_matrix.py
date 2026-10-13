"""Frozen fair sequential paired matrix; never drop failed episodes."""
from datetime import datetime,timezone
import json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
stage=sys.argv[1];family=sys.argv[2]
if stage=='corrected-dev':
 matrix=[('normal','normal-b'),('long',str(R.parent/'gosim-desi-v300/cases-v2/long-held')),('L1','L1')]
elif stage=='holdout':
 matrix=[(n,n) for n in ['L2','L3','L4']]+[(n,str(R.parent/'gosim-desi-v300/cases-v2'/n)) for n in ['dense-held','stress-held']]+[(n,str(R/'cases'/n)) for n in ['fresh-sparse','fresh-dense','fresh-mixed','fresh-long']]
elif stage=='holdout-repeat':
 matrix=[('L2','L2'),('fresh-long',str(R/'cases/fresh-long'))]
else:raise ValueError(stage)
env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],'OBSERVER_MODEL_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1'}
for f in ['baseline',family]:subprocess.run([sys.executable,str(R/f/'build_native.py')],env=env,check=True,timeout=60)
rows=[]
for name,card in matrix:
 for f in ['baseline',family]:
  label=stage+'-'+name+'-'+f;start=datetime.now(timezone.utc).isoformat()
  with (R/'experiments'/f'{label}.log').open('x') as s:q=subprocess.run([sys.executable,str(R/'run_cpu.py'),'--family',f,'--card',card,'--out',label,'--budget','900','--wall-cap','7200'],env=env,stdout=s,stderr=subprocess.STDOUT)
  row={'label':label,'card':name,'family':f,'start':start,'end':datetime.now(timezone.utc).isoformat(),'returncode':q.returncode}
  p=R/'experiments'/label/'workflow_result.json'
  if p.exists():
   d=json.loads(p.read_text());row.update(score=d['score_report'],clock=d['fair_clock'],termination=d['termination_reason'])
  rows.append(row);(R/'experiments'/f'{stage}-progress.json').write_text(json.dumps(rows,indent=2)+'\n')
  print(label,row.get('score',{}).get('total'),row.get('termination','run_failed'),flush=True)
  # Failed rows remain in the matrix; unaffected cards still execute.
