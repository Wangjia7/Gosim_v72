import copy
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR=Path(os.environ.get('PRO_TEST_AGENT', str(ROOT/'agent')))
sys.path.insert(0, str(AGENT_DIR))
from official_pro import planner as module
from official_pro.planner import Planner
from official_pro.agent import ObserverAgent
from official_pro.skymath import format_utc, local_sidereal_deg, shift_altaz, altaz_to_radec, tangent_offsets
from routing import initial_route

def fixture(side=4):
    score=json.loads((ROOT.parent/'gosim-desi-v300/fixtures/official-config/v4_score_config.json').read_text())
    now=datetime(2026,11,2,1,tzinfo=timezone.utc); end=now+timedelta(hours=6)
    glass=math.sqrt(.4)
    data={'site':{'latitude_deg':31,'longitude_deg':-70.3976,'minimum_altitude_deg':30},
        'survey':{'start_utc':format_utc(now),'end_utc':format_utc(end),'slot_seconds':900,
          'nights':[{'observing_start_utc':format_utc(now),'observing_end_utc':format_utc(end)}]},
        'instrument':{'n_fibers':side*side,'grid_side':side,'fiber_area_deg2':.4,'gap_deg':0,
          'glass_side_deg':glass,'pitch_deg':glass,'fov_side_deg':side*glass,
          'exposure':{'min_duration_seconds':60,'max_duration_seconds':3600}},'scoring':score,
        'targets':{'columns':['target_id','ra_deg','dec_deg','target_class','feature_flux','science_weight','required'],'rows':[]}}
    lst=local_sidereal_deg(now,data['site']['longitude_deg'])
    for k,f in enumerate((5,6) if side==4 else (0,)):
        a,z=shift_altaz(55,100,*module.FiberGrid(data['instrument']).fiber_center(f))
        ra,dec=altaz_to_radec(a,z,lst,31)
        data['targets']['rows'].append([f't{k}',ra,dec,'Star',.8,2,False])
    return data

def observe_result(p, index, scores):
    now=p.nights[0][0]
    p.plan(now,p.nights[0][1],0,0)
    p.on_result({'action':'observe','observe_index':index,'hits':[
      {'target_id':t,'score':s} for t,s in scores.items()]},now+timedelta(seconds=p.pending_duration),index)

