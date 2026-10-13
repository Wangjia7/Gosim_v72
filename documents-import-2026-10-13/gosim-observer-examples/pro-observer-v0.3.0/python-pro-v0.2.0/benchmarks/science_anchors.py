#!/usr/bin/env python3
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NATIVE='/Library/Developer/CommandLineTools/usr/bin/python3'
base={'GEOMETRY':'1','STATE_EVIDENCE':'1','TEMPORAL':'1','PROGRAM_AWARE':'1','EVENT_DURATIONS':'0','GAIN_CACHE':'1','SCIENCE_ANCHORS':'32'}
for label,price in [('science-anchors32','0'),('science-anchors32-price','1')]:
 command=[NATIVE,'-B',str(ROOT/'benchmarks/run.py'),'--agent-dir',str(ROOT),'--card','L1','--label',label]
 for name,value in {**base,'SCIENCE_TIME_PRICE':price}.items():command+=['--set',f'PRO_{name}={value}']
 print('STAGE_START '+label,flush=True)
 result=subprocess.run(command)
 print(f'STAGE_END {label} returncode={result.returncode}',flush=True)
