import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
while not (ROOT/'experiments/new-normal-b-pruned/workflow_result.json').exists():time.sleep(1)
rows=[]
for card in ('L1','L2','sparse','normal-a','normal-b'):
    path=str(ROOT/'cases-v2'/card) if card.startswith('normal-') else card
    out=f'minimal-{card}'
    with (ROOT/'experiments'/f'{out}.log').open('w') as log:
        r=subprocess.run([sys.executable,str(ROOT/'run_cpu.py'),'--family','minimal','--card',path,'--out',out],
            stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if r.returncode:raise RuntimeError(out)
    r=json.loads((ROOT/'experiments'/out/'workflow_result.json').read_text())
    row={'card':card,'family':'minimal','total':r['score_report']['total'],'components':r['score_report']['components'],
        'counts':r['score_report']['counts'],'termination':r['termination_reason'],'fair_clock':r['fair_clock'],'out':out}
    rows.append(row);(ROOT/'experiments/minimal-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:row[k] for k in ('card','family','total','termination')}),flush=True)
