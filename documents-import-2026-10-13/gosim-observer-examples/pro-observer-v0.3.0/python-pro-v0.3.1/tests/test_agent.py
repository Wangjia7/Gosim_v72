import contextlib
import io
import unittest
from datetime import timedelta
from unittest.mock import patch
from support import NOW, END, fixture
import agent as module
from agent import ObserverAgent

def make_agent(**kwargs):
    with contextlib.redirect_stderr(io.StringIO()):
        return ObserverAgent(fixture(**kwargs),rules_only=True)
def payload(now=NOW,cpu=1000):
    return {'now_utc':now.isoformat(),'new_messages':[],'active_requests':[],
      'wallclock':{'remaining_real_cpu_seconds':cpu,'wall_remaining_seconds':1000}}

class AgentTests(unittest.TestCase):
    def test_wait_duration_obeys_loaded_bounds(self):
        for low,high in ((1000,3600),(100,200),(173,173)):
            a=make_agent(minimum=low,maximum=high)
            for seconds in (0,1,299,300):
                wait=a._to_next_slot(NOW+timedelta(seconds=seconds),NOW)
                self.assertIs(type(wait),int)
                self.assertTrue(low <= wait <= high)
    def test_zero_cpu_fallback_does_not_search_or_wait_for_model(self):
        for remaining in (0,1e-9):
            a=make_agent()
            with patch.object(a.planner,'plan',side_effect=AssertionError('must not search')), \
                 patch.object(a,'_night_advice',side_effect=AssertionError('must not ask model')):
                action=a.respond(payload(cpu=remaining))
            self.assertIn(action['action'],('wait','finish'))
            if action['action']=='wait' and 'duration_seconds' in action:
                self.assertTrue(a.planner.min_exposure <= action['duration_seconds'] <= a.planner.max_exposure)
    def test_pacing_cost_is_attributed_to_selected_level(self):
        a=make_agent(); a.planner.fast_level=0
        def respond(_):
            a.planner.fast_level=2
            return {'action':'observe','assignments':{'0':'T0'}}
        with patch.object(a,'_respond',side_effect=respond):
            a.respond(payload())
        self.assertEqual(a.cost_ema[0],0)
        self.assertGreater(a.cost_ema[2],0)
        self.assertGreater(a.wall_ema[2],0)
    def test_final_night_clipped_observation_is_not_discarded(self):
        a=make_agent(minimum=1000,maximum=2000)
        now=END-timedelta(seconds=120)
        expected={'action':'observe','assignments':{'0':'T0'},'duration_seconds':1000,'program':'BACKUP',
                  'pointing_alt_deg':60,'pointing_az_deg':180}
        with patch.object(a,'_night_advice'), patch.object(a,'_maybe_report',return_value=None), \
             patch.object(a.planner,'plan',return_value=expected.copy()) as plan:
            action=a.respond(payload(now))
        self.assertEqual(action['action'],'observe')
        plan.assert_called_once()
    def test_normalized_reserve_tracks_current_calibration(self):
        a=make_agent()
        with patch.object(module.time,'process_time',return_value=100.),patch.object(module.time,'monotonic',return_value=1000.), \
             patch.object(a,'_respond',return_value={'action':'finish'}):
            for normalized,real,factor in ((900,450,.5),(500,500,1)):
                packet=payload(cpu=real);packet['wallclock']['remaining_seconds']=normalized
                a.respond(packet)
                reserve=module.CPU_RESERVE_NORMALIZED*factor
                self.assertAlmostEqual(a.reserve_process_seconds,reserve)
                self.assertAlmostEqual(a.planner.cpu_deadline,100+real-reserve)
    def test_normalized_reserve_boundary_prevents_state_or_search_work(self):
        a=make_agent()
        for extra in (0.,.001,.01):
            packet=payload(cpu=module.CPU_RESERVE_NORMALIZED*.5+extra)
            packet['wallclock']['remaining_seconds']=module.CPU_RESERVE_NORMALIZED+2*extra
            with patch.object(a,'_respond',return_value={'action':'finish'}) as respond:
                action=a.respond(packet)
            self.assertEqual(action['action'],'finish')
            self.assertEqual(respond.call_count,0 if extra<=.002 else 1)
    def test_adaptive_deadline_and_width_fit_spendable_cpu(self):
        a=make_agent();a.search_base_cpu_ema=.1
        packet=payload(cpu=200);packet['wallclock']['remaining_seconds']=100
        def decision(_):
            a._pace(packet,NOW)
            return {'action':'finish'}
        with patch.object(module.time,'process_time',return_value=100.),patch.object(module.time,'monotonic',return_value=1000.), \
             patch.object(module,'FIXED_LEVEL',-1),patch.object(module.v7,'WALL',False), \
             patch.object(a,'_decisions_left',return_value=10),patch.object(a,'_respond',side_effect=decision):
            a.respond(packet)
        spendable=200-module.CPU_RESERVE_NORMALIZED*2
        expected_allowance=min(spendable,max(.02,module.SEARCH_ALLOWANCE_FACTOR*module.PACE_SAFETY*spendable/10))
        self.assertAlmostEqual(a.planner.cpu_deadline,100+expected_allowance)
        self.assertLessEqual(a.planner.cpu_deadline,100+spendable)
        self.assertTrue(1<=a.planner.search_width_multiplier<=module.SEARCH_WIDTH_MAX)
    def test_state_over_local_share_does_not_finish_episode(self):
        a=make_agent()
        packet=payload(cpu=100);packet['wallclock']['remaining_seconds']=100
        cpu=[100.]
        def result(*args):cpu[0]=100.04
        def pace(*args):a.planner.cpu_deadline=100.02
        with patch.object(module.time,'process_time',side_effect=lambda:cpu[0]), \
             patch.object(module.time,'monotonic',return_value=1000.), \
             patch.object(a.planner,'on_result',side_effect=result),patch.object(a,'_pace',side_effect=pace), \
             patch.object(a,'_night_advice'),patch.object(a,'_maybe_report',return_value=None), \
             patch.object(a.planner,'plan',return_value=None),patch.object(a.planner,'monitor',return_value=None):
            action=a.respond(packet)
        self.assertEqual(action['action'],'wait')
        self.assertAlmostEqual(a.planner.cpu_deadline,100.04+module.FIRST_LEGAL_CPU_SECONDS)
        self.assertLess(a.planner.cpu_deadline,a._global_cpu_deadline)
    def test_search_expiry_does_not_start_unbudgeted_monitor(self):
        a=make_agent();a.planner.slot_seconds=900;packet=payload(cpu=100)
        def search(*args):
            a.planner.cpu_deadline=-1
            return None
        with patch.object(a,'_night_advice'),patch.object(a,'_maybe_report',return_value=None), \
             patch.object(a.planner,'plan',side_effect=search), \
             patch.object(a.planner,'monitor',side_effect=AssertionError('expired search cannot start monitor')):
            action=a.respond(packet)
        self.assertEqual(action['action'],'wait')
    def test_fair_clock_and_legacy_clock(self):
        a=make_agent()
        expected_wall=max(0.,1000.-(a.wall.reserve if module.v7.WALL else module.WALL_RESERVE_SECONDS))
        self.assertEqual(a._clock(payload(cpu=12)),(12.,expected_wall,True))
        self.assertEqual(a._clock({'wallclock':{'remaining_seconds':7}}),(7.,7.,False))

