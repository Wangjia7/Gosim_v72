"""Offline official scorer with a correct same-process CPU hook, no model/network.

The unmodified official macOS subprocess meter undercounts CPU on this host by ~41.7x.
This diagnostic runner charges time.process_time deltas around the trusted local agent's turns.
The official workflow, calibration workload, hard cap, actions and scorer remain unchanged.
ZIP subprocess protocol is verified separately.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import platform
import time

ROOT=Path(__file__).resolve().parent
args=argparse.ArgumentParser();args.add_argument('--family',required=True);args.add_argument('--card',required=True)
args.add_argument('--out',required=True);args.add_argument('--budget',type=float,default=900)
args.add_argument('--wall-cap',type=float,default=7200)
args=args.parse_args()
os.environ.pop('V5_ORACLE_REPORTS',None)
os.environ.pop('V5_DUMP_HITS',None)
folders={'baseline':'baseline','candidate':'agent'}
folder=ROOT/folders.get(args.family,args.family)
sys.path.insert(0,str(ROOT.parent/'gosim-desi-v300/runner'))
sys.path.insert(0,str(folder))
if args.family != 'incoming':
    for key,value in json.loads((folder/'observer.project.json').read_text())['environment'].items():
        if key.startswith(('PRO_', 'FUSION_', 'OBSERVER_')):os.environ[key]=value
from challenge.v4_workflow import V4Workflow
class CPU:
    @staticmethod
    def cpu():return time.process_time()
class Local:
    def initialize(self,init):
        if args.family == 'incoming':
            from agent import ObserverAgent
        else:
            from routing import initial_route
            family,_=initial_route(init)
            if family=='fusion_core':from fusion_core.agent import ObserverAgent
            elif family=='official_pro':from official_pro.agent import ObserverAgent
            else:from enhanced_agent import ObserverAgent
        self.agent=ObserverAgent(init,rules_only=True)
        manifest['route']=ObserverAgent.__module__
        manifest['python']=sys.version
        manifest['python_executable']=sys.executable
        manifest['platform']=platform.platform()
        if args.family!='incoming':
            import native
            manifest['native_loaded']=bool(native.LIB)
            manifest['native_cells']=bool(getattr(native,'CELL_LIB',None))
        else:manifest['native_loaded']=False
    def decide(self,message,deadline):
        try:
            action=self.agent.respond(message['payload'])
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        return {'protocol_version':'participant-agent-protocol-v4','message_type':'decision_response',
                'decision_sequence':message['decision_sequence'],**action}

card=Path(args.card)
if not card.exists():card=Path('/Users/jqwang/Documents/gosim-observer-examples/local-cards')/args.card
if not card.exists():card=ROOT.parent/'gosim-pro-normal-v32/cases-v2'/args.card
out=ROOT/'experiments'/args.out
assert not out.exists(),str(out)
out.mkdir(parents=True)
manifest={'source':{str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in folder.rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.json','.md')},
    'inputs':{str(p.relative_to(card)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in card.rglob('*') if p.is_file() and p.suffix in ('.csv','.json','.jsonl')},
    'family':args.family,'budget':args.budget,'wall_cap':args.wall_cap,'api':False,'meter':'local time.process_time around official workflow turns',
    'switches':{k:v for k,v in os.environ.items() if k.startswith(('PRO_', 'FUSION_', 'V5_'))},
    'start':datetime.now(timezone.utc).isoformat()}
(out/'source-input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
local=Local();started=time.monotonic()
result=V4Workflow(card).run(local.decide,out,wallclock_seconds=args.budget,initialize=local.initialize,agent_hooks=CPU(),clock_mode="cpu",wall_cap=args.wall_cap)
manifest['own_clock_cpu']=getattr(getattr(local.agent,'clock',None),'used',None)
if getattr(local.agent,'log_review',None):manifest['exposure_review']=local.agent.log_review.summary()
manifest['end']=datetime.now(timezone.utc).isoformat()
manifest['elapsed_wall_seconds']=time.monotonic()-started
(out/'source-input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'family':args.family,'card':card.name,'total':result['score_report']['total'],
    'counts':result['score_report']['counts'],'clock':result['fair_clock'],'termination':result['termination_reason']}),flush=True)
