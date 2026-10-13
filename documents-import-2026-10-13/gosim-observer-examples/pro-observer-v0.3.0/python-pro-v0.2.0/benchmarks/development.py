#!/usr/bin/env python3
"""Explicit sequential L1 development variants, no heldout cards."""
import subprocess
from pathlib import Path
NATIVE='/Library/Developer/CommandLineTools/usr/bin/python3'
ROOT=Path(__file__).resolve().parents[1]
BASE={'GEOMETRY':'1','STATE_EVIDENCE':'1','TEMPORAL':'1','PROGRAM_AWARE':'1','EVENT_DURATIONS':'0','GAIN_CACHE':'1'}
VARIANTS=[('finish-k2',{'KAPPA':'2'}),('finish-aware',{'KAPPA':'2','PARTIAL_DISCOUNT':'0.2','PARTIAL_DONE':'0.95','PARTIAL_NIGHTS':'1','LAMBDA_FRAC':'0.3','REQUIRED_BONUS':'50','REQUEST_MULT':'1','URGENCY':'0.5'}),('price-low',{'LAMBDA_FRAC':'0.15'})]
for label,extra in VARIANTS:
 command=[NATIVE,'-B',str(ROOT/'benchmarks/run.py'),'--agent-dir',str(ROOT),'--card','L1','--label',label]
 for name,value in {**BASE,**extra}.items():command+=['--set',f'PRO_{name}={value}']
 print(f'STAGE_START {label}',flush=True)
 result=subprocess.run(command)
 print(f'STAGE_END {label} returncode={result.returncode}',flush=True)
