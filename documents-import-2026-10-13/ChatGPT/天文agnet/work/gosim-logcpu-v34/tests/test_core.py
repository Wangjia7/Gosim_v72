import copy
import json
import math
import unittest
from datetime import timedelta
from test_normal import fixture
from fusion_core.guarded import Planner
from fusion_core.agent import ObserverAgent
from fusion_core.bandfit import BandFit
from fusion_core.fault import FaultDetector, QUAKE_TRACK
from fusion_core.skymath import format_utc
from test_llm import MockClient
from advisor import Advisor

class CoreTests(unittest.TestCase):
    def observe(self,p,index,score,program='DARK'):
        now=p.nights[0][0]
        p.pending={'t0':{'model':1.,'band_model':1.,'alt':55.,'az':100.,'dir_clean':True,'pred':.6,'fiber':5}}
        p.pending_cmd=(55.,100.);p.pending_program=program;p.pending_duration=900;p.pending_night=0;p.pending_notices=set()
        p.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'t0','score':score}]},now,index)
    def test_raw_and_science_maxima_are_independent_after_loss(self):
        p=Planner(fixture())
        self.observe(p,0,1.56,'DARK')
        self.observe(p,1,1.4,'BACKUP')
        self.assertGreater(p.factor_lower[0],.66)
        p._resync({'invalidated_window':{'action_index_start':1,'action_index_end_exclusive':2},'best_scores':[{'target_id':'t0','best_score':1.56}]})
        self.assertAlmostEqual(p.factor_lower[0],.65,places=5)
        self.assertEqual(p.cur[0],.78)
        self.assertEqual(p.opportunities.p,p)
    def test_duplicate_result_does_not_add_fault_evidence(self):
        p=Planner(fixture());self.observe(p,4,1.1);self.observe(p,4,1.1)
        self.assertEqual(len(p.history),1);self.assertIsNone(p.exposure_meta)
    def test_loss_removes_geometry_evidence(self):
        p=Planner(fixture());self.observe(p,0,1.1)
        p._resync({'invalidated_window':{'action_index_start':0,'action_index_end_exclusive':1},'best_scores':[]})
        self.assertEqual(p.factor_lower[0],0.);self.assertEqual(len(p.offset_evidence),0)
    def test_repair_epoch_survives_replay(self):
        p=Planner(fixture());self.observe(p,0,1.1);p.forget_quality_history();self.observe(p,1,1.3)
        p._resync({'best_scores':[{'target_id':'t0','best_score':1.3}]})
        self.assertEqual(p.calibration_epoch,1)
        self.assertEqual([r['epoch'] for r in p.history],[0,1])
        self.assertTrue(all(h>=1 for h,_ in p.samples))
    def test_each_request_uses_its_own_full_exposure_window(self):
        p=Planner(fixture());now=p.nights[0][0]
        def r(rid,end,threshold,reward):return {'request_id':rid,'issued_at_utc':format_utc(now),'deadline_utc':format_utc(now+timedelta(seconds=end)),
            'target_ids':['t0'],'minimum_completed':1,'completion_factor_threshold':threshold,'completion_reward':reward}
        p.on_requests([r('soon',300,.1,100),r('later',1800,.2,10)],now)
        a=p.request_value(0,600,1.,now.timestamp());b=p.request_value(0,300,1.,now.timestamp())
        self.assertLess(a,b);self.assertLessEqual(a,100.)
        self.assertEqual(p.request_value(0,1801,1.,now.timestamp()),0.)
    def test_runtime_required_threshold_and_duration_bounds(self):
        d=fixture();d['scoring']['required']['observed_factor_threshold']=.7;d['scoring']['required']['penalty_per_missing']=80
        d['instrument']['exposure']['min_duration_seconds']=700;d['instrument']['exposure']['max_duration_seconds']=800
        p=Planner(d);now=p.nights[0][0];a=p.plan(now,p.nights[0][1],0,0)
        self.assertEqual(p.required_bonus,128.);self.assertEqual(p.required_threshold,.7)
        self.assertGreaterEqual(a['duration_seconds'],700);self.assertLessEqual(a['duration_seconds'],800)
    def test_bandfit_configuration_and_known_physics(self):
        a=BandFit({'DARK':.65,'BRIGHT':.4},{'DARK':1.2,'BRIGHT':1.12,'BACKUP':1.06},1.)
        rows=[[m,.7*.8*(1. if m*.8>=.65 else 1./1.2),False,0.,True] for m in [.6,.7,.9,1.]]
        before=a.exposure_bounds('DARK',rows)
        BandFit({'DARK':.9,'BRIGHT':.5},{'DARK':1.5,'BRIGHT':1.2,'BACKUP':1.1},1.)
        self.assertEqual(before,a.exposure_bounds('DARK',rows));self.assertLessEqual(before[0],.7);self.assertGreaterEqual(before[1],.7)
    def test_quake_curve_disabled_and_no_absolute_probe(self):
        self.assertEqual(QUAKE_TRACK,0)
        d=FaultDetector(2);d.add_exposure(0.,0,.1,[('earthquake','ALL')],(.01,.1,'both'))
        d.add_exposure(3.,0,.1,[('earthquake','ALL')],(.01,.1,'both'))
        self.assertIsNone(d.bound_evidence(3.));self.assertFalse(d.should_report(3.,[('earthquake','ALL')]))
    def test_two_mock_llm_roles_in_fused_agent(self):
        a=ObserverAgent(fixture(),rules_only=True);client=MockClient();a.rules_only=False;a.client=client;a.advisor=Advisor(client)
        payload={'now_utc':fixture()['survey']['start_utc'],'new_messages':[{'record_type':'operator_note','message_id':'o1','text':'优先 t0'}],
            'active_requests':[],'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}
        action=a.respond(payload)
        self.assertEqual(action['action'],'observe')
        self.assertIn('operator_nlp',client.tags);self.assertIn('anomaly_review',client.tags)
    def test_common_program_uses_marginal_science(self):
        from unittest.mock import patch
        from fusion_core import planner as module
        d=fixture();d['scoring']['q0']=1
        d['instrument']['exposure']={'min_duration_seconds':900,'max_duration_seconds':900}
        for row,reach,q,w in zip(d['targets']['rows'],(.6,1),(.7,.55),(10,4)):
            row[4]=reach*450/(900*q*.97);row[5]=w
        qa={row[1]:q for row,q in zip(d['targets']['rows'],(.7,.55))}
        class Moon:
            def __init__(self,*args):pass
            def lunar_factor(self,ra,dec):return qa[ra]
        with patch.object(module,'Moon',Moon),patch.object(module,'normalized_airmass',lambda _:1):
            p=Planner(d);p.cur=[.715,0];p.factor=[.5958333,0];p.lambda_frac=0
            a=p.plan(p.nights[0][0],p.nights[0][1],0,0)
        self.assertEqual(a['program'],'BRIGHT');self.assertIn('t1',a['assignments'].values())
    def test_fused_native_matches_python_including_cell_ties(self):
        from unittest.mock import patch
        from fusion_core import planner as module
        d=fixture();d['targets']['rows']+=copy.deepcopy(d['targets']['rows'])
        d['targets']['rows'][2][0]='t2';d['targets']['rows'][3][0]='t3'
        actions=[]
        for lib in (module.CELL_LIB,None):
            with patch.object(module,'CELL_LIB',lib):
                p=Planner(d);p.deep=True
                actions.append(p.plan(p.nights[0][0],p.nights[0][1],0,0))
        self.assertEqual(actions[0],actions[1]);self.assertIsNotNone(module.CELL_LIB)
    def test_pacing_records_actual_search_level(self):
        from unittest.mock import patch
        a=ObserverAgent(fixture(),rules_only=True);a.planner.deep=True
        def changed(payload):
            a.planner.fast_level=1;a.planner.deep=False
            return {'action':'observe'}
        a._respond=changed
        with patch('time.process_time',side_effect=[10.,10.09]),patch('time.monotonic',side_effect=[100.,100.1,100.1]):
            a.respond({})
        self.assertAlmostEqual(a.cost_ema[1],.09);self.assertEqual(a.cost_ema[0],0.)
        self.assertEqual(a.deep_ema[0],0.)

    def test_monitor_is_available_without_science_value(self):
        p=Planner(fixture());now=p.nights[0][0]
        p.factor=[1.]*len(p.ids);p.cur=[1.2]*len(p.ids)
        a=p.monitor(now,p.nights[0][1],0,0)
        self.assertIsNotNone(a);self.assertEqual(a['action'],'observe')
        self.assertIn(a['program'],p.multipliers)

    def test_new_weather_notice_filters_pending_but_quake_preserves_band(self):
        for kind,ongoing,expected in [('overcast',False,False),('earthquake',False,True),('cold_snap',True,True)]:
            a=ObserverAgent(fixture(),rules_only=True);p=a.planner
            p.pending={'t0':{'model':1.,'band_model':1.,'alt':55.,'az':100.,'dir_clean':True,'clean':True,'pred':.6,'fiber':5}}
            p.pending_cmd=(55.,100.);p.pending_program='DARK';p.pending_duration=900;p.pending_night=0;p.pending_notices={(kind,'ALL')} if ongoing else set()
            a.respond({'now_utc':fixture()['survey']['start_utc'],
                'new_messages':[{'record_type':'bulletin','notices':[{'event_kind':kind,'direction':'ALL'}]}],
                'latest_bulletin':{'notices':[{'event_kind':kind,'direction':'ALL'}]},'active_requests':[],
                'last_result':{'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':1.1}]},
                'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}})
            self.assertEqual(p.history[0]['pending']['t0']['dir_clean'],expected)
    def test_applied_anomaly_review_expires_at_next_ledger_version(self):
        a=ObserverAgent(fixture(),rules_only=True);client=MockClient();a.rules_only=False;a.client=client;a.advisor=Advisor(client)
        payload={'now_utc':fixture()['survey']['start_utc'],'new_messages':[],'active_requests':[],
            'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}
        a.respond(payload);self.assertEqual(a.fault_likely,.1)
        payload['last_result']={'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':1.1}]}
        a.respond(payload);self.assertIsNone(a.fault_likely)

    def test_no_oracle_or_truth_hooks_in_fused_runtime(self):
        from pathlib import Path
        import fusion_core
        core=Path(fusion_core.__file__).parent
        for path in core.glob('*.py'):
            self.assertNotIn('ORACLE_REPORTS',path.read_text())
            self.assertNotIn('V5_DUMP_HITS',path.read_text())

if __name__=='__main__':unittest.main()
