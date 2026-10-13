import unittest
from unittest.mock import patch
from support import NOW, END, LST, fixture
import planner as module
from planner import Planner
from skymath import shift_altaz, altaz_to_radec

class ExactProgramCheckpoint(unittest.TestCase):
    def test_one_program_objective_replaces_optimistic_coarse_bound(self):
        coords=[altaz_to_radec(*shift_altaz(60,180,d,0),LST,30) for d in (-.9,.9)]
        config=fixture(coords=coords,required=False,flux=100,minimum=60,maximum=60)
        config['scoring']['program']['bands']={'DARK':.915,'BRIGHT':.4}
        with patch.object(module,'SEASON_GAMMA',0),patch.object(module,'URGENCY',0),patch.object(module,'EVENT_DURATIONS',0),patch.object(module,'PROGRAM_AWARE',1):
            p=Planner(config); action=p.plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        bands={p._band(v['model']*p.calibrated_band_scale(0)) for v in p.pending.values()}
        self.assertGreater(len(bands),1)
        predicted=p.decision_record['predicted']['science_gain']
        # With obligations/urgency/season disabled, exact utility is science.
        self.assertAlmostEqual(p.decision_record['heuristic']['utility'],predicted)
        self.assertLess(predicted,sum(p.weight)*max(p.multipliers.values()))

class RequestChanceAndLeaderRefinement(unittest.TestCase):
    def test_dependence_free_bounds(self):
        self.assertAlmostEqual(Planner.joint_completion_lower_bound([.3],1),.3)
        self.assertAlmostEqual(Planner.joint_completion_lower_bound([.8,.8],2),.6)
        self.assertAlmostEqual(Planner.joint_completion_lower_bound([.8,.8,.8],2),.7)
        self.assertEqual(Planner.joint_completion_lower_bound([1,1],2),1)
    def test_single_uncertain_hit_and_underfilled_progress(self):
        from support import request
        from datetime import timedelta
        with patch.object(module,'SEASON_GAMMA',0):
            p=Planner(fixture(required=False));p.on_requests([request(reward=40)],NOW)
        self.assertEqual(p.aggregate_request_gain([0],NOW,60,{0:1},False),40)
        self.assertAlmostEqual(p.aggregate_request_gain([0],NOW,60,{0:1},True,{0:.3}),12)
        p.on_requests([request(reward=40,remaining=2)],NOW)
        legacy=p.aggregate_request_gain([0],NOW,60,{0:1},True)
        self.assertEqual(legacy,20)
        self.assertEqual(p.aggregate_request_gain([0],NOW,60,{0:1},True,{0:1}),legacy)
        self.assertEqual(p.aggregate_request_gain([0],NOW,60,{0:1},False),0)
    def test_exact_science_time_price_excludes_obligation_bonuses(self):
        from support import request
        rates=[]
        with patch.object(module,'SEASON_GAMMA',0),patch.object(module,'URGENCY',0),patch.object(module,'EVENT_DURATIONS',0),patch.object(module,'LEADER_REFINE',0),patch.object(module,'SCIENCE_TIME_PRICE',1),patch.object(module,'EXACT_TIME_PRICE',1):
            for required in (False,True):
                p=Planner(fixture(required=required,flux=100,minimum=60,maximum=60))
                if required:
                    p.on_requests([request(reward=4000)],NOW)
                action=p.plan(NOW,END,0,0)
                self.assertIsNotNone(action)
                rates.append(p.rate_ema)
        self.assertAlmostEqual(rates[0],rates[1])
        self.assertLess(rates[1],1)
    def test_boosted_target_proxy_is_fully_cancelled(self):
        from support import request
        from types import SimpleNamespace
        utilities=[]
        with patch.object(module,'SEASON_GAMMA',0),patch.object(module,'URGENCY',0),patch.object(module,'EVENT_DURATIONS',0),patch.object(module,'LEADER_REFINE',0):
            for split in (0,1):
                with patch.object(module,'REWARD_SPLIT',split):
                    p=Planner(fixture(required=False,flux=100,minimum=60,maximum=60))
                    p.on_requests([request(reward=40)],NOW)
                    p.group_plan=SimpleNamespace(update=lambda *_:{0})
                    action=p.plan(NOW,END,0,0)
                    self.assertIsNotNone(action)
                    utilities.append(p.decision_record['heuristic']['utility'])
        self.assertAlmostEqual(utilities[0],utilities[1])
    def test_leader_shift_improves_legal_assignment(self):
        coords=[altaz_to_radec(*shift_altaz(60,180,0,d),LST,30) for d in (0,-.29,.29)]
        config=fixture(coords=coords,required=False,flux=100,minimum=60,maximum=60)
        config['targets']['rows'][0][4]=100
        actions=[];gains=[]
        with patch.object(module,'SEASON_GAMMA',0),patch.object(module,'URGENCY',0),patch.object(module,'N_ANCHORS',1),patch.object(module,'N_DENSE',0),patch.object(module,'SCIENCE_ANCHORS',0),patch.object(module,'SPECIAL_ANCHORS',0),patch.object(module,'REFINE_STEPS',()),patch.object(module,'EVENT_DURATIONS',0),patch.object(module,'EDGE_BOX',0):
            for enabled in (0,1):
                with patch.object(module,'LEADER_REFINE',enabled):
                    p=Planner(config);action=p.plan(NOW,END,0,0)
                    actions.append(action);gains.append(p.decision_record['predicted']['science_gain'])
                    from skymath import tangent_offsets,radec_to_altaz
                    for fiber,tid in action['assignments'].items():
                        i=p.index_of[tid]
                        a,z=radec_to_altaz(p.ra[i],p.dec[i],LST,p.lat)
                        reached,_=p.grid.classify(*tangent_offsets(a,z,action['pointing']['alt_deg'],action['pointing']['az_deg']))
                        self.assertEqual(reached,int(fiber))
                    if enabled:self.assertLessEqual(p.leader_refinement_centers,150)
        self.assertGreater(len(actions[1]['assignments']),len(actions[0]['assignments']))
        self.assertGreater(gains[1],gains[0])

