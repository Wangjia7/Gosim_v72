"""Diagnostic profile of unchanged Pro; partial run, NOT a performance score."""
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time

ROOT = Path('/Users/jqwang/Documents/gosim-observer-examples')
OUT = Path(__file__).resolve().parent / 'profile-L1-first20'
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'python-pro'), str(ROOT / 'runner')]
os.environ['OBSERVER_MODEL_DISABLED'] = '1'
os.environ['PRO_FIXED_LEVEL'] = '0'
from agent import ObserverAgent
from challenge.v4_workflow import V4Workflow, PROTOCOL_VERSION

OUT.mkdir(parents=True, exist_ok=True)
profiler = cProfile.Profile(timer=time.process_time)
observer = None
records = []
init_cpu = None
observes = 0


def initialize(payload):
    global observer, init_cpu
    start = time.process_time()
    observer = ObserverAgent(payload, rules_only=True)
    init_cpu = time.process_time() - start


def decide(message, deadline):
    global observes
    if observes >= 20:
        action = {'action': 'finish', 'reason': 'audit profile stops after 20 exposures'}
    else:
        cpu = time.process_time()
        wall = time.monotonic()
        action = profiler.runcall(observer.respond, message['payload'])
        records.append({'sequence': message['decision_sequence'], 'action': action['action'],
                        'cpu_seconds_instrumented': time.process_time() - cpu,
                        'wall_seconds_instrumented': time.monotonic() - wall})
        observes += action['action'] == 'observe'
    return {'protocol_version': PROTOCOL_VERSION, 'message_type': 'decision_response',
            'decision_sequence': message['decision_sequence'], **action}


workflow = V4Workflow(ROOT / 'local-cards/L1')
result = workflow.run(decide, OUT, wallclock_seconds=900, initialize=initialize)
profiler.dump_stats(str(OUT / 'baseline.pstats'))
stream = io.StringIO()
stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative')
stats.print_stats(35)
(OUT / 'profile.txt').write_text(stream.getvalue())
components = []
for (file, line, name), (primitive, calls, own, cumulative, callers) in pstats.Stats(profiler).stats.items():
    if file.endswith(('planner.py', 'agent.py', 'skymath.py')):
        components.append({'file': file, 'line': line, 'function': name, 'calls': calls,
                           'own_cpu_seconds': own, 'cumulative_cpu_seconds': cumulative})
summary = {'kind': 'diagnostic-only, first 20 exposures; cProfile overhead included; no performance score claim',
           'init_cpu_seconds': init_cpu, 'records': records,
           'components': sorted(components, key=lambda x: -x['cumulative_cpu_seconds']),
           'termination_reason': result['termination_reason']}
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'termination': result['termination_reason'], 'observes': observes,
                  'profile': str(OUT / 'profile.txt')}))
