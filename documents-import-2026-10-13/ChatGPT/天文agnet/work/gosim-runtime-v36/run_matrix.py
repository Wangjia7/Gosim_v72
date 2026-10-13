"""Sequential paired runs; retain every failure and first candidate result."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
matrix=[('normal-base','baseline','normal-b'),('normal-initial','initial-frozen','normal-b'),
        ('normal-anomaly','anomaly-only','normal-b'),
        ('long-base','baseline',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
        ('long-initial','initial-frozen',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
        ('long-anomaly','anomaly-only',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
        ('L1-base','baseline','L1'),('L1-initial','initial-frozen','L1')]
final='--final' in sys.argv
if final:
    matrix=[('normal-final','final-frozen','normal-b'),
            ('normal-final-anomaly','final-anomaly','normal-b'),
            ('long-final','final-frozen',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
            ('long-final-anomaly','final-anomaly',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
            ('L1-final','final-frozen','L1')]
accepted='--accepted' in sys.argv
if accepted:
    matrix=[('normal-accepted','accepted-frozen','normal-b'),
            ('long-accepted','accepted-frozen',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
            ('L1-accepted','accepted-frozen','L1')]
release='--release' in sys.argv
if release:
    matrix=[('normal-release','release-frozen','normal-b'),
            ('long-release','release-frozen',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
            ('L1-release','release-frozen','L1')]
native_release='--release-native' in sys.argv
if native_release:
    matrix=[('normal-release-native','release-native-frozen','normal-b'),
            ('long-release-native','release-native-frozen',str(root.parent/'gosim-desi-v300/cases-v2/long-held')),
            ('L1-release-native','release-native-frozen','L1')]
env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],
     'PYTHONDONTWRITEBYTECODE':'1','OBSERVER_MODEL_DISABLED':'1'}
rows=[]
for label,family,card in matrix:
    logfile=root/'experiments'/f'{label}.log'
    start=datetime.now(timezone.utc).isoformat()
    with logfile.open('x') as stream:
        process=subprocess.run([sys.executable,str(root/'run_cpu.py'),'--family',family,'--card',card,
            '--out',label,'--budget','900','--wall-cap','7200'],env=env,stdout=stream,stderr=subprocess.STDOUT)
    row={'label':label,'family':family,'card':card,'start':start,
         'end':datetime.now(timezone.utc).isoformat(),'returncode':process.returncode}
    result=root/'experiments'/label/'workflow_result.json'
    if result.exists():
        d=json.loads(result.read_text());row.update({'score':d['score_report'],'clock':d['fair_clock'],'termination':d['termination_reason']})
    rows.append(row)
    (root/'experiments'/('release-native-progress.json' if native_release else 'release-progress.json' if release else 'accepted-progress.json' if accepted else 'final-progress.json' if final else 'matrix-progress.json')).write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({k:v for k,v in row.items() if k not in ('score','clock')})+
          (' total='+str(row['score']['total']) if 'score' in row else ''),flush=True)
    if process.returncode:break
