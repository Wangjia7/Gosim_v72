import unittest
import time
from datetime import timedelta
from unittest.mock import patch
from support import NOW, END, LST, fixture, request
import planner as module
from planner import Planner
from skymath import (FiberGrid, shift_altaz, tangent_offsets, altaz_to_radec,
                     radec_to_altaz, max_hour_angle_deg, SIDEREAL_DEG_PER_SECOND)

class GeometryTests(unittest.TestCase):
    def test_science_seeds_can_recover_a_field_outside_proxy_pool(self):
        coords = [altaz_to_radec(60, z, LST, 30) for z in (90, 180)]
        cfg = fixture(coords=coords, required=False)
        cfg['targets']['rows'][0][3:5] = [0.00001, 100]
        selected = []
        with patch.object(module, 'POOL', 1), patch.object(module, 'N_ANCHORS', 1), patch.object(module, 'N_DENSE', 0), patch.object(module, 'EVENT_DURATIONS', 0):
            for count in (0, 1):
                with patch.object(module, 'SCIENCE_ANCHORS', count):
                    action = Planner(cfg).plan(NOW, END, 0, 0)
                    selected.append(set(action['assignments'].values()))
        self.assertEqual(selected, [{'T0'}, {'T1'}])

    def test_loaded_square_grids_and_reduced_search(self):
        for side in (2, 3, 4, 6):
            with self.subTest(side=side):
                p = Planner(fixture(side=side))
                self.assertTrue(p.grid.central_fibers)
                self.assertTrue(all(0 <= f < side*side for f in p.grid.central_fibers))
                for level in (0, 3):
                    p = Planner(fixture(side=side)); p.fast_level = level
                    action = p.plan(NOW, END, 0, 0)
                    self.assertIsNotNone(action)
                    self.assertTrue(all(0 <= int(f) < side*side for f in action['assignments']))
    def test_full_footprint_including_shifted_center(self):
        for side in (2, 4, 6):
            grid = FiberGrid(fixture(side=side)['instrument'])
            for center in ((60, 30), shift_altaz(60, 30, .4, -.4), (85, 359.8)):
                points = [shift_altaz(*center, *grid.fiber_center(f)) for f in (0, grid.n-1)]
                coords = [altaz_to_radec(a,z,LST,30) for a,z in points]
                p = Planner(fixture(coords=coords, side=side))
                cr, cd = altaz_to_radec(*center,LST,30)
                self.assertEqual(set(p.neighbours(cr,cd,grid.query_radius_deg)), {0,1})
                self.assertEqual([grid.classify(*tangent_offsets(a,z,*center))[0] for a,z in points], [0,grid.n-1])
    def test_single_anchor_opposite_corners_are_both_assigned(self):
        grid = FiberGrid(fixture()['instrument'])
        coords = [altaz_to_radec(*shift_altaz(60,30,*grid.fiber_center(f)),LST,30) for f in (0,15)]
        cfg = fixture(coords=coords); cfg['targets']['rows'][0][4] = 100
        with patch.object(module,'N_ANCHORS',1), patch.object(module,'N_DENSE',0):
            action = Planner(cfg).plan(NOW, END, 0, 0)
        self.assertEqual(set(action['assignments'].values()), {'T0','T1'})
    def test_glass_gap_is_unreachable(self):
        grid = FiberGrid(fixture(side=2,gap=.2)['instrument'])
        self.assertIsNone(grid.classify(0,0)[0])
        self.assertEqual(grid.classify(*grid.fiber_center(0))[0],0)

