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
import time

ROOT=Path(__file__).resolve().parent
args=argparse.ArgumentParser();args.add_argument('--family',required=True);args.add_argument('--card',required=True)
args.add_argument('--out',required=True);args.add_argument('--budget',type=float,default=180)
args=args.parse_args()
folders={'baseline':'baseline','cache':'cache-only','full':'candidate-initial-frozen','pruned':'candidate-pruned','final':'agent'}
if args.family=='minimal':
    folders['minimal']='candidate-pruned'
    os.environ.update(PRO_FULL_FIELD='0',PRO_BREAKPOINTS='0',PRO_CONSERVATIVE_REQUIRED='0',PRO_REQUEST_BATCH='0')
if args.family=='windows':
    folders['windows']='candidate-pruned'
    os.environ['PRO_WINDOW_URGENCY']='1'
folder=ROOT/folders.get(args.family,args.family)
sys.path.insert(0,str(ROOT.parent/'gosim-desi-v300/runner'))
sys.path.insert(0,str(folder))
from challenge.v4_workflow import V4Workflow
class CPU:
    @staticmethod
    def cpu():return time.process_time()
class Local:
    def initialize(self,init):
        if args.family in ('baseline','cache'):
            from agent import ObserverAgent
        else:
            from routing import initial_route
            family,_=initial_route(init)
            if family=='official_pro':from official_pro.agent import ObserverAgent
            else:from enhanced_agent import ObserverAgent
        self.agent=ObserverAgent(init,rules_only=True)
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
if not card.exists():card=ROOT.parent/'gosim-desi-v300/cases'/args.card
out=ROOT/'experiments'/args.out
assert not out.exists(),str(out)
out.mkdir(parents=True)
manifest={'source':{str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in folder.rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.json','.md')},
    'inputs':{str(p.relative_to(card)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in card.rglob('*') if p.is_file() and p.suffix in ('.csv','.json','.jsonl')},
    'family':args.family,'budget':args.budget,'api':False,'meter':'local time.process_time around official workflow turns',
    'switches':{k:v for k,v in os.environ.items() if k.startswith('PRO_')},
    'start':datetime.now(timezone.utc).isoformat()}
(out/'source-input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
local=Local();started=time.monotonic()
result=V4Workflow(card).run(local.decide,out,wallclock_seconds=args.budget,initialize=local.initialize,agent_hooks=CPU())
manifest['end']=datetime.now(timezone.utc).isoformat()
manifest['elapsed_wall_seconds']=time.monotonic()-started
(out/'source-input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'family':args.family,'card':card.name,'total':result['score_report']['total'],
    'counts':result['score_report']['counts'],'clock':result['fair_clock'],'termination':result['termination_reason']}),flush=True)
