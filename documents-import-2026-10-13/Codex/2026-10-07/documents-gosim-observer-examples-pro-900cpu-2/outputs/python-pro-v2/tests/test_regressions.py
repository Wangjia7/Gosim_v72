"""Synthetic public-protocol regressions; no card truth or model endpoint required."""
import sys
import unittest
import math
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planner import Planner
from skymath import FiberGrid, altaz_to_radec, shift_altaz, local_sidereal_deg, parse_utc, format_utc, separation_deg
from exposure import duration_candidates
from agent import ObserverAgent
from review import StepReviewer, validate_review

NOW = parse_utc('2026-01-01T00:00:00Z')


def init(side=4, positions=None):
    instrument = {'grid_side': side, 'n_fibers': side*side, 'glass_side_deg': 0.6,
                  'pitch_deg': 0.7, 'fov_side_deg': side*0.7,
                  'exposure': {'min_duration_seconds': 60, 'max_duration_seconds': 3600}}
    grid = FiberGrid(instrument)
    positions = positions or [shift_altaz(65, 180, *grid.fiber_center(f)) for f in range(grid.n)]
    lst = local_sidereal_deg(NOW, 0)
    rows = [[str(i), *altaz_to_radec(a, z, lst, 30), 0.5, 10., True] for i, (a,z) in enumerate(positions)]
    return {'site': {'latitude_deg': 30, 'longitude_deg': 0, 'minimum_altitude_deg': 20},
            'survey': {'start_utc': format_utc(NOW), 'end_utc': format_utc(NOW+timedelta(hours=6)),
                       'slot_seconds': 900, 'nights': [{'observing_start_utc': format_utc(NOW),
                                                     'observing_end_utc': format_utc(NOW+timedelta(hours=6))}]},
            'instrument': instrument,
            'scoring': {'flux_zero_point': .5, 'exposure_zero_point_seconds': 900, 'q0': .68,
                        'airmass_exponent': .6, 'required': {'observed_factor_threshold': .5},
                        'lunar_model': {'maximum_penalty': .75, 'altitude_exponent': 1, 'angular_decay_scale_deg': 35},
                        'program': {'bands': {'DARK': .65, 'BRIGHT': .4},
                                    'multipliers': {'DARK': 1.2, 'BRIGHT': 1.12, 'BACKUP': 1.06}, 'mismatch_multiplier': 1}},
            'targets': {'columns': ['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'], 'rows': rows}}


def request(deadline=500, threshold=.5, reward=100, issued=0):
    return {'target_ids': ['0'], 'completed_target_ids': [], 'minimum_completed': 1,
            'remaining_count': 1, 'completion_reward': reward, 'completion_factor_threshold': threshold,
            'issued_at_utc': format_utc(NOW+timedelta(seconds=issued)),
            'deadline_utc': format_utc(NOW+timedelta(seconds=deadline))}