class DurationAndBudgetTests(unittest.TestCase):
    def test_declared_limits_at_all_levels(self):
        for low, high in ((1000,3600),(100,200),(173,173)):
            for level in range(5):
                p = Planner(fixture(minimum=low,maximum=high))
                durations=p.duration_candidates(4000,level,events=(99,174,3601))
                self.assertTrue(durations)
                self.assertEqual(durations,sorted(set(durations)))
                self.assertTrue(all(type(t) is int and low <= t <= high for t in durations))
                p.fast_level=level
                action=p.plan(NOW,END,0,0)
                self.assertIsNotNone(action)
                self.assertTrue(low <= action['duration_seconds'] <= high)
    def test_event_rounding_and_window_endpoint(self):
        p=Planner(fixture(minimum=100,maximum=1000))
        durations=p.duration_candidates(500,events=(173.2,500,501))
        self.assertTrue({173,174,500}.issubset(durations))
        self.assertTrue(all(t <= 500 for t in durations))
        self.assertEqual(p.duration_candidates(0),[])
    def test_minimum_declaration_can_clip_at_horizon(self):
        p=Planner(fixture(minimum=1000,maximum=2000))
        self.assertIn(1000,p.duration_candidates(120))
        action=p.plan(NOW,NOW+timedelta(seconds=120),0,0)
        self.assertIsNotNone(action)
        self.assertGreaterEqual(action['duration_seconds'],1000)
        self.assertEqual(p.pending_duration,120)
    def test_short_setting_visibility_is_used(self):
        ha=max_hour_angle_deg(0,30,20.6)
        coords=[((LST-(ha-450*SIDEREAL_DEG_PER_SECOND))%360,0)]
        p=Planner(fixture(coords=coords,minimum=100,maximum=200))
        action=p.plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        self.assertLessEqual(action['duration_seconds'],200)
    def test_default_limits_use_window_shorter_than_first_coarse_duration(self):
        ha=max_hour_angle_deg(0,30,20.6)
        coords=[((LST-(ha-100*SIDEREAL_DEG_PER_SECOND))%360,0)]
        for events in (0,1):
            with self.subTest(event_refinement=events),patch.object(module,'EVENT_DURATIONS',events):
                p=Planner(fixture(coords=coords,minimum=60,maximum=3600))
                action=p.plan(NOW,END,0,0)
                self.assertIsNotNone(action)
                self.assertLessEqual(p.pending_duration,100)
                self.assertGreaterEqual(action['duration_seconds'],60)
    def test_narrow_request_deadline_survives_coarse_search(self):
        for events in (0,1):
            with self.subTest(event_refinement=events),patch.object(module,'EVENT_DURATIONS',events):
                p=Planner(fixture(minimum=60,maximum=3600,required=False))
                p.on_requests([request(deadline=NOW+timedelta(seconds=100),reward=10000)])
                action=p.plan(NOW,END,0,0)
                self.assertIsNotNone(action)
                self.assertLessEqual(p.pending_duration,100)
                self.assertEqual(p.decision_record['predicted']['request_reward'],10000)
    def test_expired_budget_returns_before_geometry(self):
        p=Planner(fixture()); p.cpu_deadline=time.process_time()-1
        with patch.object(p,'neighbours',side_effect=AssertionError('search after expiry')):
            self.assertTrue(p.budget_expired())
            self.assertIsNone(p.plan(NOW,END,0,0))
    def test_same_input_has_predictable_ties(self):
        coords=[altaz_to_radec(60,180,LST,30)]*2
        a=Planner(fixture(coords=coords)).plan(NOW,END,0,0)
        b=Planner(fixture(coords=coords)).plan(NOW,END,0,0)
        self.assertEqual(a,b)
        self.assertEqual(len(a['assignments']),1)

