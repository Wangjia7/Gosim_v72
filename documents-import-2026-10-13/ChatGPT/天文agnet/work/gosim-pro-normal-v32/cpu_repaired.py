import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
while not (ROOT/'experiments/minimal-normal-b/workflow_result.json').exists():time.sleep(1)
rows=[]
for card,family,out in [('L1','minimal','repaired-L1-minimal'),('L1','pruned','repaired-L1-full'),('L2','pruned','repaired-L2-full')]:
    with (ROOT/'experiments'/f'{out}.log').open('w') as log:
        run=subprocess.run([sys.executable,str(ROOT/'run_cpu.py'),'--family',family,'--card',card,'--out',out],
                           stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if run.returncode:raise RuntimeError(out)
    r=json.loads((ROOT/'experiments'/out/'workflow_result.json').read_text())
    row={'card':card,'family':family,'total':r['score_report']['total'],'counts':r['score_report']['counts'],
         'components':r['score_report']['components'],'fair_clock':r['fair_clock'],'termination':r['termination_reason'],'out':out}
    rows.append(row);(ROOT/'experiments/repaired-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:row[k] for k in ('card','family','total','termination')}),flush=True)
