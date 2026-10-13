"""Read-only synthetic regression probes; imports original baseline without bytecode writes."""
import sys, os, math, json, time
os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.dont_write_bytecode=True
sys.path.insert(0,'/Users/jqwang/Documents/gosim-observer-examples/python-pro')
import planner as mod
from planner import Planner
from skymath import *
from datetime import datetime,timedelta,timezone
NOW=datetime(2026,10,7,0,0,tzinfo=timezone.utc)
LST=local_sidereal_deg(NOW,0)
def fixture(coords=None, side=4, minimum=300,maximum=3600, flux=100):
    if coords is None: coords=[altaz_to_radec(60,180,LST,30)]
    return {'site':{'latitude_deg':30,'longitude_deg':0,'minimum_altitude_deg':20},
      'survey':{'nights':[{'observing_start_utc':NOW.isoformat(),'observing_end_utc':(NOW+timedelta(hours=4)).isoformat()}], 'end_utc':(NOW+timedelta(hours=4)).isoformat(),'slot_seconds':300},
      'instrument':{'grid_side':side,'n_fibers':side*side,'glass_side_deg':round(math.sqrt(.4),6),'pitch_deg':round(math.sqrt(.4),6),'fov_side_deg':round(side*math.sqrt(.4),6),'exposure':{'min_duration_seconds':minimum,'max_duration_seconds':maximum}},
      'scoring':{'flux_zero_point':1,'exposure_zero_point_seconds':1000,'q0':1,'airmass_exponent':1,'program':{'bands':{'DARK':.8,'BRIGHT':.4},'multipliers':{'DARK':1.2,'BRIGHT':1,'BACKUP':.8},'mismatch_multiplier':.5},'lunar_model':{'maximum_penalty':0,'altitude_exponent':1,'angular_decay_scale_deg':30}},
      'targets':{'columns':['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'],'rows':[[f'T{i}',r,d,flux,10,True] for i,(r,d) in enumerate(coords)]}}
def plan_case(label,**kw):
    p=Planner(fixture(**kw)); start=time.process_time(); action=p.plan(NOW,NOW+timedelta(hours=4),0,0)
    return {'case':label,'action':action,'cpu_ms':round(1000*(time.process_time()-start),3)}
results=[]
results.append(plan_case('configured_min_1000',minimum=1000))
results.append(plan_case('configured_max_200',minimum=100,maximum=200,flux=.1))
# Construct target that crosses planner's altitude safety limit in exactly 450 seconds.
ha_end=max_hour_angle_deg(0,30,20.6)
coords=[((LST-(ha_end-450*SIDEREAL_DEG_PER_SECOND))%360,0)]
p=Planner(fixture(coords=coords,minimum=100,maximum=3600)); start=time.process_time()
a=p.plan(NOW,NOW+timedelta(hours=4),0,0)
alt0=radec_to_altaz(*coords[0],LST,30)[0]; alt200=radec_to_altaz(*coords[0],LST+200*SIDEREAL_DEG_PER_SECOND,30)[0]
results.append({'case':'450sec_window','start_alt':alt0,'alt_after_200sec':alt200,'action':a,'cpu_ms':round(1000*(time.process_time()-start),3)})
old_cutoff=mod.MIN_VISIBLE_SECONDS
mod.MIN_VISIBLE_SECONDS=100
p=Planner(fixture(coords=coords,minimum=100,maximum=3600))
results.append({'case':'450sec_window_cutoff100_control','action':p.plan(NOW,NOW+timedelta(hours=4),0,0)})
mod.MIN_VISIBLE_SECONDS=old_cutoff
results.append(plan_case('2x2_level0_control',side=2))
# 2x2 reduced search uses synthetic out-of-range fiber 5; may or may not capture target.
p=Planner(fixture(side=2)); p.fast_level=3; a=p.plan(NOW,NOW+timedelta(hours=4),0,0)
results.append({'case':'2x2_level3','n_fibers':p.grid.n,'anchor_fiber':5,'anchor_offset':p.grid.fiber_center(5),'action':a})
# Same legal field has opposite-corner targets; anchor query misses other target.
grid=FiberGrid(fixture()['instrument']); ca,cz=60,30
points=[shift_altaz(ca,cz,*grid.fiber_center(f)) for f in [0,15]]
coords=[altaz_to_radec(a,z,LST,30) for a,z in points]; p=Planner(fixture(coords=coords))
results.append({'case':'opposite_corner_geometry','separation_deg':separation_deg(*coords[0],*coords[1]),'declination_difference_deg':abs(coords[0][1]-coords[1][1]),'radius_deg':mod.NEIGHBOUR_RADIUS_DEG,'query_from_anchor0':p.neighbours(*coords[0],mod.NEIGHBOUR_RADIUS_DEG),'exact_classifications':[grid.classify(*tangent_offsets(a,z,ca,cz)) for a,z in points]})
# Controlled single-anchor search isolates candidate pruning from other seed routes.
saved=(mod.N_ANCHORS,mod.N_DENSE,mod.NEIGHBOUR_RADIUS_DEG)
mod.N_ANCHORS,mod.N_DENSE=1,0
for radius in (2.1,3.5):
    mod.NEIGHBOUR_RADIUS_DEG=radius
    init=fixture(coords=coords); init['targets']['rows'][0][4]=100
    p=Planner(init); start=time.process_time(); a=p.plan(NOW,NOW+timedelta(hours=4),0,0)
    results.append({'case':'single_anchor_radius_control','radius':radius,'action':a,'cpu_ms':round(1000*(time.process_time()-start),3)})
mod.N_ANCHORS,mod.N_DENSE,mod.NEIGHBOUR_RADIUS_DEG=saved
# Official L1 program config: mismatch 1.0, DARK top multiplier 1.2.
with open('/Users/jqwang/Documents/gosim-observer-examples/local-cards/L1/config/v4_score_config.json') as fh:
    official_score=json.load(fh)
init=fixture(); init['scoring']['program']=official_score['program']
p=Planner(init); p.factor[0]=.55; p.cur[0]=.55
p._resync({'best_scores':[{'target_id':'T0','best_score':5.5}],'observed_target_ids':['T0']})
results.append({'case':'resync_default_mismatch_factor','known_history_factor':.55,'mismatch_multiplier':1.0,'top_multiplier':1.2,'score':5.5,'resynced_factor':p.factor[0],'resynced_cur':p.cur[0],'crosses_required_threshold':p.factor[0]<.5})
# Official validator permits these alternate layouts and exposure bounds.
sys.path.insert(0,'/Users/jqwang/Documents/gosim-observer-examples')
from runner.challenge.v4_config_check import validate_fiber_config
for side,low,high in [(2,60,3600),(4,1000,3600),(4,100,200)]:
    cfg={'field':{'n_fibers':side*side,'fiber_area_deg2':.4,'gap_deg':0},'exposure':{'min_duration_seconds':low,'max_duration_seconds':high}}
    validate_fiber_config(cfg)
    results.append({'case':'official_config_validation','n_fibers':side*side,'minimum':low,'maximum':high,'accepted':True})
# Level4 still searches; exhaustion triggering inspected separately.
p=Planner(fixture()); p.fast_level=4; start=time.process_time(); a=p.plan(NOW,NOW+timedelta(hours=4),0,0)
results.append({'case':'level4','action':a,'cpu_ms':round(1000*(time.process_time()-start),3)})
print(json.dumps(results,indent=2))
