from pathlib import Path
import json,subprocess,sys
R=Path(__file__).resolve().parent
matrix=[('candidate','normal-b','candidate-normal-b-900'),
 ('baseline','L1','baseline-L1-900'),('candidate','L1','candidate-L1-900'),
 ('baseline',str(R.parent/'gosim-desi-v300/cases-v2/long-held'),'baseline-long-900'),
 ('candidate',str(R.parent/'gosim-desi-v300/cases-v2/long-held'),'candidate-long-900')]
for family,card,name in matrix:
 print('starting '+name,flush=True)
 with (R/(name+'.log')).open('w') as f:
  result=subprocess.run([sys.executable,str(R/'run_cpu.py'),'--family',family,'--card',card,'--out',name,'--budget','900','--wall-cap','7200'],stdout=f,stderr=subprocess.STDOUT)
 if result.returncode:
  print('failed '+name+' code '+str(result.returncode),flush=True);sys.exit(result.returncode)
 d=json.loads((R/'experiments'/name/'workflow_result.json').read_text())
 print(json.dumps({'run':name,'total':d['score_report']['total'],'termination':d['termination_reason'],'clock':d['fair_clock']},ensure_ascii=False),flush=True)
