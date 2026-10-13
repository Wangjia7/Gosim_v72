import time,unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from llm_client import Call
class Client:
    max_retries=3
    def __init__(self):self.timeouts=[]
    def _request(self,system,user,timeout):
        self.timeouts.append(timeout);raise OSError('fake unavailable')
class Deadline(unittest.TestCase):
    def test_retry_backoff_fits_total_deadline(self):
        client=Client();start=time.monotonic();call=Call(client,'test','',{},.02)
        self.assertTrue(call.wait(.15));self.assertLess(time.monotonic()-start,.15)
        self.assertEqual(len(client.timeouts),1);self.assertLessEqual(client.timeouts[0],.02)
    def test_success_unchanged(self):
        client=Client();client._request=lambda *a:{'ok':True};call=Call(client,'test','',{},.1)
        self.assertTrue(call.wait(.2));self.assertEqual(call.answer,{'ok':True})
if __name__=='__main__':unittest.main()
