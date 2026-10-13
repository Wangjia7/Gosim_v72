from pathlib import Path
from unittest.mock import patch
import copy,json,os,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent'))
sys.path.insert(0,str(ROOT.parent/'gosim-desi-v300/tests'))
from test_observer import init
from routing import initial_route
class RouterTests(unittest.TestCase):
 def test_standard_uses_pro(self):self.assertEqual(initial_route(init())[0],'official_pro')
 def test_small_layout_stays_pro(self):self.assertEqual(initial_route(init(3))[0],'official_pro')
 def test_large_layout_uses_enhanced(self):self.assertEqual(initial_route(init(10))[0],'enhanced')
 def test_nonstandard_threshold(self):self.assertEqual(initial_route(init(4,.7))[0],'enhanced')
 def test_nonstandard_penalty(self):
  x=init();x['scoring']['required']['penalty_per_missing']=80;self.assertEqual(initial_route(x)[0],'enhanced')
 def test_card_name_cannot_change_route(self):
  x=init();x['task_card']={'card_id':'hidden-earthquake-offset-stress'};self.assertEqual(initial_route(x)[0],'official_pro')
 def test_normal_action_matches_exact_pro(self):
  from official_pro.agent import ObserverAgent as Official
  sys.path.insert(0,str(ROOT.parent/'gosim-desi-v300/baseline'))
  # Package copy changes imports only; compare actual upstream CLI output.
  data=init();messages=[{'protocol_version':'participant-agent-protocol-v4','message_type':'initialize','payload':data},
   {'protocol_version':'participant-agent-protocol-v4','message_type':'decision_request','decision_sequence':1,
   'payload':{'now_utc':data['survey']['start_utc'],'new_messages':[],'active_requests':[],
   'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
  env={**os.environ,'OBSERVER_MODEL_DISABLED':'1','PRO_FIXED_LEVEL':'0'}
  outputs=[]
  for cwd in (ROOT/'agent',ROOT.parent/'gosim-desi-v300/baseline'):
   p=subprocess.run([sys.executable,'-u','agent.py'],cwd=cwd,env=env,text=True,
    input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,timeout=20)
   self.assertEqual(p.returncode,0,p.stderr);outputs.append(json.loads(p.stdout))
  self.assertEqual(outputs[0],outputs[1])
 def test_enhanced_jsonl(self):
  data=init(4,.7);msgs=[{'message_type':'initialize','payload':data},
   {'message_type':'decision_request','decision_sequence':8,'payload':{'now_utc':data['survey']['start_utc'],
    'new_messages':[],'active_requests':[],'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
  p=subprocess.run([sys.executable,'agent.py'],cwd=ROOT/'agent',env={**os.environ,'OBSERVER_MODEL_DISABLED':'1'},text=True,
    input=''.join(json.dumps(m)+'\n' for m in msgs),capture_output=True,timeout=20)
  self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['action'],'observe')
  self.assertIn('enhanced',p.stderr)
if __name__=='__main__':unittest.main()