class ExposureSearchTests(unittest.TestCase):
    def test_science_time_price_is_independent_of_required_bonus_scale(self):
        rates = []
        with patch.object(module, 'SCIENCE_TIME_PRICE', 1), patch.object(module, 'EVENT_DURATIONS', 0):
            for bonus in (50.0, 500.0):
                with patch.object(module, 'REQUIRED_BONUS', bonus):
                    p = Planner(fixture())
                    self.assertIsNotNone(p.plan(NOW, END, 0, 0))
                    rates.append(p.rate_ema)
        self.assertGreater(rates[0], 0)
        self.assertAlmostEqual(rates[0], rates[1])

    def test_saturation_event_beats_coarse_grid_with_prior_best(self):
        p=Planner(fixture(flux=2,required=False,minimum=60,maximum=1000))
        p.cur[0]=.6
        p.rate_ema=.005 / p.lambda_frac
        with patch.object(module,'normalized_airmass',return_value=1), patch.object(module,'REFINE_STEPS',()), patch.object(module,'EVENT_DURATIONS',1):
            action=p.plan(NOW,END,0,0)
        # The public model saturates at 1000/(2*0.97)=515.46s;
        # a positive time price selects its first legal integer successor.
        self.assertEqual(action['duration_seconds'],516)
        self.assertGreater(p.decision_record['predicted']['science_gain'],5.9)
        self.assertEqual(action['program'],'DARK')
    def test_target_selection_changes_with_duration_in_same_cell(self):
        coords=[altaz_to_radec(60,180,LST,30)]*2
        for duration,expected in ((100,'T0'),(1000,'T1')):
            cfg=fixture(coords=coords,required=False,minimum=duration,maximum=duration)
            cfg['targets']['rows'][0][3:5]=[10,1]
            cfg['targets']['rows'][1][3:5]=[1,4]
            with patch.object(module,'normalized_airmass',return_value=1):
                action=Planner(cfg).plan(NOW,END,0,0)
            self.assertEqual(list(action['assignments'].values()),[expected])
    def test_event_refinement_work_is_bounded_for_dense_fields(self):
        coords=[altaz_to_radec(60,180,LST,30)]*200
        cfg=fixture(coords=coords,required=False)
        for i,row in enumerate(cfg['targets']['rows']):
            row[3]=.2+i*.007
        p=Planner(cfg)
        candidates=p.duration_candidates
        event_sizes=[]
        def durations(seconds_left,level=0,events=()):
            result=candidates(seconds_left,level,events)
            if events:
                event_sizes.append(len(result))
            return result
        with patch.object(module,'EVENT_MAX',4), patch.object(module,'REFINE_STEPS',()), patch.object(module,'EVENT_DURATIONS',1), \
             patch.object(p,'duration_candidates',side_effect=durations):
            action=p.plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        self.assertTrue(event_sizes)
        # Four event anchors should keep the expensive duration grid small
        # even when the broad neighborhood contains 200 eligible targets.
        self.assertLess(max(event_sizes),100)

    def test_interrupted_search_retains_and_revalidates_first_candidate(self):
        p=Planner(fixture())
        original=p.neighbours
        interrupted=[False]; calls=[0]
        def neighbours(*args):
            calls[0]+=1
            if calls[0]>=2:
                interrupted[0]=True
            return original(*args)
        with patch.object(p,'neighbours',side_effect=neighbours), \
             patch.object(p,'budget_expired',side_effect=lambda:interrupted[0]):
            action=p.plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        self.assertTrue(p.decision_record['search']['interrupted'])
        center=action['pointing']
        for f,t in action['assignments'].items():
            i=p.index_of[t]; a,z=radec_to_altaz(p.ra[i],p.dec[i],LST,30)
            self.assertEqual(p.grid.classify(*tangent_offsets(a,z,center['alt_deg'],center['az_deg']))[0],int(f))

class RequestTests(unittest.TestCase):
    def test_inclusive_start_and_deadline_boundaries(self):
        p=Planner(fixture()); p.on_requests([request()])
        for start, duration, expected in ((NOW,600,40),(NOW,601,0),(NOW-timedelta(seconds=1),600,0),
                (NOW+timedelta(seconds=1),599,40),(NOW+timedelta(seconds=1),600,0)):
            with self.subTest(start=start,duration=duration):
                self.assertEqual(p.request_gain(0,start,duration,.5),expected)
        self.assertEqual(p.request_gain(0,NOW,600,.5-1e-9),0)
    def test_overlaps_keep_separate_thresholds(self):
        p=Planner(fixture())
        a=request(threshold=.3,reward=10); b=request(threshold=.8,reward=50); b['request_id']='R2'
        p.on_requests([a,b])
        self.assertEqual(p.request_gain(0,NOW,300,.4),10)
        self.assertEqual(p.aggregate_request_gain([0],NOW,300,{0:.4}),10)
        self.assertEqual(p.aggregate_request_gain([0],NOW,300,{0:.8}),60)
    def test_all_or_nothing_and_no_double_count(self):
        coords=[altaz_to_radec(60,180,LST,30)]*3
        p=Planner(fixture(coords=coords)); p.on_requests([request(ids=('T0','T1','T2'),remaining=2)])
        self.assertEqual(p.aggregate_request_gain([0],NOW,300,{0:1}),0)
        self.assertEqual(p.aggregate_request_gain([0,0],NOW,300,{0:1}),0)
        self.assertEqual(p.aggregate_request_gain([0,1],NOW,300,{0:1,1:1}),40)
        self.assertEqual(p.aggregate_request_gain([0,1,2],NOW,300,{0:1,1:1,2:1}),40)
    def test_planner_uses_actual_clipped_interval_for_request_credit(self):
        for deadline_offset,expected in ((120,40),(119,0)):
            p=Planner(fixture(minimum=1000,maximum=2000))
            p.on_requests([request(deadline=NOW+timedelta(seconds=deadline_offset))])
            action=p.plan(NOW,NOW+timedelta(seconds=120),0,0)
            self.assertIsNotNone(action)
            self.assertEqual(p.pending_duration,120)
            self.assertEqual(p.decision_record['predicted']['request_reward'],expected)
    def test_completed_request_has_no_new_reward(self):
        p=Planner(fixture()); p.on_requests([request(remaining=0)])
        self.assertEqual(p.request_gain(0,NOW,300,1),0)

if __name__ == '__main__': unittest.main()
