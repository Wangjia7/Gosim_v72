"""Test-only comparisons to unchanged official runner code, using synthetic inputs.

The observer runtime never imports this module or reads card/truth files.
"""
import contextlib
import copy
import io
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from support import NOW, END, LST, fixture, request
EXAMPLES_ROOT = Path(os.environ.get('GOSIM_EXAMPLES_ROOT', str(Path.home() / 'Documents/gosim-observer-examples')))
sys.path.insert(0,str(EXAMPLES_ROOT / 'runner'))
from challenge.v4_scorer import (BestLedger, SlotTruth, WeatherTruth, score_target_exposure,
    observation_request_status, required_penalty, uniformity_penalty)
from challenge.v4_fiber_map import FiberGrid as OfficialGrid, min_altitude_during
from challenge.v4_runner import normalize_action
from challenge.v4_workflow import V4Workflow, PROTOCOL_VERSION
from planner import Planner
from agent import ObserverAgent
from skymath import altaz_to_radec, max_hour_angle_deg, SIDEREAL_DEG_PER_SECOND

def targets(config):
    return [dict(zip(config['targets']['columns'],row)) for row in config['targets']['rows']]
def official_request(public):
    converted=copy.deepcopy(public)
    converted['issued_at_utc']=NOW.fromisoformat(public['issued_at_utc'])
    converted['deadline_utc']=NOW.fromisoformat(public['deadline_utc'])
    return converted

def record_hit(planner,index,factor,program,ledger):
    # All configured program/mismatch multipliers equal one in certainty fixtures.
    score=planner.weight[0]*factor
    start=NOW+timedelta(seconds=300*index); end=start+timedelta(seconds=300)
    ledger.record(index,'T0',factor,score,start,end)
    planner.pending_program=program; planner.pending_duration=300; planner.pending_start=start
    planner.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'T0','score':round(score,6)}]},end,index)

def certainty_fixture():
    config=fixture()
    config['scoring']['program']['multipliers']={'DARK':1,'BRIGHT':1,'BACKUP':1}
    config['scoring']['program']['mismatch_multiplier']=1
    return config