class ScoreColumnParity(unittest.TestCase):
    def test_mixed_program_events_requests_and_chance_match_scalar_cache(self):
        from contextlib import ExitStack
        from datetime import timedelta
        from support import request
        from types import SimpleNamespace
        coords=[altaz_to_radec(*shift_altaz(60,180,n,e),LST,30)
                for n,e in ((-.9,0),(.9,0),(0,-.29),(0,.29),(0,.29))]
        config=fixture(coords=coords,required=True,flux=1,minimum=60,maximum=900)
        config['scoring']['program']['bands']={'DARK':.915,'BRIGHT':.4}
        with ExitStack() as stack:
            for name,value in [('SEASON_GAMMA',0),('URGENCY',0),('PROGRAM_AWARE',1),
                               ('SCIENCE_TIME_PRICE',1),('EXACT_TIME_PRICE',1)]:
                stack.enter_context(patch.object(module,name,value))
            for events in (0,1):
                for horizon in (37,600):
                    observations=[]
                    for cached,columns in ((1,0),(1,1),(0,0),(0,1)):
                        with patch.object(module,'GAIN_CACHE',cached),patch.object(module,'SCORE_COLUMNS',columns),patch.object(module,'EVENT_DURATIONS',events):
                            p=Planner(config)
                            p.pointing=SimpleNamespace(p_inside=lambda dn,de,fiber,alt:.8 if fiber%2 else .6, command=lambda alt,az:(alt,az))
                            p.on_requests([request(ids=('T0','T1'),remaining=2,reward=400,deadline=NOW+timedelta(seconds=137))],NOW)
                            action=p.plan(NOW,NOW+timedelta(seconds=horizon),0,0)
                            self.assertIsNotNone(action)
                            record=p.decision_record
                            observations.append((action,record['predicted'],record['heuristic'],p.rate_ema))
                            if not cached:
                                self.assertEqual(record['search']['gain_cache_entries'],0)
                    for observation in observations[1:]:
                        self.assertEqual(observations[0],observation)

class ExpandedWidth(unittest.TestCase):
    def test_width_above_five_reaches_pool_selection(self):
        import os
        import heapq
        coords=[altaz_to_radec(*shift_altaz(60,180,i*.01,0),LST,30) for i in range(20)]
        with patch.dict(os.environ,{'PRO_SEARCH_WIDTH_MAX':'20'}),patch.object(module,'SEASON_GAMMA',0),patch.object(module,'DEEP_POOL',1),patch.object(module,'EVENT_DURATIONS',0):
            p=Planner(fixture(coords=coords,required=False,flux=100,minimum=60,maximum=60))
            p.deep=True;p.fast_level=0;p.search_width_multiplier=10
            with patch.object(module.heapq,'nlargest',wraps=heapq.nlargest) as largest:
                self.assertIsNotNone(p.plan(NOW,END,0,0))
            self.assertEqual(largest.call_args_list[0].args[0],10)
            self.assertEqual(p.effective_search_width(),10)
            p.fast_level=1;self.assertEqual(p.effective_search_width(),1)
            p.fast_level=0;p.deep=False;self.assertEqual(p.effective_search_width(),1)

class SaturatedRequestDensity(unittest.TestCase):
    def test_high_width_zero_density_preserves_timed_anchor(self):
        import os
        from support import request
        with patch.dict(os.environ,{'PRO_SEARCH_WIDTH_MAX':'20'}),patch.object(module,'SEASON_GAMMA',0):
            p=Planner(fixture(required=False,flux=100,minimum=60,maximum=60))
            p.cur[0]=1.2;p.factor[0]=1;p.factor_lower[0]=1;p.factor_upper[0]=1
            p.on_requests([request(reward=40)],NOW)
            p.deep=True;p.search_width_multiplier=10
            action=p.plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        self.assertEqual(action['action'],'observe')
        self.assertIn(p.ids[0],action['assignments'].values())
        self.assertEqual(p.decision_record['predicted']['science_gain'],0)
        self.assertEqual(p.decision_record['predicted']['request_reward'],40)

if __name__ == '__main__':
    unittest.main()
