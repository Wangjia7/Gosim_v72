import io,json,os,unittest
from unittest.mock import patch
from test_observer import init
from advisor import Advisor
from planner import Planner
from llm_client import LLMClient
class Response(io.BytesIO):
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
class ApiContract(unittest.TestCase):
 def test_both_roles_use_chat_completion_transport(self):
  requests=[]
  def endpoint(request,timeout):
   body=json.loads(request.data);requests.append(body)
   self.assertNotIn('temperature',body)
   self.assertEqual([x['role'] for x in body['messages']],['system','user'])
   user=json.loads(body['messages'][1]['content'])
   if 'Workflow operator_nlp' in body['messages'][0]['content']:
    answer={'bad_night':False,'avoid_directions':[],'prioritize_target_ids':['t0'],
      'prioritize_request_ids':[],'ambiguities':[], 'sources':[{'source_id':'o1','quote':'优先 t0'}],'reason':'known note'}
   else:answer={'ledger_version':user['ledger_version'],'fault_likely':.2,'diagnosis':'inconclusive',
      'recommendation':'gather_evidence','reason':'not enough data'}
   return Response(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}).encode())
  with patch('urllib.request.urlopen',endpoint),patch.dict(os.environ,{'OPENAI_API_KEY':'test-not-real'}):
   client=LLMClient(max_calls=4,max_retries=1);a=Advisor(client);p=Planner(init())
   a.ingest({'now_utc':init()['survey']['start_utc'],'operator_messages':[{'message_id':'o1','text':'优先 t0'}]},p)
   plan,fault=a.start_night('2026-11-01',[],[],{'rows':[]},120,2)
   self.assertEqual(len(requests),2);self.assertEqual(client.ok,2);self.assertEqual(a.validated,{'operator_nlp':1,'anomaly_review':1})
   self.assertEqual(plan['prioritize_target_ids'],['t0']);self.assertEqual(fault['recommendation'],'gather_evidence')
 def test_duplicate_nonfinite_and_truncated_responses_fail(self):
  client=LLMClient(max_retries=1)
  for text,finish in [('{"a":1,"a":2}','stop'),('{"a":NaN}','stop'),('{"a":1}','length')]:
   raw=json.dumps({'choices':[{'finish_reason':finish,'message':{'content':text}}]}).encode()
   with patch('urllib.request.urlopen',lambda *a,**k:Response(raw)):
    with self.assertRaises(ValueError):client._request('system',{},1)
