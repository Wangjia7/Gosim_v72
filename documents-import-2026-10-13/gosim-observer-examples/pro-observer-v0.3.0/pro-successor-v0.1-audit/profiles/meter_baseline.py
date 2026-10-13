"""Observe baseline CPU without modifying its source or protocol actions."""
import json
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, '/Users/jqwang/Documents/gosim-observer-examples/python-pro')
import agent

records = []
original_respond = agent.ObserverAgent.respond


def metered(self, payload):
    before = time.process_time()
    wall = time.monotonic()
    action = original_respond(self, payload)
    records.append({'now_utc': payload['now_utc'], 'action': action['action'],
                    'cpu_seconds': time.process_time() - before,
                    'wall_seconds': time.monotonic() - wall,
                    'speed_factor': payload.get('wallclock', {}).get('speed_factor'),
                    'level': self.planner.fast_level})
    return action


agent.ObserverAgent.respond = metered
try:
    status = agent.main()
finally:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {'kind': 'diagnostic wrapper around unchanged baseline respond; timer overhead excluded from per-call measurements',
              'process_cpu_at_exit': time.process_time(),
              'resource_user_cpu': usage.ru_utime, 'resource_system_cpu': usage.ru_stime,
              'sum_respond_cpu': sum(r['cpu_seconds'] for r in records),
              'sum_respond_wall': sum(r['wall_seconds'] for r in records),
              'sum_cpu_div_snapshot_speed_factor': sum(r['cpu_seconds'] / r['speed_factor'] for r in records if r['speed_factor']),
              'records': records}
    Path(__file__).with_name('baseline-L1-fixed0-metered-cpu.json').write_text(json.dumps(result, indent=2) + '\n')
raise SystemExit(status)
