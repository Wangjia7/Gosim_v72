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
    def test_fair_clock_and_legacy_clock(self):
        a=make_agent()
        self.assertEqual(a._clock(payload(cpu=12)),(12.,1000.,True))
        self.assertEqual(a._clock({'wallclock':{'remaining_seconds':7}}),(7.,7.,False))

if __name__=='__main__': unittest.main()