class GeometryTests(unittest.TestCase):
    def test_all_layouts_and_levels(self):
        for side in (1,2,4,5):
            for level in range(5):
                with self.subTest(side=side, level=level):
                    p = Planner(init(side)); p.fast_level = level
                    action = p.plan(NOW, p.nights[0][1], 0, 0)
                    self.assertIsNotNone(action)
                    self.assertTrue(all(0 <= int(f) < side*side for f in action['assignments']))
                    self.assertTrue(60 <= action['duration_seconds'] <= 3600)

    def test_opposite_fibres_reachable(self):
        p = Planner(init())
        self.assertGreater(separation_deg(p.ra[0],p.dec[0],p.ra[15],p.dec[15]), 2.1)
        self.assertIn(15, p.neighbours(p.ra[0], p.dec[0], p.grid.neighbour_radius))
        action = p.plan(NOW, p.nights[0][1], 0, 0)
        self.assertEqual(set(action['assignments'].values()), set(p.ids))

    def test_offset_scan_resumes(self):
        p=Planner(init())
        evidence=[((65,180),[(65,180,5,False)])]
        for _ in range(3):
            checks=iter([False]*5+[True])
            with patch.object(p,'budget_expired',side_effect=lambda:next(checks,True)):
                self.assertFalse(p._rescore_offsets(evidence))
        self.assertEqual(p._offset_scan[3],15)
        self.assertTrue(p._rescore_offsets(evidence))
        self.assertIsNone(p._offset_scan)
        self.assertEqual(len(p.offset_scores),len(p.offset_grid))

    def test_coarse_offset_does_not_replace_better_current(self):
        p=Planner(init());p.offset=(.21,-.17);cmd=(65,180)
        rows=[]
        for f in range(p.grid.n):
            dn,de=p.grid.fiber_center(f)
            for delta in (-.28,.28):
                a,z=shift_altaz(cmd[0]+p.offset[0],cmd[1]+p.offset[1],dn+delta,de)
                rows.append((a,z,f,True))
        p.offset_evidence.append((cmd,rows));p.offset_misses=6
        p.pending_cmd=cmd
        p.pending={str(k): {'alt':a,'az':z,'fiber':f} for k,(a,z,f,_) in enumerate(rows)}
        before=p.offset
        with patch.object(p,'_refine_offset'):
            p._offset_evidence({str(k):1 for k in range(len(rows))})
        self.assertEqual(p.offset,before)

    def test_expired_budget_has_useful_fallback(self):
        p=Planner(init());p.cpu_deadline=0
        action=p.plan(NOW,p.nights[0][1],0,0)
        self.assertGreaterEqual(action['duration_seconds'],900)
        self.assertGreater(len(action['assignments']),1)

    def test_pole_and_ra_wrap(self):
        data=init(1); data['targets']['rows']=[['0',359.8,0,.5,1,False],['1',.2,0,.5,1,False],['2',180,89.5,.5,1,False]]
        p=Planner(data)
        self.assertIn(1,p.neighbours(359.8,0,1))
        self.assertIn(2,p.neighbours(0,89.5,2))

    def test_instrument_limits_and_short_night(self):
        data=init(1);data['instrument']['exposure']={'min_duration_seconds': 73,'max_duration_seconds': 147}
        p=Planner(data)
        a=p.plan(NOW,NOW+timedelta(seconds=101),0,0)
        self.assertTrue(73 <= a['duration_seconds'] <= 101)

    def test_pointing_offset_evidence(self):
        p=Planner(init())
        cmd=(65,180); expected=(.21,-.17)
        actual=(cmd[0]+expected[0],cmd[1]+expected[1])
        rows=[]
        # Include off-centre outcomes so zero offset disagrees.
        for f in range(p.grid.n):
            dn,de=p.grid.fiber_center(f)
            for delta in (-.26,.26):
                alt,az=shift_altaz(*actual,dn+delta,de)
                rows.append((alt,az,f,True))
        self.assertGreater(p._consistent(cmd,rows,*expected),p._consistent(cmd,rows,0,0))
        p.offset_evidence.append((cmd,rows));p._rescore_offsets(list(p.offset_evidence));p._refine_offset()
        self.assertGreater(p._consistent(cmd,rows,*p.offset),p._consistent(cmd,rows,0,0))


class StateTests(unittest.TestCase):
    def test_request_exact_deadline_and_overlap(self):
        p=Planner(init(1));p.on_requests([request(500,.5,100),request(1000,.9,200)])
        self.assertGreater(p.request_gain(0,NOW,500,.7),0)
        self.assertEqual(p.request_gain(0,NOW,501,.7),0)
        self.assertGreater(p.request_gain(0,NOW,501,1),0)
        self.assertEqual(p.request_gain(0,NOW,1001,1),0)
        p.on_requests([request(1000,issued=10)])
        self.assertEqual(p.request_gain(0,NOW,500,1),0)

    def test_request_only_target_survives_ranking(self):
        p=Planner(init(1));p.factor[0]=1;p.cur[0]=1.2
        p.on_requests([request(deadline=500,threshold=.2)])
        action=p.plan(NOW,p.nights[0][1],0,0)
        self.assertIsNotNone(action)
        self.assertLessEqual(action['duration_seconds'],500)
        self.assertIn('0',action['assignments'].values())

    def test_short_request_below_coarse_floor(self):
        p=Planner(init(1));p.factor[0]=1;p.cur[0]=1.2
        p.on_requests([request(deadline=180,threshold=.1)])
        action=p.plan(NOW,p.nights[0][1],0,0)
        self.assertIsNotNone(action)
        self.assertLessEqual(action['duration_seconds'],180)

    def test_factor_independent_of_best_score_after_loss(self):
        p=Planner(init(1));p.factor_history={0:[(0,.55)],1:[(0,.48)],2:[(0,.9)]}
        p._resync({'invalidated_window': {'action_index_start':2,'action_index_end_exclusive':3},
                   'best_scores':[{'target_id':'0','best_score':5.76}]})
        self.assertEqual(p.factor[0],.55)
        self.assertAlmostEqual(p.cur[0],.576)
        p._resync({'invalidated_window': {'action_index_start':0,'action_index_end_exclusive':1},
                   'best_scores':[{'target_id':'0','best_score':5.76}]})
        self.assertEqual(p.factor[0],.48)

    def test_resync_unknown_history_conservative(self):
        p=Planner(init(1));p._resync({'best_scores':[{'target_id':'0','best_score':12}]})
        self.assertEqual(p.factor[0],0)
        self.assertEqual(p.cur[0],1.2)

    def test_result_processed_before_resync(self):
        a=ObserverAgent(init(1),True); calls=[]
        a.planner.on_result=lambda *x: calls.append('result')
        a.planner.on_messages=lambda *x: calls.append('messages')
        payload={'now_utc':format_utc(NOW),'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':1800}}
        a.respond(payload)
        self.assertEqual(calls[:2],['result','messages'])


