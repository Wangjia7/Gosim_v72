import io
import json
import unittest
from unittest.mock import patch
from test_normal import fixture, Planner, ROOT
from advisor import Advisor
from llm_client import LLMClient

class Ready:
    def __init__(self,answer):self.answer=answer
    def done(self):return True
    def wait(self,t):return True
class MockClient:
    def __init__(self):self.tags=[]
    def submit(self,tag,system,user,left):
        self.tags.append(tag)
        if tag=='operator_nlp':
            answer={'bad_night':False,'avoid_directions':[],'prioritize_target_ids':['t0'],
                    'sources':[{'source_id':'o1','quote':'优先 t0'}]}
        else:
            answer={'ledger_version':user['ledger_version'],'fault_likely':.1,
                    'diagnosis':'normal','recommendation':'retain','reason':'no residual'}
        return Ready(answer)
    def collect(self,call):return call.answer

class ModelTests(unittest.TestCase):
    def test_two_local_model_roles_with_normal_planner(self):
        p=Planner(fixture());client=MockClient();a=Advisor(client)
        a.ingest({'now_utc':fixture()['survey']['start_utc'],
                  'operator_messages':[{'message_id':'o1','text':'优先 t0'}]},p)
        plan,fault=a.start_night('2026-11-01',[],[],{'rows':[]},300,1)
        self.assertEqual(client.tags,['operator_nlp','anomaly_review'])
        self.assertEqual(plan['prioritize_target_ids'],['t0']);self.assertEqual(fault['diagnosis'],'normal')
    def test_unknown_target_and_stale_ledger_are_rejected(self):
        a=Advisor(MockClient());a.known_targets={'t0'};a.sources={'o1':'优先 t0'};a.ledger_version=2
        self.assertIsNone(a._valid_plan({'bad_night':False,'prioritize_target_ids':['invented'],
            'sources':[{'source_id':'o1','quote':'优先 t0'}]}))
        self.assertIsNone(a._valid_fault({'ledger_version':1,'fault_likely':.9,
            'diagnosis':'throughput_candidate','recommendation':'report_fault'}))
    def test_strict_json_accepts_one_object_or_fence(self):
        client=LLMClient()
        for text in ('{"ok":true}','```json\n{"ok":true}\n```'):
            raw=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':text}}]}).encode()
            with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
                self.assertEqual(client._request('system',{},1),{'ok':True})
    def test_strict_json_rejects_multiple_objects_and_nonfinite(self):
        client=LLMClient()
        for text in ('{} {}','prefix {}','{"x":NaN}','{"x":1,"x":2}'):
            raw=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':text}}]}).encode()
            with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError):client._request('system',{},1)

if __name__=='__main__':unittest.main()
