"""Synthetic public protocol fixtures; no card or judge truth is imported."""
import math
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skymath import altaz_to_radec, local_sidereal_deg
NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
END = NOW + timedelta(hours=4)
LST = local_sidereal_deg(NOW, 0)
def fixture(coords=None, side=4, minimum=60, maximum=3600, flux=100, required=True, gap=0):
    if coords is None:
        coords = [altaz_to_radec(60, 180, LST, 30)]
    glass = math.sqrt(.4)
    pitch = glass + gap
    return {'site': {'latitude_deg':30, 'longitude_deg':0, 'minimum_altitude_deg':20},
      'survey': {'start_utc':NOW.isoformat(), 'end_utc':END.isoformat(), 'slot_seconds':300,
        'nights':[{'observing_start_utc':NOW.isoformat(), 'observing_end_utc':END.isoformat()}]},
      'instrument': {'grid_side':side, 'n_fibers':side*side, 'glass_side_deg':glass, 'pitch_deg':pitch,
        'fov_side_deg':side*glass+(side-1)*gap,
        'exposure':{'min_duration_seconds':minimum, 'max_duration_seconds':maximum}},
      'scoring': {'flux_zero_point':1, 'exposure_zero_point_seconds':1000, 'q0':1, 'airmass_exponent':1,
        'program':{'bands':{'DARK':.8,'BRIGHT':.4}, 'multipliers':{'DARK':1.2,'BRIGHT':1,'BACKUP':.8}, 'mismatch_multiplier':.5},
        'lunar_model':{'maximum_penalty':0,'altitude_exponent':1,'angular_decay_scale_deg':30}},
      'targets':{'columns':['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'],
        'rows':[[f'T{i}',r,d,flux,10,required] for i,(r,d) in enumerate(coords)]}}
def request(ids=('T0',), threshold=.5, reward=40, remaining=1, start=NOW, deadline=None):
    return {'request_id':'R', 'target_ids':list(ids), 'minimum_completed':remaining, 'remaining_count':remaining,
      'completed_target_ids':[], 'completion_factor_threshold':threshold, 'completion_reward':reward,
      'issued_at_utc':start.isoformat(), 'deadline_utc':(deadline or NOW+timedelta(seconds=600)).isoformat()}
