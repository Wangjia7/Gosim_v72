import time,unittest,threading,os,json
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from llm_client import Call,LLMClient,MAX_BODY_BYTES
import llm_client as module
class Client:
    max_retries=3
    def __init__(self):self.timeouts=[];self._request_slots=threading.BoundedSemaphore(1)
    def _request(self,system,user,timeout,tag=None):
        self.timeouts.append(timeout);raise OSError('fake unavailable')
class Deadline(unittest.TestCase):
    def test_retry_backoff_fits_total_deadline(self):
        client=Client();start=time.monotonic();call=Call(client,'test','',{},.02)
        self.assertTrue(call.wait(.15));self.assertLess(time.monotonic()-start,.15)
        self.assertEqual(len(client.timeouts),1);self.assertLessEqual(client.timeouts[0],.02)
    def test_slow_request_deadline_keeps_worker_slots_bounded(self):
        client=Client(); release=threading.Event(); entered=threading.Event()
        def slow(*args):
            entered.set();release.wait(.5);return {'ok':True}
        client._request=slow
        try:
            first=Call(client,'slow','',{},.02)
            self.assertTrue(entered.wait(.1));self.assertTrue(first.wait(.15))
            self.assertEqual(first.error,'TimeoutError')
            second=Call(client,'second','',{},.02)
            self.assertTrue(second.wait(.1));self.assertEqual(second.error,'in_flight_limit')
        finally:
            release.set()
    def test_invalid_provider_endpoint_disables_calls(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-secret','OPENAI_BASE_URL':'https://user:private@host/v1'},clear=True):
            client=LLMClient()
            self.assertEqual(client.key,'')
            self.assertIsNone(client.submit('test','',{},100))
    def test_response_size_and_nonfinite_json_are_rejected(self):
        class Response:
            def __init__(self,raw):self.raw=raw
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return self.raw[:limit]
        with patch.dict(os.environ,{},clear=True):
            client=LLMClient()
        answers=(b'x'*(MAX_BODY_BYTES+1),json.dumps({'choices':[{'message':{'content':'{"confidence":NaN}'}}]}).encode())
        for raw in answers:
            with patch.object(module.urllib.request,'urlopen',return_value=Response(raw)):
                with self.assertRaises(ValueError):client._request('',{},.02)
    def test_success_unchanged(self):
        client=Client();client._request=lambda *a:{'ok':True};call=Call(client,'test','',{},.1)
        self.assertTrue(call.wait(.2));self.assertEqual(call.answer,{'ok':True})
if __name__=='__main__':unittest.main()
