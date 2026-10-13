#!/usr/bin/env python3
"""Synthetic dense-catalogue/low-budget protocol stress test for v72.

Tests only action legality, fiber utilization, latency and graceful degradation.
Does NOT reproduce the GOSIM simulator or official survey scores.
"""
import json, os, sys, pathlib, random, time, subprocess, resource, math, argparse

parser=argparse.ArgumentParser()
parser.add_argument('source', type=pathlib.Path)
parser.add_argument('--runs', type=int, default=1)
parser.add_argument('--include-emergency',action='store_true',help='also test the near-exhausted-budget wait/degradation branch')
args=parser.parse_args()
src=args.source.resolve()
sys.path.insert(0, str(src))
from skymath import local_sidereal_deg, parse_utc
start='2026-10-05T18:00:00Z'
ra=local_sidereal_deg(parse_utc(start), 0.)

config=json.loads((src/'observer.project.json').read_text())
env=os.environ.copy();env.update(config.get('environment',{}));env['OBSERVER_MODEL_DISABLED']='1';env['PYTHONDONTWRITEBYTECODE']='1'

# Temporal squeeze: 25, 14, or 8 minutes, with up to 10,000 targets.
# Separate from the CPU/wall-time squeeze, which is declared to the agent's wallclock block.
CASES=[
    # (n_targets, minutes_left_in_night, remaining_CPU_s, remaining_WALL_s, seed)
    (1000, 25, 60, 900, 5),
    (5000, 25, 30, 450, 5),
    (10000, 14, 20, 150, 5),
    (10000, 8, 20, 150, 5),
]

if args.include_emergency:
    CASES.append((10000,14,0.40,104,5))

def init_case(n,night_min, seed):
    rng=random.Random(seed)
    # 10x10 fibre layout with a dense, observable RA/Dec patch near the local meridian.
    rows=[]
    for i in range(n):
        dx=rng.uniform(-1.18, 1.18)
        dy=rng.uniform(-1.18, 1.18)
        rows.append([f'X{i:05}',(ra+dx)%360.,30.+dy, 18.+rng.random()*5,4.+rng.random()*8,int(i%17==0)])
    from datetime import timedelta
    end=(parse_utc(start)+timedelta(minutes=night_min)).isoformat().replace('+00:00','Z')
    return {
      'site': {'latitude_deg':30., 'longitude_deg':0., 'minimum_altitude_deg':20., 'utc_offset_hours':0.},
      'survey': {'start_utc':start,'end_utc':end,
                 'nights':[{'observing_start_utc':start,'observing_end_utc':end,'night_date':'2026-10-05'}],
                 'slot_seconds':300},
      'instrument':{'grid_side':10,'n_fibers':100,'glass_side_deg':0.23,'pitch_deg':0.24,
                    'fov_side_deg':2.52,
                    'exposure':{'min_duration_seconds':300,'max_duration_seconds':3600}},
      'targets':{'columns':['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'],'rows':rows},
      'scoring':{'flux_zero_point':10., 'exposure_zero_point_seconds':600., 'q0':1.,
                 'airmass_exponent':1.,'program':{'bands':{'DARK':0.65,'BRIGHT':0.40},
                 'multipliers':{'DARK':1.2,'BRIGHT':1.12,'BACKUP':1.06},'mismatch_multiplier':1.},
                 'lunar_model':{'maximum_penalty':0.2,'altitude_exponent':1.,'angular_decay_scale_deg':50.},
                 'required':{'observed_factor_threshold':0.5},
                 'reporting':{'false_report_free_allowance':2}}
    }