class EffectiveWidthAccounting(unittest.TestCase):
    def test_nondeep_cost_does_not_divide_by_requested_width(self):
        a=make_agent();a.planner.search_width_multiplier=20;a.planner.deep=False
        def decision(_):
            return {'action':'observe','assignments':{'0':'T0'}}
        with patch.object(a,'_respond',side_effect=decision):
            a.respond(payload())
        self.assertGreater(a.search_base_cpu_ema,0)
        self.assertAlmostEqual(a.search_base_cpu_ema,a.cost_ema[a.planner.fast_level])

class WidthAwareDeepGate(unittest.TestCase):
    def paced(self,enabled,wall=100,decisions=0):
        a=make_agent();a.cost_ema=[.1]*4;a.wall_ema=[.1]*4
        a.deep_ema=[20.,20.];a.deep_base_ema=[2.,1.];a.decisions=decisions
        a.planner.deep=False;a.search_base_cpu_ema=2.
        packet=payload(cpu=100);packet['wallclock']['remaining_seconds']=100
        def decide(_):
            a._pace(packet,NOW)
            return {'action':'finish'}
        with patch.object(module,'WIDTH_AWARE_GATE',enabled),patch.object(module,'FIXED_LEVEL',-1),patch.object(module,'SEARCH_WIDTH_MAX',20),patch.object(module,'PACE_SAFETY',1.),patch.object(module.v7,'WALL',False),patch.object(a,'_clock',return_value=(100.,wall,True)),patch.object(a,'_decisions_left',return_value=10),patch.object(a,'_respond',side_effect=decide):
            a.respond(packet)
        return a
    def test_costly_previous_width_can_shrink_and_fit(self):
        a=self.paced(1)
        self.assertTrue(a.planner.deep)
        self.assertGreater(a.planner.search_width_multiplier,1)
        self.assertLessEqual(a.planner.search_width_multiplier,4)
        self.assertEqual(a.deep_ema,[20.,20.])
    def test_wall_share_limits_width(self):
        a=self.paced(1,wall=20)
        self.assertTrue(a.planner.deep)
        self.assertLessEqual(a.planner.search_width_multiplier,2)
    def test_flag_off_preserves_raw_cost_gate(self):
        a=self.paced(0)
        self.assertFalse(a.planner.deep)
    def test_inactive_normalized_cost_decays_only_when_enabled(self):
        enabled=self.paced(1,wall=1,decisions=49)
        disabled=self.paced(0,wall=1,decisions=49)
        self.assertFalse(enabled.planner.deep)
        self.assertEqual(enabled.deep_base_ema,[1.7,.85])
        self.assertEqual(disabled.deep_base_ema,[2.,1.])
        self.assertEqual(enabled.deep_ema,disabled.deep_ema)
    def test_reserve_still_prevents_search(self):
        a=make_agent()
        with patch.object(module,'WIDTH_AWARE_GATE',1),patch.object(a,'_pace',side_effect=AssertionError('reserve must stop pacing')):
            self.assertEqual(a.respond(payload(cpu=0))['action'],'finish')

