import importlib, json, math, os, subprocess, sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'agent'))
from planner import Planner
from opportunities import request_gain
from skymath import FiberGrid, local_sidereal_deg, format_utc

def init(side=4, threshold=.5):
    score=json.loads((ROOT/'fixtures/official-config/v4_score_config.json').read_text())
    score['required']['observed_factor_threshold']=threshold
    start=datetime(2026,11,2,1,tzinfo=timezone.utc);end=start+timedelta(hours=6)
    ra=local_sidereal_deg(start,-70.3976)
    return {'site':{'latitude_deg':-24.6157,'longitude_deg':-70.3976,'minimum_altitude_deg':30},
     'survey':{'start_utc':format_utc(start),'end_utc':format_utc(end),'slot_seconds':900,
      'nights':[{'observing_start_utc':format_utc(start),'observing_end_utc':format_utc(end)}]},
     'instrument':{'n_fibers':side*side,'grid_side':side,'fiber_area_deg2':.4,'gap_deg':0,'glass_side_deg':math.sqrt(.4),
       'pitch_deg':math.sqrt(.4),'fov_side_deg':side*math.sqrt(.4),'exposure':{'min_duration_seconds':60,'max_duration_seconds':3600}},
     'scoring':score, 'targets':{'columns':['target_id','ra_deg','dec_deg','target_class','feature_flux','science_weight','required'],
       'rows':[['t0',ra,-30,'QSO',.3,2,True],['t1',(ra+.5)%360,-30.5,'Star',1.8,1,False]]},'limits':{}}

class Tests(unittest.TestCase):
 def test_deadline_and_overlap(self):
    p=Planner(init()); now=datetime(2026,11,2,1,tzinfo=timezone.utc).timestamp()
    legs=[{'start':now,'end':now+100,'threshold':.35,'value':20}, {'start':now,'end':now+900,'threshold':.7,'value':50}]
    self.assertGreater(request_gain(legs,now,90,.4,p.opportunities,0),0)
    self.assertEqual(request_gain(legs,now,101,.4,p.opportunities,0),0)
    self.assertGreater(request_gain(legs,now,200,.8,p.opportunities,0),0)
    self.assertEqual(request_gain(legs,now-1,90,.8,p.opportunities,0),0)
 def test_short_window(self):
    p=Planner(init());now=p.nights[0][0].timestamp();p.opportunities.cache[0]=[(now,now+90)]
    self.assertEqual(p.opportunities.remaining(0,now,duration=60)[1],1)
    self.assertEqual(p.opportunities.remaining(0,now,duration=91)[1],0)
 def test_resync_replays_independent_maxima(self):
    p=Planner(init());p.history=[[(0,1.632,.8,.8)],[(0,1.53,.9,.9)]]
    p._resync({'invalidated_window':{'action_index_start':0,'action_index_end_exclusive':1},'best_scores':[{'target_id':'t0','best_score':1.53}]})
    self.assertAlmostEqual(p.factor[0],.9);self.assertAlmostEqual(p.cur[0],.765)
 def test_no_short_exposure_stacking(self):
    p=Planner(init());p.history=[[(0,.4,.2,.2)],[(0,.5,.25,.25)]]
    p._resync({'invalidated_window':{'action_index_start':0,'action_index_end_exclusive':0},'best_scores':[{'target_id':'t0','best_score':.5}]})
    self.assertEqual(p.factor[0],.25)
 def test_raw_bound_under_fault(self):
    p=Planner(init());p.pending={'t0':{'model':1,'band_model':1,'alt':60,'az':180,'dir_clean':True,'fiber':0,'pred':.5}}
    p.pending_cmd=(60,180);p.pending_program='DARK';p.pending_duration=900
    p.on_result({'action':'observe','hits':[{'target_id':'t0','score':2*.4*1.2}]},p.nights[0][0],1)
    self.assertAlmostEqual(p.factor[0],.4);self.assertLess(p.factor[0],.5)
 def test_dynamic_layout_protocol(self):
    for side in (1,3,4,5,10):
     p=Planner(init(side,.7));p.fast_level=3; now=p.nights[0][0]
     action=p.plan(now,p.nights[0][1],0,0)
     self.assertIsNotNone(action); self.assertTrue(all(0<=int(k)<side*side for k in action['assignments']))
     self.assertGreaterEqual(action['duration_seconds'],60)
 def test_jsonl(self):
    messages=[{'protocol_version':'participant-agent-protocol-v4','message_type':'initialize','payload':init()},
      {'protocol_version':'participant-agent-protocol-v4','message_type':'decision_request','decision_sequence':7,
       'payload':{'now_utc':init()['survey']['start_utc'],'new_messages':[],'active_requests':[],
        'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
    run=subprocess.run([sys.executable,'-u','agent.py'],cwd=ROOT/'agent',input=''.join(json.dumps(m)+'\n' for m in messages),
      text=True,capture_output=True,env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},timeout=20)
    self.assertEqual(run.returncode,0,run.stderr)
    lines=run.stdout.splitlines();self.assertEqual(len(lines),1);reply=json.loads(lines[0]);self.assertEqual(reply['decision_sequence'],7)
    self.assertEqual(reply['action'],'observe');self.assertNotIn('request_id',reply)

if __name__=='__main__': unittest.main()
