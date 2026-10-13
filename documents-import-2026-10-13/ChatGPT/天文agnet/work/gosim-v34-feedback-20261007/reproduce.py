"""Reproduce an estimator inconsistency without API calls or scoring truth."""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'work/gosim-logcpu-v34/agent'))
from planner import Planner
from advisor import Advisor

p = Planner.__new__(Planner)
p.bands = {'DARK': .65, 'BRIGHT': .4}
results = []
for ratio in [.002, .01, .05, .2, .7]:
    p.e_ratios = collections.deque([(10., ratio)] * 4)
    p.band_obs = [(10., 1., 'DARK', True, True)] * 4
    max_sky = ratio / .95 * 1.06 ** 30
    results.append({'raw_ratio': ratio, 'minimum_sky_from_band': .65,
                    'search_sky_max': max_sky, 'returned_E': p.clean_e(10.),
                    'inconsistent_all_candidates': max_sky < .65})
    if max_sky < .65:
        assert results[-1]['returned_E'] == 1.  # identifies current defect, not a passing fix

a = Advisor(object())
accepted = a._valid_plan({'bad_night': False, 'hardware_events': [
    {'at_utc': '2027-06-01T18:30:00Z', 'kind': 'guide_camera_work'}]}) is not None
assert not accepted
out = {'description': 'Offline structural reproductions; not replayed platform payloads. No API calls.',
       'clean_e': results, 'operator_hardware_schema_accepts': accepted}
(ROOT / 'outputs/gosim-v34-feedback/structural-reproductions.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
