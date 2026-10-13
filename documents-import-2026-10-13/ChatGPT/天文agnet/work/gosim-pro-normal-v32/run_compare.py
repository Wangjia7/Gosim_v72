import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--cards',nargs='+',default=['L1','L2'])
parser.add_argument('--families',nargs='+',default=['baseline','full','cache'])
parser.add_argument('--tag',default='initial');parser.add_argument('--budget',type=float,default=180)
args=parser.parse_args()
manifest={}
for family,folder in [('baseline','baseline'),('full','agent'),('cache','cache-only')]:
    manifest[family]={str(p.relative_to(ROOT/folder)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.md','.json')}
(ROOT/f'experiments/{args.tag}-source.json').write_text(json.dumps(manifest,indent=2)+'\n')
results=[]
for card in args.cards:
    path=Path('/Users/jqwang/Documents/gosim-observer-examples/local-cards')/card
    if not path.exists():path=ROOT.parent/'gosim-desi-v300/cases'/card
    for family in args.families:
        folder={'baseline':'baseline','full':'agent','cache':'cache-only'}[family]
        out=ROOT/'experiments'/f'{args.tag}-{card}-{family}'
        assert not out.exists(),str(out)
        start=datetime.now(timezone.utc).isoformat();t=time.monotonic()
        cmd=[sys.executable,str(ROOT.parent/'gosim-desi-v300/runner/run_local.py'),'--inherit-env',
             '--card',str(path),'--agent',sys.executable+' -u agent.py','--agent-cwd',str(ROOT/folder),
             '--out',str(out),'--wallclock',str(args.budget),'--quiet']
        run=subprocess.run(cmd,env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},text=True,capture_output=True,timeout=600)
        out.mkdir(exist_ok=True);(out/'runner.stdout').write_text(run.stdout);(out/'runner.stderr').write_text(run.stderr)
        w=json.loads((out/'workflow_result.json').read_text()) if (out/'workflow_result.json').exists() else {}
        score=w.get('score_report',{})
        row={'card':card,'family':family,'start':start,'end':datetime.now(timezone.utc).isoformat(),
             'exit_code':run.returncode,'elapsed_wall_seconds':time.monotonic()-t,
             'total':score.get('total'),'components':score.get('components'),'counts':score.get('counts'),
             'termination':w.get('termination_reason'),'fair_clock':w.get('fair_clock'),
             'actions_sha256':hashlib.sha256((out/'actions.jsonl').read_bytes()).hexdigest() if (out/'actions.jsonl').exists() else None,
             'command':cmd}
        results.append(row);(ROOT/f'experiments/{args.tag}-results.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ('card','family','total','termination','elapsed_wall_seconds')},ensure_ascii=False),flush=True)