class OfficialContractTests(unittest.TestCase):
    def test_repeat_science_and_max_factor_are_independent(self):
        p=Planner(fixture())
        ledger=BestLedger()
        for index,factor,mult,program in ((0,.55,1.2,'DARK'),(1,.7,.8,'BACKUP'),(2,.3,1.2,'DARK')):
            score=10*factor*mult
            ledger.record(index,'T0',factor,score,NOW,NOW+timedelta(seconds=300))
            p.pending_program=program; p.pending_duration=300
            p.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'T0','score':score}]},NOW+timedelta(seconds=300),index)
        self.assertAlmostEqual(ledger.best()['T0'][1],6.6)
        self.assertAlmostEqual(ledger.max_factors()['T0'],.7)
        self.assertAlmostEqual(p.cur[0]*p.weight[0],ledger.best()['T0'][1])
        # Public contributions cannot identify the hidden band; truthful intervals contain max factor.
        self.assertLessEqual(p.factor_lower[0],ledger.max_factors()['T0'])
        self.assertGreaterEqual(p.factor_upper[0],ledger.max_factors()['T0'])
    def test_required_and_uniformity_use_independent_configured_thresholds(self):
        config=certainty_fixture()
        config['scoring']['required']={'observed_factor_threshold':.6,'penalty_per_missing':50}
        config['scoring']['uniformity']={'observed_factor_threshold':.8,'ra_band_width_deg':180,'weight':20}
        rows=targets(config)
        second=copy.deepcopy(rows[0]); second.update(target_id='T1',ra_deg=(rows[0]['ra_deg']+180)%360)
        rows.append(second)
        ledger=BestLedger(); ledger.record(0,'T0',.7,7); ledger.record(1,'T1',.9,9)
        self.assertEqual(required_penalty(rows,ledger.max_factors(),config['scoring']),(0,0))
        fractions,penalty=uniformity_penalty(rows,ledger.max_factors(),config['scoring'])
        self.assertEqual(sorted(fractions.values()),[0.,1.]); self.assertAlmostEqual(penalty,10)
        p=Planner(config); record_hit(p,0,.7,'DARK',BestLedger())
        self.assertTrue(p.required_satisfied(0))
        self.assertEqual(p.score_config_uniformity_threshold,.8)
    def test_request_window_equality_and_one_second_overrun_match_official(self):
        for start_delta,duration in ((0,600),(0,601),(-1,600),(1,599),(1,600)):
            p=Planner(fixture()); public=request(); p.on_requests([public])
            start=NOW+timedelta(seconds=start_delta)
            ledger=BestLedger(); ledger.record(0,'T0',.5,5,start,start+timedelta(seconds=duration))
            official=observation_request_status(official_request(public),ledger)
            self.assertEqual(p.aggregate_request_gain([0],start,duration,{0:.5}),official['reward'])
    def test_inflight_result_precedes_half_open_invalidation(self):
        config=certainty_fixture(); ledger=BestLedger()
        with contextlib.redirect_stderr(io.StringIO()):
            agent=ObserverAgent(config,rules_only=True)
        p=agent.planner; record_hit(p,0,.3,'DARK',ledger)
        ledger.record(1,'T0',.8,8,NOW+timedelta(seconds=300),NOW+timedelta(seconds=600))
        ledger.invalidate_window(1,2,'loss')
        p.pending_program='DARK'; p.pending_duration=300; p.pending_start=NOW+timedelta(seconds=300)
        packet={'now_utc':(NOW+timedelta(seconds=600)).isoformat(),
            'last_result':{'action':'observe','observe_index':1,'hits':[{'target_id':'T0','score':8}]},
            'new_messages':[{'record_type':'state_resync','invalidated_window':{'action_index_start':1,'action_index_end_exclusive':2},
                'best_scores':[{'target_id':tid,'best_score':best[1]} for tid,best in ledger.best().items()]}],
            'active_requests':[], 'wallclock':{'remaining_real_cpu_seconds':1000,'wall_remaining_seconds':1000}}
        with contextlib.redirect_stderr(io.StringIO()),patch.object(agent,'_night_advice'),patch.object(agent,'_maybe_report',return_value=None),patch.object(p,'plan',return_value=None):
            agent.respond(packet)
        self.assertFalse(p.hit_ledger[1]['valid']); self.assertTrue(p.hit_ledger[0]['valid'])
        self.assertAlmostEqual(p.cur[0]*10,ledger.best()['T0'][1])
        self.assertFalse(p.required_satisfied(0))
    def test_generated_actions_pass_official_envelope_and_exact_geometry(self):
        for side,minimum,maximum,horizon in ((2,100,200,END),(3,100,200,END),(4,100,200,END),(6,100,200,END),(2,1000,2000,NOW+timedelta(seconds=120))):
            config=fixture(side=side,minimum=minimum,maximum=maximum)
            p=Planner(config); action=p.plan(NOW,horizon,0,0)
            response={'protocol_version':PROTOCOL_VERSION,'message_type':'decision_response','decision_sequence':7,'reason':'synthetic',**action}
            raw=V4Workflow.action_from_response(response,7)
            scenario=SimpleNamespace(fiber_config={'field':{'n_fibers':side*side,'fiber_area_deg2':.4,'gap_deg':0},
                'exposure':config['instrument']['exposure']})
            rows={row['target_id']:row for row in targets(config)}
            normalized=normalize_action(raw,scenario,rows,NOW)
            grid=OfficialGrid(.4,0,side*side)
            point=normalized['pointing']
            for fiber,tid in normalized['assignments'].items():
                row=rows[tid]
                result=grid.classify_target(row['ra_deg'],row['dec_deg'],NOW,point['alt_deg'],point['az_deg'],30,0)
                self.assertEqual(result.fiber_id,fiber); self.assertEqual(result.region,'glass')
                site={**config['site']}
                altitude=min_altitude_during(row['ra_deg'],row['dec_deg'],NOW,min(horizon,NOW+timedelta(seconds=normalized['duration_seconds'])),{'site':site})
                self.assertGreaterEqual(altitude,site['minimum_altitude_deg'])
    def test_short_setting_interval_passes_official_whole_interval_horizon(self):
        ha=max_hour_angle_deg(0,30,20.6)
        coords=[((LST-(ha-450*SIDEREAL_DEG_PER_SECOND))%360,0)]
        config=fixture(coords=coords,minimum=100,maximum=200)
        action=Planner(config).plan(NOW,END,0,0)
        self.assertIsNotNone(action)
        ra,dec=coords[0]
        self.assertGreaterEqual(min_altitude_during(ra,dec,NOW,NOW+timedelta(seconds=action['duration_seconds']),{'site':config['site']}),20)
        self.assertLess(min_altitude_during(ra,dec,NOW,NOW+timedelta(seconds=900),{'site':config['site']}),20)
    def test_official_quality_scoring_saturates_without_accumulating_repeats(self):
        config=certainty_fixture(); config['scoring'].pop('lunar_model')
        target=targets(config)[0]; target['feature_flux']=1
        slot=SlotTruth('S',NOW,END,True,1,1,1,1)
        weather=WeatherTruth([slot],None); ledger=BestLedger()
        p=Planner(certainty_fixture())
        for index,duration in enumerate((300,300,1200)):
            result=score_target_exposure(target,[(duration,slot)],[],weather,duration,1,config['scoring'],NOW,lambda moment:(90,180))
            self.assertAlmostEqual(result.factor,min(duration/1000,1))
            ledger.record(index,'T0',result.factor,result.score,NOW,NOW+timedelta(seconds=duration))
            p.pending_program='DARK'; p.pending_duration=duration
            p.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'T0','score':result.score}]},NOW+timedelta(seconds=duration),index)
            self.assertAlmostEqual(p.cur[0]*p.weight[0],ledger.best()['T0'][1])
            if index==1:
                self.assertFalse(p.required_satisfied(0)); self.assertAlmostEqual(ledger.max_factors()['T0'],.3)
        self.assertTrue(p.required_satisfied(0)); self.assertEqual(ledger.max_factors()['T0'],1)
    def test_remaining_opportunities_exclude_holes_and_depend_on_duration(self):
        config=fixture(minimum=60)
        sidereal_day=360/SIDEREAL_DEG_PER_SECOND
        spans=[(0,3600),(6*3600,600),(sidereal_day,1800),(2*sidereal_day,120)]
        config['survey']['nights']=[{'observing_start_utc':(NOW+timedelta(seconds=start)).isoformat(),
            'observing_end_utc':(NOW+timedelta(seconds=start+duration)).isoformat()} for start,duration in spans]
        config['survey']['end_utc']=config['survey']['nights'][-1]['observing_end_utc']
        p=Planner(config)
        self.assertEqual(p.remaining_opportunities(0,0,100),2)
        self.assertEqual(p.remaining_opportunities(0,0,500),1)
        self.assertEqual(p.remaining_opportunities(0,2,500),0)

if __name__=='__main__': unittest.main()
