"""Authorized tiny synthetic probes of the unmodified attachment; no cards/API/main."""
import sys,math,json,time,platform,hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
SOURCE=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()/'work/incoming/improved-source'
sys.dont_write_bytecode=True
source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.glob('*.py')}
sys.path.insert(0,str(SOURCE))
import planner as module
from planner import Planner
from skymath import (FiberGrid,altaz_to_radec,shift_altaz,tangent_offsets,local_sidereal_deg,
                     max_hour_angle_deg,SIDEREAL_DEG_PER_SECOND,separation_deg)
NOW=datetime(2026,10,7,tzinfo=timezone.utc);END=NOW+timedelta(hours=4);LST=local_sidereal_deg(NOW,0)
def fixture(coords=None,minimum=60,maximum=3600,required=False):
 if coords is None:coords=[altaz_to_radec(60,180,LST,30)]
 glass=math.sqrt(.4)
 return {'site':{'latitude_deg':30,'longitude_deg':0,'minimum_altitude_deg':20},
  'survey':{'start_utc':NOW.isoformat(),'end_utc':END.isoformat(),'slot_seconds':300,
   'nights':[{'night_date':'2026-10-07','observing_start_utc':NOW.isoformat(),'observing_end_utc':END.isoformat()}]},
  'instrument':{'grid_side':4,'n_fibers':16,'glass_side_deg':glass,'pitch_deg':glass,'fov_side_deg':4*glass,
   'exposure':{'min_duration_seconds':minimum,'max_duration_seconds':maximum}},
  'scoring':{'flux_zero_point':1,'exposure_zero_point_seconds':1000,'q0':1,'airmass_exponent':1,
   'required':{'observed_factor_threshold':.6,'penalty_per_missing':50},
   'program':{'bands':{'DARK':.8,'BRIGHT':.4},'multipliers':{'DARK':1.2,'BRIGHT':1,'BACKUP':.8},'mismatch_multiplier':1},
   'lunar_model':{'maximum_penalty':0,'altitude_exponent':1,'angular_decay_scale_deg':30}},
  'targets':{'columns':['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'],
   'rows':[[f'T{i}',r,d,100,10,required] for i,(r,d) in enumerate(coords)]}}
results=[];started=time.process_time()
def add(case,**fields):results.append({'case':case,**fields})
# Exact geometry is legal; incomplete anchor query excludes the opposite corner.
grid=FiberGrid(fixture()['instrument']);points=[shift_altaz(60,30,*grid.fiber_center(f)) for f in (0,15)]
coords=[altaz_to_radec(a,z,LST,30) for a,z in points];p=Planner(fixture(coords=coords))
add('opposite_corner_query',radius=p.neighbour_radius,separation=separation_deg(*coords[0],*coords[1]),
    exact_fibers=[grid.classify(*tangent_offsets(a,z,60,30))[0] for a,z in points],
    anchor_query=p.neighbours(*coords[0],p.neighbour_radius),expected_anchor_targets=[0,1])
# Fix the same single-anchor candidate, compare only the candidate radius parameter.
saved=(module.N_ANCHORS,module.N_DENSE)
module.N_ANCHORS,module.N_DENSE=1,0
cfg=fixture(coords=coords);cfg['targets']['rows'][0][4]=100
for radius in (p.neighbour_radius,3.5):
 q=Planner(cfg);q.neighbour_radius=radius
 action=q.plan(NOW,END,0,0)
 add('single_anchor_radius_control',radius=radius,action=action)
module.N_ANCHORS,module.N_DENSE=saved
# A shifted center can legitimately acquire a target outside its original anchor neighborhood.
shifted=shift_altaz(60,30,.6,.6)
p2=shift_altaz(*shifted,*grid.fiber_center(15));shiftcoords=[coords[0],altaz_to_radec(*p2,LST,30)]
p=Planner(fixture(coords=shiftcoords))
add('shifted_center_query',exact_shift_fiber=grid.classify(*tangent_offsets(*p2,*shifted))[0],
    anchor_query=p.neighbours(*shiftcoords[0],p.neighbour_radius),
    fresh_center_query=p.neighbours(*altaz_to_radec(*shifted,LST,30),p.neighbour_radius))