def run_case(n, minute, cpu, wall, seed):
    init=init_case(n,minute,seed)
    msg=[{'protocol_version':'participant-agent-protocol-v4','message_type':'initialize','payload':init},
         {'protocol_version':'participant-agent-protocol-v4','message_type':'decision_request','decision_sequence':1,
          'payload':{'now_utc':start,'new_messages':[], 'active_requests':[], 'latest_bulletin':{'notices':[]},
                     'last_result':None,'wallclock':{'remaining_real_cpu_seconds':cpu,
                     'wall_remaining_seconds':wall}}},
         {'protocol_version':'participant-agent-protocol-v4','message_type':'finish','payload':{'termination_reason':'synthetic-stress-test'}}]
    data='\n'.join(json.dumps(m,ensure_ascii=False,separators=(',',':')) for m in msg)+'\n'
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    t0=time.perf_counter()
    try:
        p=subprocess.run(config['run'],cwd=src,env=env,input=data,text=True,capture_output=True,timeout=30)
    except subprocess.TimeoutExpired as e:
        return {'n_targets':n,'night_min':minute,'cpu_budget_claim_s':cpu,'wall_budget_claim_s':wall,'error':'timeout>30s'}
    elapsed=time.perf_counter()-t0
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    used=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
    rows=[json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    err={'n_targets':n,'night_min':minute,'cpu_budget_claim_s':cpu,'wall_budget_claim_s':wall,
      'process_cpu_s':round(used,3),'process_wall_s':round(elapsed,3),'exit_code':p.returncode}
    if not rows:
        return err|{'error':p.stderr[-700:]}
    a=rows[0]
    err['action']=a.get('action');err['reason']=a.get('reason')
    err['source']=a.get('decision_source')
    err['warnings']=[l for l in p.stderr.splitlines() if any(k in l for k in ('pace level','v7 wall','v5: error','initialize failed'))][-5:]
    if a.get('action')=='observe':
        ass=a.get('assignments',{});m=int(a.get('duration_seconds',0))
        ids=[r[0] for r in init['targets']['rows']]
        legal=len(ass)==len(set(ass))==len(set(ass.values())) and len(ass)<=100 and all(i in ids for i in ass.values()) and 300<=m<=min(3600, minute*60) and all(str(k).isdigit() and 0<=int(k)<100 for k in ass)
        # Independent focal-grid sanity check using the same sky-coordinate convention.
        from skymath import radec_to_altaz
        c_alt=float(a['pointing']['alt_deg']); c_az=float(a['pointing']['az_deg'])
        legal=legal and 20<=c_alt<=90 and 0<=c_az<360
        a0,z0=math.radians(c_alt),math.radians(c_az)
        n0=(-math.sin(a0)*math.cos(z0),-math.sin(a0)*math.sin(z0),math.cos(a0))
        e0=(-math.sin(z0),math.cos(z0),0.)
        f0=(math.cos(a0)*math.cos(z0),math.cos(a0)*math.sin(z0),math.sin(a0))
        sky={r[0]:r for r in init['targets']['rows']}
        geometry_ok=True
        for fiber, target in ass.items():
            tr=sky[target]
            alt,az=radec_to_altaz(tr[1],tr[2],ra,30.)
            aa,zz=math.radians(alt),math.radians(az)
            v=(math.cos(aa)*math.cos(zz),math.cos(aa)*math.sin(zz),math.sin(aa))
            depth=sum(x*y for x,y in zip(v,f0))
            dn=math.degrees(sum(x*y for x,y in zip(v,n0))/depth)
            de=math.degrees(sum(x*y for x,y in zip(v,e0))/depth)
            row,col=divmod(int(fiber),10)
            center=4.5
            # The planner models a probabilistic (not guaranteed) fibre hit under initial pointing uncertainty.
            xn=dn-(row-center)*.24;xe=de-(col-center)*.24
            hgf=.115-.002
            az_half=.04*math.cos(a0)
            def overlap(x,lo,hi):
                return max(0.,min(hi,x+hgf)-max(lo,x-hgf))/(hi-lo) if hi-lo>1e-8 else float(abs(x)<=hgf)
            p=overlap(xn,-.02,.02)*overlap(xe,-az_half,az_half)
            if p < .3-1e-5:
                geometry_ok=False
                err['first_geometry_mismatch']={'fiber':fiber,'dn':round(dn,5),'de':round(de,5),'p':round(p,4),'alt_az':a['pointing']}
                break
        legal=legal and geometry_ok
        err['geometry_ok']=geometry_ok
        err.update({'assigned_fibers':len(ass),'fiber_utilization':round(len(ass)/100,3),
                    'exposure_seconds':m,'valid_protocol_action':legal,'program':a.get('program')})
    else:
        err['valid_protocol_action']=(a.get('action') in ('wait','finish') and (a.get('action') != 'wait' or bool(a.get('until_utc') or a.get('duration_seconds'))))
    return err

for n,minute,cpu,wall,seed in CASES:
    for s in range(args.runs):
        result=run_case(n,minute,cpu,wall,seed+s)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if result.get('error') or result.get('exit_code') not in (0,) or not result.get('valid_protocol_action'):
            sys.exit(2)