class DurationBudgetTests(unittest.TestCase):
    def test_saturation_threshold_endpoint_neighbours(self):
        points=duration_candidates(60,1000,[.5,1],lambda t:t/733,[617.8])
        for t in (366,367,732,733,734,617,618): self.assertIn(t,points)

    def test_nonmonotone_crossings(self):
        points=duration_candidates(60,1000,[.5],lambda t:1-((t-530)/400)**2,[])
        for root in (530-400/math.sqrt(2),530+400/math.sqrt(2)):
            self.assertIn(math.floor(root),points)
            self.assertIn(math.ceil(root),points)

    def test_constant_quality_saturation_not_fixed_grid(self):
        data=init(1)
        data['scoring']['airmass_exponent']=0
        data['scoring']['lunar_model']['maximum_penalty']=0
        p=Planner(data);p.rate_ema=.01
        action=p.plan(NOW,p.nights[0][1],0,0)
        saturation=p.f0t0*p.q0/(p.flux[0]*.97)
        self.assertLessEqual(abs(action['duration_seconds']-saturation),2)
        self.assertAlmostEqual(p.pending['0']['model'],1/p.q0,places=10)

    def test_emergency_model_budget_and_cost_bucket(self):
        a=ObserverAgent(init(1),True);a.last_now=NOW;a.planner.fast_level=4
        self.assertGreaterEqual(a._model_wait_budget({'wallclock':{'remaining_seconds':10}}),0)
        def respond(_):
            a.planner.fast_level=2
            return {'action':'observe','assignments':{}}
        a._respond=respond
        a.respond({'now_utc':format_utc(NOW),'wallclock':{'remaining_seconds':900}})
        self.assertGreater(a.cost_ema[2],0)
        self.assertEqual(a.cost_ema[0],0)


class ReviewTests(unittest.TestCase):
    def test_reject_invalid_and_nonfinite(self):
        self.assertIsNone(validate_review({'summary':'x','confidence':float('nan')}))
        self.assertIsNone(validate_review({'summary':'x','confidence':True}))
        self.assertIsNone(validate_review({'summary':'x','confidence':.5,'issues':[{}]}))
        self.assertIsNotNone(validate_review({'summary':'x','confidence':.5,'issues':[]}))

    def test_transport_failure_releases_slot(self):
        import http.client
        from llm_client import LLMClient
        client=LLMClient(max_retries=1)
        with patch.object(client,'_request',side_effect=http.client.IncompleteRead(b'partial')):
            call=client.submit('test','test',{},90)
            self.assertTrue(call.wait(1))
        self.assertEqual(client.in_flight(),0)
        self.assertIsNone(client.collect(call))
        self.assertEqual(call.error,'IncompleteRead')

    def test_no_model_and_bounded_queue(self):
        reviewer=StepReviewer(None)
        for k in range(100): reviewer.record(k,{'now_utc':format_utc(NOW)},None,{}, {},900,900)
        self.assertEqual(reviewer.calls,0)
        self.assertEqual(len(reviewer.queue),0)

    def test_async_busy_and_schema(self):
        class Call:
            def done(self): return False
        class Client:
            max_in_flight=4
            def in_flight(self): return 0
            def submit(self,*args): return Call()
        r=StepReviewer(Client())
        for k in range(100): r.record(k,{'now_utc':format_utc(NOW)},None,{}, {},900,900)
        self.assertEqual(r.calls,1)
        self.assertEqual(len(r.queue),16)
        self.assertGreater(r.dropped,0)


if __name__=='__main__': unittest.main()