class Tests(unittest.TestCase):
    def test_program_uses_marginal_scores(self):
        d=fixture();d['scoring']['q0']=1
        d['instrument']['exposure']={'min_duration_seconds':900,'max_duration_seconds':900}
        for row,reach,q,w in zip(d['targets']['rows'],(.6,1),(.7,.55),(10,4)):
            row[4]=reach*450/(900*q*.97);row[5]=w
        qa={d['targets']['rows'][i][1]:q for i,q in enumerate((.7,.55))}
        class Moon:
            def __init__(self,*args):pass
            def lunar_factor(self,ra,dec):return qa[ra]
        with patch.object(module,'Moon',Moon),patch.object(module,'normalized_airmass',lambda _:1):
            p=Planner(d);p.cur=[.715,0];p.factor=[.5958333,0];p.lambda_frac=0
            a=p.plan(p.nights[0][0],p.nights[0][1],0,0)
        self.assertEqual(a['program'],'BRIGHT')
        self.assertIn('t1',a['assignments'].values())

    def test_request_deadline_and_reward_cap(self):
        d=fixture();d['targets']['rows']=d['targets']['rows'][:1]
        p=Planner(d);now=p.nights[0][0]
        p.on_requests([{'request_id':'r','issued_at_utc':format_utc(now),'deadline_utc':format_utc(now+timedelta(seconds=300)),
            'target_ids':['t0'],'minimum_completed':1,'completion_factor_threshold':.5,'completion_reward':30}])
        a=p.plan(now,p.nights[0][1],0,0)
        self.assertLessEqual(a['duration_seconds'],300)
        self.assertIn('t0',a['assignments'].values())
    def test_expired_or_impossible_request_has_no_bonus(self):
        p=Planner(fixture());now=p.nights[0][0]
        p.on_requests([{'request_id':'r','issued_at_utc':format_utc(now),'deadline_utc':format_utc(now+timedelta(seconds=10)),
            'target_ids':['t0'],'minimum_completed':1,'completion_factor_threshold':.5,'completion_reward':30}])
        p.plan(now,p.nights[0][1],0,0);self.assertEqual(p.request_bonus,{})
    def test_request_progress_zero_is_not_reactivated(self):
        p=Planner(fixture());now=p.nights[0][0]
        p.on_requests([{'request_id':'r','deadline_utc':format_utc(now+timedelta(hours=1)),
            'target_ids':['t0'],'minimum_completed':1,'remaining_count':0,'completion_factor_threshold':.5,'completion_reward':30}])
        self.assertEqual(p.requests,[]);self.assertEqual(p.request_bonus,{})
    def test_future_rising_request_target_cannot_break_current_search(self):
        d=fixture();now=module.parse_utc(d['survey']['start_utc'])
        d['targets']['rows'][1][1]=(local_sidereal_deg(now,d['site']['longitude_deg'])+100)%360
        p=Planner(d)
        p.on_requests([{'request_id':'future','issued_at_utc':format_utc(now),
            'deadline_utc':format_utc(now+timedelta(hours=6)), 'target_ids':['t1'],
            'minimum_completed':1,'completion_factor_threshold':.5,'completion_reward':30}])
        self.assertIsNotNone(p.plan(now,p.nights[0][1],0,0))
    def test_geometry_full_neighbourhood_contains_opposite_cell(self):
        d=fixture();p=Planner(d);lst=local_sidereal_deg(p.nights[0][0],p.lon)
        rows=[]
        for f in (0,15):
            a,z=shift_altaz(55,15,*p.grid.fiber_center(f));ra,dec=altaz_to_radec(a,z,lst,31)
            rows.append([str(f),ra,dec,'Star',1,2,False])
        d['targets']['rows']=rows;p=Planner(d)
        radius=math.sqrt(2)*p.grid.fov+module.REFINE_ROUNDS*module.REFINE+.1
        self.assertIn(0,p.neighbours(p.ra[1],p.dec[1],radius))
    def test_required_bound_and_runtime_threshold(self):
        d=fixture();d['scoring']['required']['observed_factor_threshold']=.7;d['scoring']['required']['penalty_per_missing']=80
        p=Planner(d);observe_result(p,0,{'t0':2*.69*1.2})
        self.assertLess(p.factor_lower[0],.7);self.assertAlmostEqual(p.required_bonus,128)
        self.assertGreaterEqual(p.factor[0],p.factor_lower[0])
    def test_unknown_program_factor_lower_is_independent_of_estimate(self):
        p=Planner(fixture());p.pending={'t0':{'model':1,'band_model':1,'alt':55,'az':100,
            'dir_clean':True,'pred':.6,'fiber':5}}
        p.pending_program='DARK';p.pending_duration=900;p.pending_cmd=(55,100)
        p.on_result({'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':1.2}]},p.nights[0][0],0)
        self.assertLessEqual(p.factor_lower[0],.5)
        self.assertGreaterEqual(p.factor[0],p.factor_lower[0])
    def test_raw_factor_and_science_best_replay_separately(self):
        p=Planner(fixture());now=p.nights[0][0]
        for index,program,score in [(0,'DARK',2*.8*1.2),(1,'BACKUP',2*.9*1.06)]:
            p.pending={'t0':{'model':1,'band_model':1,'alt':55,'az':100,'dir_clean':True,'pred':.9,'fiber':5}}
            p.pending_program=program;p.pending_duration=900;p.pending_cmd=(55,100)
            p.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'t0','score':score}]},now,index)
        p._resync({'invalidated_window':{'action_index_start':0,'action_index_end_exclusive':0},
            'best_scores':[{'target_id':'t0','best_score':2*.8*1.2}]})
        self.assertAlmostEqual(p.cur[0],.96)
        self.assertAlmostEqual(p.factor_lower[0],.9,places=6)
    def test_repair_epoch_does_not_resurrect_old_calibration(self):
        p=Planner(fixture());observe_result(p,0,{'t0':.6,'t1':.6});p.forget_quality_history()
        observe_result(p,1,{'t0':.8,'t1':.8})
        p._resync({'invalidated_window':{'action_index_start':1,'action_index_end_exclusive':2},
            'best_scores':[{'target_id':'t0','best_score':.6},{'target_id':'t1','best_score':.6}]})
        self.assertEqual(len(p.all_ratios),0);self.assertEqual(len(p.offset_evidence),0)
        self.assertAlmostEqual(p.cur[0],.3)
    def test_best_exposure_does_not_sum(self):
        p=Planner(fixture());observe_result(p,0,{'t0':.4});observe_result(p,1,{'t0':.5})
        self.assertAlmostEqual(p.cur[0],.25)
        self.assertLessEqual(p.factor_lower[0],.25)
    def test_data_loss_removes_learning_and_factor_contributions(self):
        p=Planner(fixture());observe_result(p,0,{'t0':.6,'t1':.6});observe_result(p,1,{'t0':.8,'t1':.8})
        p._resync({'invalidated_window':{'action_index_start':0,'action_index_end_exclusive':1},
            'best_scores':[{'target_id':'t0','best_score':.8},{'target_id':'t1','best_score':.8}]})
        self.assertEqual(len(p.offset_evidence),1)
        self.assertTrue(all(h==1 for h,_ in p.samples));self.assertEqual(len(p.all_ratios),2)
        self.assertAlmostEqual(p.cur[0],.4)
        self.assertLessEqual(p.factor_lower[0],.4)
    def test_duplicate_result_not_recorded_twice(self):
        p=Planner(fixture());observe_result(p,0,{'t0':.4})
        p.on_result({'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':.4}]},p.nights[0][0],1)
        self.assertEqual(len(p.history),1)
    def test_duration_never_exceeds_instrument_limit(self):
        d=fixture();d['instrument']['exposure']={'min_duration_seconds':60,'max_duration_seconds':210}
        p=Planner(d);a=p.plan(p.nights[0][0],p.nights[0][1],0,0)
        self.assertGreaterEqual(a['duration_seconds'],60);self.assertLessEqual(a['duration_seconds'],210)
    def test_geometry_windows_require_entire_exposure(self):
        p=Planner(fixture());now=p.nights[0][0].timestamp();p.opportunities.cache[0]=[(now,now+800),(now+900,now+1600)]
        self.assertEqual(p.opportunities.remaining(0,now,duration=750)[1],1)
        self.assertEqual(p.opportunities.remaining(0,now,duration=801)[1],0)
    def test_cpu_attribution_uses_actual_level(self):
        a=ObserverAgent.__new__(ObserverAgent);a.planner=types.SimpleNamespace(fast_level=0)
        a.turn_end=None;a.model_wait=0;a.cost_ema=[0.0]*4;a.wall_ema=[0.0]*4
        def respond(_):a.planner.fast_level=2;return {'action':'observe'}
        a._respond=respond
        with patch('time.process_time',side_effect=[10,10.09]),patch('time.monotonic',side_effect=[100,100.1,100.1]):a.respond({})
        self.assertEqual(a.cost_ema[0],0);self.assertAlmostEqual(a.cost_ema[2],.09)
    def test_earthquake_does_not_erase_independent_band_evidence(self):
        a=ObserverAgent(fixture(),rules_only=True);p=a.planner;now=p.nights[0][0]
        p.plan(now,p.nights[0][1],0,0)
        payload={'now_utc':format_utc(now+timedelta(seconds=p.pending_duration)),
            'last_result':{'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':.6}]},
            'active_requests':[], 'new_messages':[{'record_type':'bulletin','notices':[{'event_kind':'earthquake','direction':'ALL'}]}],
            'latest_bulletin':{'notices':[{'event_kind':'earthquake','direction':'ALL'}]},
            'wallclock':{'remaining_real_cpu_seconds':1000,'wall_remaining_seconds':1000}}
        a.respond(payload)
        self.assertTrue(p.history[0]['pending']['t0']['dir_clean'])
    def test_native_and_python_choose_same_action(self):
        import native
        if native.LIB is None:self.skipTest('compiler unavailable')
        actions=[]
        for lib in (native.LIB,None):
            with patch.object(module,'LIB',lib):
                p=Planner(fixture());actions.append(p.plan(p.nights[0][0],p.nights[0][1],0,0))
        self.assertEqual(actions[0],actions[1])
    def test_jsonl_missing_key_and_duplicate_sequence(self):
        d=fixture();msgs=[{'message_type':'initialize','payload':d},
          {'message_type':'decision_request','decision_sequence':7,'payload':{'now_utc':d['survey']['start_utc'],
            'new_messages':[],'active_requests':[],'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
        msgs.append(msgs[-1]);env={**os.environ,'PRO_FIXED_LEVEL':'0'}
        for k in ('OPENAI_API_KEY','KIMI_API_KEY','OBSERVER_MODEL_DISABLED'):env.pop(k,None)
        r=subprocess.run([sys.executable,'agent.py'],cwd=AGENT_DIR,env=env,input=''.join(json.dumps(m)+'\n' for m in msgs),
            text=True,capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);lines=r.stdout.splitlines()
        self.assertEqual(len(lines),2);self.assertEqual(lines[0],lines[1]);self.assertEqual(json.loads(lines[0])['action'],'observe')
        self.assertNotIn('error ',r.stderr)

if __name__=='__main__':unittest.main()
