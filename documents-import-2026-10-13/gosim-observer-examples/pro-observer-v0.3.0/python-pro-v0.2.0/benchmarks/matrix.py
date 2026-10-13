#!/usr/bin/env python3
"""Sequential L1 ablations; each stage is recorded by the standalone harness."""
import subprocess
from pathlib import Path
NATIVE='/Library/Developer/CommandLineTools/usr/bin/python3'
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['GEOMETRY','STATE_EVIDENCE','TEMPORAL','PROGRAM_AWARE','EVENT_DURATIONS']
STAGES=[('guards-cache',0),('geometry',1),('state',2),('temporal',3),('program',4),('events-all',5)]
for label,enabled in STAGES:
    command=[NATIVE,'-B',str(ROOT/'benchmarks/run.py'),'--agent-dir',str(ROOT),'--card','L1','--label',label,'--set','PRO_GAIN_CACHE=1']
    for index,flag in enumerate(FLAGS): command+=['--set',f'PRO_{flag}={int(index<enabled)}']
    print(f'STAGE_START {label}',flush=True)
    result=subprocess.run(command)
    print(f'STAGE_END {label} returncode={result.returncode}',flush=True)
