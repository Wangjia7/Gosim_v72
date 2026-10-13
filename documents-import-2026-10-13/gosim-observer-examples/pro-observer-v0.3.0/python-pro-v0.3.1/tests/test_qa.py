import io,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from decision_log import DecisionLogger,sanitize
from qa_review import ReviewClient,validate_review,deterministic_review,replay_records,bounded_context_body,MAX_BYTES

class QA(unittest.TestCase):
    def test_append_and_redact(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'secret-value'}):
            path=Path(folder)/'log'; logger=DecisionLogger({'api_key':'secret-value'},str(path))
            logger.emit({'kind':'decision','step':1,'text':'secret-value','bad':float('nan')});logger.emit({'kind':'outcome','step':1})
            text=path.read_text();self.assertNotIn('secret-value',text);rows=[json.loads(x) for x in text.splitlines()];self.assertEqual(len(rows),2);self.assertIsNone(rows[0]['bad'])
    def test_finite_float_records_remain_numeric_for_qa(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'log'; logger=DecisionLogger(path=str(path))
            logger.emit({'record_type':'decision','step':1,'selected':{'action':'finish'},
                         'cpu':{'remaining_seconds':0.0},'predicted':{'science_gain':2.5,'factors':[.6]},
                         'nonfinite':[float('inf'),float('-inf'),float('nan')]})
            record=json.loads(path.read_text())
            self.assertIs(type(record['cpu']['remaining_seconds']),float)
            self.assertEqual(record['predicted'],{'science_gain':2.5,'factors':[.6]})
            self.assertEqual(record['nonfinite'],[None,None,None])
            self.assertTrue(any('CPU budget exhausted' in alarm for alarm in deterministic_review([record])['alarms']))
    def test_internal_error_alarms_but_unknown_wait_feasibility_does_not(self):
        wait={'record_type':'decision','step':1,'selected':{'action':'wait'},
              'constraints':{'feasible':None},'cpu':{'remaining_seconds':100}}
        failed={'record_type':'decision','step':2,'selected':{'action':'finish'},
                'constraints':{'feasible':None,'reason':'INTERNAL_ERROR'},
                'error':{'class':'KeyError','frames':[{'file':'planner.py','function':'plan','line':1}],
                         'message':'fake-secret-must-not-enter-review'},
                'cpu':{'remaining_seconds':100}}
        self.assertEqual(deterministic_review([wait])['alarms'],[])
        review=deterministic_review([wait,failed])
        self.assertEqual(review['alarms'],['Step 2: recorded internal error.'])
        self.assertNotIn('fake-secret',json.dumps(review))

    def test_unwritable_fallback(self):
        stream=io.StringIO();logger=DecisionLogger(path='/nonexistent-pro-qa-dir/log',stderr=stream)
        self.assertFalse(logger.emit({'step':1}));self.assertEqual(json.loads(stream.getvalue())['step'],1)
    def test_disabled(self):
        with patch.dict(os.environ,{},clear=True):self.assertEqual(ReviewClient().review([])['status'],'disabled')
    def test_invalid_endpoint_is_unavailable_without_network_or_credentials(self):
        endpoints=('not-a-url','file:///tmp/private','https:///chat','https://user:private-pass@host/v1',
                   'https://host:bad/v1','https://bad host/v1','https://[invalid/v1')
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint),patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'synthetic-secret',
                    'PRO_REVIEW_BASE_URL':endpoint,'PRO_REVIEW_MODEL':'fake'}):
                opener=unittest.mock.Mock(side_effect=AssertionError('invalid endpoint must not open'))
                result=ReviewClient(opener=opener).review([])
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['error'],'invalid_endpoint')
                self.assertIsNone(result['review'])
                opener.assert_not_called()
                self.assertNotIn('private-pass',json.dumps(result))
                self.assertNotIn('synthetic-secret',json.dumps(result))
    def test_malformed_and_nonfinite(self):
        for value in ({},{'warnings':[],'alarms':[],'hypotheses':[],'evidence':[],'recommended_ablations':[],'confidence':float('nan')}):
            with self.assertRaises(ValueError):validate_review(value)
    def test_timeout_and_retries(self):
        calls=[]
        def unavailable(*args,**kwargs):calls.append(kwargs['timeout']);raise OSError('secret provider error')
        with patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'secret-value','PRO_REVIEW_BASE_URL':'https://example.test/v1','PRO_REVIEW_MODEL':'fake'}):
            result=ReviewClient(.2,2,unavailable).review([]);self.assertEqual(len(calls),3);self.assertNotIn('secret',json.dumps(result))
            def hangs(*args,**kwargs):time.sleep(.3)
            start=time.monotonic();result=ReviewClient(.02,2,hangs).review([]);self.assertLess(time.monotonic()-start,.15);self.assertEqual(result['error'],'total_timeout')
    def test_remote_valid_and_malformed(self):
        answer={'warnings':[],'alarms':[],'hypotheses':[],'evidence':[],'recommended_ablations':[],'confidence':.5}
        class Response:
            def __init__(self, content):self.content=content
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps({'choices':[{'message':{'content':self.content}}]}).encode()[:limit]
        with patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'secret-value','PRO_REVIEW_BASE_URL':'https://example.test/v1','PRO_REVIEW_MODEL':'fake'}):
            valid=ReviewClient(opener=lambda *a,**k:Response(json.dumps(answer))).review([])
            self.assertEqual(valid['status'],'ok')
            malformed=ReviewClient(retries=0,opener=lambda *a,**k:Response('not json')).review([])
            self.assertEqual(malformed['status'],'unavailable')
    def test_wait_and_pending_are_not_false_alarms(self):
        records=[{'kind':'decision','step':1,'selected':{'action':'wait'},'constraints':{'feasible':False}}, {'kind':'outcome','step':1,'status':'pending'}]
        result=deterministic_review(records)
        self.assertEqual(result['alarms'],[]);self.assertTrue(result['warnings'])
        records[0]['selected']['action']='observe'
        self.assertTrue(deterministic_review(records)['alarms'])
    def test_replay_each_step(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'log'
            rows=[{'kind':'decision','step':1},{'kind':'outcome','step':1},{'kind':'decision','step':2}]
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            packets=list(replay_records(path));self.assertEqual([len(p) for p in packets],[2,1])
    def test_large_context_retains_recent_and_declares_coverage(self):
        records=[{'step':i,'text':'x'*8192} for i in range(1000)]
        body,coverage=bounded_context_body(records,'fake','diagnose')
        self.assertLessEqual(len(body),MAX_BYTES)
        context=json.loads(json.loads(body)['messages'][1]['content'])
        self.assertEqual(context['records'][-1]['step'],999)
        self.assertTrue(coverage['recent_window_only'])
        self.assertEqual(coverage['records_received'],1000)
        self.assertEqual(coverage['records_included']+coverage['records_omitted'],1000)
    def test_oversized_record_and_secret_context(self):
        with patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'secret-value'}):
            body,coverage=bounded_context_body([{'step':1,'text':'secret-value'},{'step':2,'text':'x'*(MAX_BYTES*2)}],'fake','diagnose')
            self.assertEqual(coverage['records_included'],1)
            self.assertEqual(coverage['oversized_records_skipped'],1)
            self.assertNotIn('secret-value',body.decode())
            _,none=bounded_context_body([{'text':'x'*(MAX_BYTES*2)}],'fake','diagnose')
            self.assertEqual(none['records_included'],0)
    def test_remote_large_run_uses_bounded_body(self):
        captured=[]
        answer={'warnings':[],'alarms':[],'hypotheses':[],'evidence':[],'recommended_ablations':[],'confidence':.5}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps({'choices':[{'message':{'content':json.dumps(answer)}}]}).encode()
        def fake(request,**kwargs):captured.append(request.data);return Response()
        with patch.dict(os.environ,{'PRO_REVIEW_API_KEY':'secret-value','PRO_REVIEW_BASE_URL':'https://example.test/v1','PRO_REVIEW_MODEL':'fake'}):
            result=ReviewClient(opener=fake).review([{'step':i,'text':'x'*8192} for i in range(1000)])
            self.assertEqual(result['status'],'ok');self.assertLessEqual(len(captured[0]),MAX_BYTES)
            self.assertGreater(result['coverage']['records_omitted'],0)
            impossible=ReviewClient(opener=lambda *a,**k:self.fail('must not call')).review([{'text':'x'*(MAX_BYTES*2)}])
            self.assertEqual(impossible['error'],'request_too_large')
    def test_step_packet_retained_when_small(self):
        records=[{'kind':'decision','step':1},{'kind':'outcome','step':1}]
        body,coverage=bounded_context_body(records,'fake','diagnose')
        self.assertEqual(json.loads(json.loads(body)['messages'][1]['content'])['records'],records)
        self.assertFalse(coverage['recent_window_only'])
    def test_pending_and_purity(self):
        records=[{'kind':'decision','step':1}];before=json.dumps(records)
        self.assertIn('pending',deterministic_review(records)['warnings'][0]);self.assertEqual(json.dumps(records),before)
if __name__=='__main__':unittest.main()
