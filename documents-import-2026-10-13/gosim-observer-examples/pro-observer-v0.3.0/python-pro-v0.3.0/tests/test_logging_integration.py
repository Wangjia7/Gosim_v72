import contextlib,io,json,os,tempfile,unittest
from unittest.mock import patch
from support import fixture,NOW
from agent import ObserverAgent
class Integration(unittest.TestCase):
    def test_all_steps_correlated_and_pending(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'PRO_LOG_PATH':d+'/run.jsonl','OBSERVER_MODEL_DISABLED':'1'}),contextlib.redirect_stderr(io.StringIO()):
            a=ObserverAgent(fixture());a.current_sequence=11
            payload={'now_utc':NOW.isoformat(),'running_total':1,'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':100}}
            with patch.object(a,'_respond',return_value={'action':'wait','duration_seconds':60}):a.respond(payload)
            a.current_sequence=12
            payload2={**payload,'running_total':3,'last_result':{'action':'wait'}}
            with patch.object(a,'_respond',return_value={'action':'finish'}):a.respond(payload2)
            a.finalize_log('agent_finished')
            rows=[json.loads(s) for s in open(d+'/run.jsonl')]
            self.assertEqual([(r['record_type'],r['step']) for r in rows],[('decision',11),('outcome',11),('decision',12),('outcome',12)])
            self.assertEqual(rows[1]['realized']['science_delta_including_corrections'],2)
            self.assertIsNone(rows[1]['realized']['quality']);self.assertEqual(rows[-1]['status'],'pending')
            self.assertNotIn('public_initialize',json.dumps(rows))
    def test_no_key_uses_rules(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'PRO_LOG_PATH':d+'/run.jsonl'},clear=True),contextlib.redirect_stderr(io.StringIO()):
            a=ObserverAgent(fixture());self.assertTrue(a.rules_only);self.assertIsNone(a.client)
if __name__=='__main__':unittest.main()
