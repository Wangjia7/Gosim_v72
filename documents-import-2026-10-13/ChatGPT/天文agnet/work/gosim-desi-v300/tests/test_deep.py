import json, math, os, random, sys, time, unittest
from pathlib import Path
from test_observer import init, ROOT
from planner import Planner
from skymath import FiberGrid, shift_altaz, tangent_offsets
from native import FieldBatch, LIB
from geometry_feedback import GeometryFeedback
from advisor import Advisor
from agent import ObserverAgent

class Ready:
 def __init__(self,answer,tag):self.answer=answer;self.tag=tag
 def done(self):return True
 def wait(self,t):return True
class MockClient:
 def __init__(self):self.tags=[]
 def submit(self,tag,system,user,left):
  self.tags.append(tag)
  if tag=='operator_nlp':
   answer={'bad_night':False,'avoid_directions':[],'prioritize_target_ids':['t0'],'prioritize_request_ids':[],
     'ambiguities':[],'sources':[{'source_id':'o1','quote':'优先 t0'}],'reason':'operator preference'}
  else: answer={'ledger_version':user['ledger_version'],'fault_likely':.1,'diagnosis':'normal','recommendation':'retain','reason':'no residual'}
  return Ready(answer,tag)
 def collect(self,call):return call.answer

class Deep(unittest.TestCase):
 def test_shared_boundary_matches_engine(self):
  sys.path.insert(0,str(ROOT/'runner'))
  from challenge.v4_fiber_map import FiberGrid as EngineGrid
  for side in (1,3,4,5,10):
   grid=FiberGrid(init(side)['instrument']);engine=EngineGrid(.4,0,side*side)
   p=grid.pitch
   for row in range(side+1):
    for col in range(side+1):
     a=(row-side/2)*p;z=(col-side/2)*p
     self.assertEqual(grid.classify(a,z)[0],engine.classify_offset(a,z)[0])
 def test_gap_is_not_glass(self):
  cfg=init()['instrument'];cfg.update(gap_deg=.1,pitch_deg=math.sqrt(.4)+.1,fov_side_deg=4*math.sqrt(.4)+.3)
  grid=FiberGrid(cfg);self.assertIsNone(grid.classify(0,0)[0])
 @unittest.skipIf(LIB is None,'native not built')
 def test_native_python_same_cells_and_winners(self):
  rng=random.Random(20261006)
  for side in (1,3,4,5,10):
   grid=FiberGrid(init(side)['instrument']);base={};misses=[0]*100;near=list(range(100));choices=[(60,'BRIGHT'),(900,'DARK')]
   for j in near:base[j]=shift_altaz(55,120,rng.uniform(-grid.fov,grid.fov),rng.uniform(-grid.fov,grid.fov))
   gains={(j,t,p):rng.random()*10 for j in near for t,p in choices}
   batch=FieldBatch(grid,near,base,misses,choices,lambda j,t,p:gains[j,t,p],.04)
   for t,p,pick,total in batch.evaluate(55,120):
    expected={}
    for j in near:
     xy=tangent_offsets(*base[j],55,120);fib,margin=grid.classify(*xy)
     if fib is not None and margin>=.02:
      if fib not in expected or (gains[j,t,p],j)>(gains[expected[fib],t,p],expected[fib]):expected[fib]=j
    self.assertEqual(pick,expected);self.assertAlmostEqual(total,sum(gains[j,t,p] for j in expected.values()),places=10)
 def test_offset_needs_future_validation(self):
  grid=FiberGrid(init()['instrument']);feedback=GeometryFeedback(grid,True)
  for exposure in range(6):
   pending={};hits={}
   for f in range(grid.n):
    n,e=grid.fiber_center(f);edge=grid.glass/2-.003
    a,z=shift_altaz(55.1,119.9,n+(edge if f%2 else -edge),e+(edge if f%4<2 else -edge))
    pending[str(f)]={'alt':a,'az':z,'geometry':{'altitude_feasible':True,'fiber':f,'command_alt':55,'command_az':120}}
    if grid.classify(*tangent_offsets(a,z,55.1,119.9))[0]==f:hits[str(f)]=0
   result=feedback.record(pending,hits)
   if exposure<5:self.assertEqual(feedback.offset,(0,0))
  self.assertAlmostEqual(feedback.offset[0],.1,places=3);self.assertAlmostEqual(feedback.offset[1],-.1,places=3)
 def test_all_misses_cannot_certify_offset(self):
  grid=FiberGrid(init()['instrument']);g=GeometryFeedback(grid,True)
  p={str(f):{'alt':55,'az':120,'geometry':{'altitude_feasible':True,'fiber':f,'command_alt':55,'command_az':120}} for f in range(grid.n)}
  for _ in range(10):g.record(p,{})
  self.assertEqual(g.offset,(0,0));self.assertIsNone(g.proposal)
 def test_two_llm_roles(self):
  planner=Planner(init());client=MockClient();a=Advisor(client)
  a.ingest({'now_utc':init()['survey']['start_utc'],'operator_messages':[{'message_id':'o1','text':'优先 t0'}]},planner)
  plan,fault=a.start_night('2026-11-01',[],[],{'rows':[]},300,1)
  self.assertEqual(client.tags,['operator_nlp','anomaly_review']);self.assertEqual(plan['prioritize_target_ids'],['t0'])
  self.assertEqual(fault['diagnosis'],'normal');self.assertEqual(a.validated,{'operator_nlp':1,'anomaly_review':1})
 def test_unsupported_operator_preferences_rejected(self):
  a=Advisor(MockClient());a.known_targets={'t0'};a.sources={'o1':'优先 t0'}
  base={'bad_night':False,'avoid_directions':[],'sources':[{'source_id':'o1','quote':'优先 t0'}]}
  self.assertIsNone(a._valid_plan({**base,'prioritize_target_ids':['imaginary']}))
  self.assertIsNone(a._valid_plan({**base,'avoid_directions':['SW']}))
  self.assertIsNone(a._valid_plan({**base,'sources':[{'source_id':'o1','quote':'invented'}]}))
 def test_malformed_model_arrays_rejected(self):
  a=Advisor(MockClient());a.known_targets={'t0'}
  self.assertIsNone(a._valid_plan({'bad_night':False,'prioritize_target_ids':[{}]}))
  self.assertIsNone(a._valid_fault({'ledger_version':0,'fault_likely':True,'diagnosis':'normal','recommendation':'retain'}))
 def test_class_preference_needs_source(self):
  a=Advisor(MockClient());a.sources={'o1':'今晚优先类星体'}
  self.assertIsNotNone(a._valid_plan({'bad_night':False,'prioritize_classes':['QSO'],
    'sources':[{'source_id':'o1','quote':'优先类星体'}]}))
  self.assertIsNone(a._valid_plan({'bad_night':False,'prioritize_classes':['Star'],
    'sources':[{'source_id':'o1','quote':'优先类星体'}]}))
 def test_stale_anomaly_rejected(self):
  a=Advisor(MockClient());a.ledger_version=2
  self.assertIsNone(a._valid_fault({'ledger_version':1,'fault_likely':.9,'diagnosis':'throughput_candidate','recommendation':'report_fault'}))
 def test_cpu_budget_returns_incumbent(self):
  p=Planner(init(10));p.cpu_turn_budget=.00001
  action=p.plan(p.nights[0][0],p.nights[0][1],0,0)
  self.assertIsNotNone(action);self.assertEqual(action['action'],'observe')
 def test_deadline_target_survives_crowded_pool(self):
  from unittest.mock import patch
  from skymath import format_utc
  from datetime import timedelta
  data=init(1);data['targets']['rows'][1][1]=data['targets']['rows'][0][1]+10
  p=Planner(data);now=p.nights[0][0];p.cpu_turn_budget=.00001
  p.on_requests([{'request_id':'r1','issued_at_utc':format_utc(now),
    'deadline_utc':format_utc(now+timedelta(seconds=900)),'target_ids':['t1'],
    'minimum_completed':1,'completion_factor_threshold':.5,'completion_reward':10}])
  with patch('planner.POOL',1),patch('planner.N_ANCHORS',1):
   action=p.plan(now,p.nights[0][1],0,0)
  self.assertIn('t1',action['assignments'].values())
  self.assertLessEqual(action['duration_seconds'],900)
 def test_new_request_survives_old_geometry_misses(self):
  from unittest.mock import patch
  from skymath import format_utc
  from datetime import timedelta
  data=init(1);data['targets']['rows'][1][1]=data['targets']['rows'][0][1]+10
  p=Planner(data);p.misses[1]=20;now=p.nights[0][0];p.cpu_turn_budget=.00001
  p.on_requests([{'request_id':'r1','issued_at_utc':format_utc(now),
    'deadline_utc':format_utc(now+timedelta(seconds=900)),'target_ids':['t1'],
    'minimum_completed':1,'completion_factor_threshold':.5,'completion_reward':10}])
  with patch('planner.POOL',1),patch('planner.N_ANCHORS',1):
   action=p.plan(now,p.nights[0][1],0,0)
  self.assertIn('t1',action['assignments'].values())
  self.assertLessEqual(action['duration_seconds'],900)
 def test_expired_note_ignored(self):
  p=Planner(init());a=Advisor(MockClient())
  a.ingest({'now_utc':init()['survey']['start_utc'],'operator_messages':[{'text':'优先 t0','expires_utc':'2026-01-01T00:00:00Z'}]},p)
  self.assertEqual(a.texts,[])

if __name__=='__main__':unittest.main()