# Best score cannot determine raw completion under unknown program multipliers.
p=Planner(fixture(required=True));p.factor[0]=.61;p.cur[0]=.61
p._resync({'best_scores':[{'target_id':'T0','best_score':6.1}],'observed_target_ids':['T0']})
add('required_factor_resync',known_possible_raw_factor=.61,configured_threshold=.6,
    factor_after_resync=p.factor[0],required_threshold_attribute=getattr(p,'required_threshold',None),
    correct_required_satisfied=True)
p=Planner(fixture(required=True));p._resync({'best_scores':[{'target_id':'T0','best_score':6.6}]})
add('configured_required_threshold',factor_after_resync=p.factor[0],configured_threshold=.6,
    actual_factor_for_matching_dark=.55,required_is_unsatisfied=True,
    gain_branch_considers_unsatisfied=(p.factor[0]<.5),planner_value=p.value(0))
# Legal short opportunities are removed by the fixed 600-second prefilter.
for span in (100,450):
 ha=max_hour_angle_deg(0,30,20.6);coord=[((LST-(ha-span*SIDEREAL_DEG_PER_SECOND))%360,0)]
 p=Planner(fixture(coords=coord));a=p.plan(NOW,END,0,0)
 old=module.MIN_VISIBLE_SECONDS;module.MIN_VISIBLE_SECONDS=60
 control=Planner(fixture(coords=coord,minimum=60,maximum=90)).plan(NOW,END,0,0)
 module.MIN_VISIBLE_SECONDS=old
 add('short_visibility',seconds_above_safety=span,action=a,short_grid_control=control)
# The geometry precheck accepts 600 sec although the only declared exposure is 900 sec.
for deadline in (600,899,900,901):
 p=Planner(fixture(minimum=900,maximum=900));r={'request_id':'R','issued_at_utc':NOW.isoformat(),
  'deadline_utc':(NOW+timedelta(seconds=deadline)).isoformat(),'target_ids':['T0'],'minimum_completed':1,
  'remaining_count':1,'completed_target_ids':[],'completion_factor_threshold':.5,'completion_reward':100}
 p.on_requests([r],NOW);a=p.plan(NOW,END,0,0)
 add('request_interval',deadline_seconds=deadline,action=a,request_proxy=p.request_bonus,
     selected_utility=p.last_plan_gain,official_interval_credit_possible=(a is not None and a['duration_seconds']<=deadline))
p=Planner(fixture());p.season.update([0],0,force=True);r0=p.season.ratio
p.season.update([.8],0,force=True);r8=p.season.ratio
add('replacement_cost',demand_supply_factor0=r0,demand_supply_factor08=r8,
    remaining_cost_ratio=r8/r0,correct_full_replacement_cost_ratio=1,
    desi_design=p.season.desi_design)
# Default optional flags leave same-night season cache intact after a correction.
p=Planner(fixture());p.plan(NOW,END,0,0);old=p.season.price[:]
p._resync({'best_scores':[{'target_id':'T0','best_score':8}]})
p.plan(NOW+timedelta(seconds=60),END,0,1/60)
add('same_night_resync_dirty',season_enabled=p.season is not None,long_dirty=p.long_dirty,
    season_night=p.season_night,price_unchanged=(old==p.season.price),expected_allocation_dirty=True)
print(json.dumps({'source':str(SOURCE),'native_process_cpu_seconds':time.process_time()-started,
                 'planner_module':module.__file__,'python_version':platform.python_version(),'machine':platform.machine(),
                 'source_hashes_before':source_hashes,
                 'source_unchanged':source_hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.glob('*.py')},
                 'results':results},indent=2))