if __name__ == '__main__':
    unittest.main()


class SafeErrorDiagnostics(unittest.TestCase):
    def test_traceback_metadata_excludes_sensitive_exception_content(self):
        import json
        credential='fake-credential-123456'
        def recurse(depth):
            secret_local=credential
            if depth:
                return recurse(depth-1)
            raise RuntimeError('OPENAI_API_KEY='+secret_local)
        try:
            recurse(12)
        except RuntimeError as exc:
            metadata=module.safe_error_metadata(exc)
        self.assertEqual(metadata['class'],'RuntimeError')
        self.assertEqual(len(metadata['frames']),8)
        for frame in metadata['frames']:
            self.assertEqual(set(frame),{'file','function','line'})
            self.assertEqual(frame['file'],'test_agent.py')
            self.assertEqual(frame['function'],'recurse')
            self.assertIsInstance(frame['line'],int)
        encoded=json.dumps(metadata)
        self.assertNotIn(credential,encoded)
        self.assertNotIn('OPENAI_API_KEY',encoded)
        self.assertNotIn('secret_local',encoded)

    def test_decision_failure_logs_metadata_and_preserves_finish_response(self):
        import json
        from types import SimpleNamespace
        fake=SimpleNamespace(current_sequence=None,planner=SimpleNamespace(decision_record={}))
        def broken(_payload):
            raise KeyError('fake-credential-123456')
        fake.respond=broken
        fake._log_outcome=lambda *_:None
        records=[]
        fake._log_decision=lambda *_:records.append(fake.planner.decision_record)
        fake.model_influence_current=lambda:False
        fake.finalize_log=lambda *_:None
        messages=[{'protocol_version':module.PROTOCOL,'message_type':'initialize','payload':{}},
                  {'protocol_version':module.PROTOCOL,'message_type':'decision_request','decision_sequence':1,'payload':{}}]
        out,err=io.StringIO(),io.StringIO()
        with patch.object(module,'ObserverAgent',return_value=fake),patch.object(module,'model_disabled',return_value=True),patch.object(module.sys,'stdin',io.StringIO('\n'.join(map(json.dumps,messages)))),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(module.main(),0)
        response=json.loads(out.getvalue())
        self.assertEqual(response['action'],'finish')
        self.assertEqual(response['decision_sequence'],1)
        self.assertEqual(records[0]['constraints']['reason'],'INTERNAL_ERROR')
        self.assertEqual(records[0]['error']['class'],'KeyError')
        self.assertNotIn('fake-credential-123456',err.getvalue()+json.dumps(records))

    def test_initialize_failure_emits_only_metadata(self):
        import json
        message={'protocol_version':module.PROTOCOL,'message_type':'initialize','payload':{}}
        err=io.StringIO()
        with patch.object(module,'ObserverAgent',side_effect=ValueError('fake-credential-in-init')),patch.object(module,'model_disabled',return_value=True),patch.object(module.sys,'stdin',io.StringIO(json.dumps(message))),contextlib.redirect_stderr(err):
            self.assertEqual(module.main(),0)
        self.assertNotIn('fake-credential-in-init',err.getvalue())
        self.assertIn('"class":"ValueError"',err.getvalue())
        self.assertIn('"frames":',err.getvalue())
