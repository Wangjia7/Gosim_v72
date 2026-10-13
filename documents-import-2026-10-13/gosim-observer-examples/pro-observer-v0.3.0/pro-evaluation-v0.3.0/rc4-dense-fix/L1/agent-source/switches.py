"""Submission switches; defaults preserve the copied v6.1 runtime."""
import json
import math
import os

DEFAULTS = {'V7_WALL':'0', 'V7_WAIT_SKIP':'0', 'V7_API_ASYNC':'0', 'V7_NIGHTPLAN':'on', 'V7_SHORT_API':'1', 'V7_API_POLICY':'legacy', 'V7_MODEL_EFFORT':'auto',
    'V6_DL_HORIZON':'0', 'V6_DL_REQ':'0', 'V6_FAULT_FIX':'0',
    'V6_FAULT_DEEP':'0', 'V6_DL_FLAT':'0', 'V6_DL_FAULT':'0',
    'V7_FREE_POLICY':'v5', 'V7_PAID':'v5', 'V7_SHADOW':'1',
    'V7_FAULT_MH':'0', 'V7_FAULT_U':'off', 'V7_SKILL':'0', 'V7_QA0':'0',
    'V7_SPLIT_EV':'0', 'V6_DL_WEATHER':'0', 'V6_DESI_HA':'0',
    'V6_GROUP_REQUESTS':'0', 'V6_REWARD_SPLIT':'0', 'V6_LP_WEATHER':'0',
    'V6_LP_MOON':'0', 'V6_LP_EVENTS':'0', 'V6_POINT_MODEL':'0'}
VALUES = {k:os.environ.get(k,v) for k,v in DEFAULTS.items()}
WALL = VALUES['V7_WALL'] == '1'
WAIT_SKIP = VALUES['V7_WAIT_SKIP'] == '1'
ASYNC = VALUES['V7_API_ASYNC'] == '1'
NIGHTPLAN = VALUES['V7_NIGHTPLAN']
API_POLICY = VALUES['V7_API_POLICY']
TIERED = ASYNC and API_POLICY == 'tiered'
SHORT_API = VALUES['V7_SHORT_API'] == '1'
FLAT = VALUES['V6_DL_FLAT'] == '1'
FAULT = int(VALUES['V6_FAULT_FIX']) > 0 or VALUES['V6_FAULT_DEEP'] == '1' or FLAT

def number(name, default, minimum=0.0, maximum=math.inf):
    value = float(os.environ.get('V7_'+name, default))
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('invalid V7_'+name)
    return value

NIGHT_WAIT = number('NIGHT_WAIT', 8., 0., 20.)
MODEL_SHARE = number('MODEL_SHARE', .08, 0., .08)
MONITOR_CAP = number('MONITOR_CAP', .1, 0., 1.)
THETA_SCALE = number('THETA_SCALE', 1.)
WAIT_H = number('WAIT_H', 2.5, .01, 24.)
DOWNGRADE_FRAC = number('DOWNGRADE_FRAC', .05, 0., 1.)
UPGRADE_MARGIN = number('UPGRADE_MARGIN', .1, 0., 1.)

def announce(log):
    for k,v in VALUES.items():
        choices = ('legacy','tiered') if k == 'V7_API_POLICY' else ('auto','low','none') if k == 'V7_MODEL_EFFORT' else ('on','shadow','off') if k in ('V7_NIGHTPLAN','V7_FAULT_U') else (
            ('v5','off','deep','ev') if k == 'V7_PAID' else
            ('v5','ev') if k == 'V7_FREE_POLICY' else
            ('0','1','2') if k == 'V6_FAULT_FIX' else ('0','1'))
        if v not in choices:
            raise ValueError('invalid '+k)
    for k in ('V7_FAULT_MH','V7_SKILL','V7_QA0','V7_SPLIT_EV','V6_DL_WEATHER'):
        if VALUES[k] != DEFAULTS[k]:
            raise ValueError(k+' is not implemented; keep disabled')
    if VALUES['V7_FAULT_U'] != 'off' or VALUES['V7_PAID'] == 'ev' or VALUES['V7_FREE_POLICY'] == 'ev':
        raise ValueError('unimplemented fault posterior mode')
    log('v7 switches: '+json.dumps(VALUES,sort_keys=True,separators=(',',':')))
