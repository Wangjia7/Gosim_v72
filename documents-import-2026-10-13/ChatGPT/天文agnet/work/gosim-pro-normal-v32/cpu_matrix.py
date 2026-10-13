from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
# Never run two charged experiments together. Wait for the separately started reference.
while not (ROOT/'experiments/cpu-L1-baseline/workflow_result.json').exists():time.sleep(1)
rows=[]
for card,family in [('L1','baseline'),('L1','pruned'),('L1','cache'),('L2','baseline'),('L2','pruned'),
                    ('sparse','baseline'),('sparse','pruned')]:
    out=f'cpu-{card}-{family}'
    if not (ROOT/'experiments'/out/'workflow_result.json').exists():
        log=ROOT/'experiments'/f'{out}.log'
        with log.open('w') as handle:
            r=subprocess.run([sys.executable,str(ROOT/'run_cpu.py'),'--family',family,'--card',card,'--out',out],
                stdout=handle,stderr=subprocess.STDOUT,env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},timeout=600)
        if r.returncode:raise RuntimeError(f'{out}: {r.returncode}; see {log}')
    r=json.loads((ROOT/'experiments'/out/'workflow_result.json').read_text())
    row={'card':card,'family':family,'total':r['score_report']['total'],'components':r['score_report']['components'],
         'counts':r['score_report']['counts'],'termination':r['termination_reason'],'fair_clock':r['fair_clock'],'out':out}
    rows.append(row);(ROOT/'experiments/cpu-matrix-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:row[k] for k in ('card','family','total','termination')},ensure_ascii=False),flush=True)
