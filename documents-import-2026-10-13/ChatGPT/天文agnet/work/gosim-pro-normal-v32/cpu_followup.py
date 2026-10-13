import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
while not (ROOT/'experiments/cpu-sparse-pruned/workflow_result.json').exists():time.sleep(1)
rows=[]
plan=[('L1','pruned','cpu-L1-pruned-r2')]
for card in ('normal-a','normal-b'):
    plan += [(str(ROOT/'cases-v2'/card),'baseline',f'new-{card}-baseline'),
             (str(ROOT/'cases-v2'/card),'pruned',f'new-{card}-pruned')]
for card,family,out in plan:
    with (ROOT/'experiments'/f'{out}.log').open('w') as log:
        run=subprocess.run([sys.executable,str(ROOT/'run_cpu.py'),'--family',family,'--card',card,'--out',out],
            stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},timeout=600)
    if run.returncode:raise RuntimeError(out)
    r=json.loads((ROOT/'experiments'/out/'workflow_result.json').read_text())
    row={'card':Path(card).name,'family':family,'total':r['score_report']['total'],'components':r['score_report']['components'],
         'counts':r['score_report']['counts'],'termination':r['termination_reason'],'fair_clock':r['fair_clock'],'out':out}
    rows.append(row);(ROOT/'experiments/followup-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:row[k] for k in ('card','family','total','termination')},ensure_ascii=False),flush=True)
