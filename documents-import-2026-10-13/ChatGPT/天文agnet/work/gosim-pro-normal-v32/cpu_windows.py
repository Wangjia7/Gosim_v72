import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
while not (ROOT/'experiments/repaired-L2-full/workflow_result.json').exists():time.sleep(1)
rows=[]
for card in ('normal-a','normal-b','sparse'):
    path=str(ROOT/'cases-v2'/card) if card.startswith('normal-') else card
    out=f'windows-{card}'
    with (ROOT/'experiments'/f'{out}.log').open('w') as log:
        r=subprocess.run([sys.executable,str(ROOT/'run_cpu.py'),'--family','windows','--card',path,'--out',out],
                         stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if r.returncode:raise RuntimeError(out)
    r=json.loads((ROOT/'experiments'/out/'workflow_result.json').read_text())
    row={'card':card,'family':'windows','total':r['score_report']['total'],'counts':r['score_report']['counts'],
         'components':r['score_report']['components'],'fair_clock':r['fair_clock'],'termination':r['termination_reason'],'out':out}
    rows.append(row);(ROOT/'experiments/windows-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:row[k] for k in ('card','family','total','termination')}),flush=True)
