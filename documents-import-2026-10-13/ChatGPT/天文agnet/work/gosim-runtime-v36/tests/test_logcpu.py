import copy
from datetime import timedelta
import json
import unittest
from test_normal import fixture
from fusion_core.guarded import Planner
from fusion_core.agent import ObserverAgent
from enhanced_agent import ObserverAgent as Enhanced
from budget import AgentClock
from log_review import ObservationReview
from advisor import Advisor
from test_llm import MockClient

class LogCPUTests(unittest.TestCase):
    def test_900_default_and_authoritative_speed_units(self):
        c=AgentClock(fixture());self.assertEqual(c.read({})[0],900.)
        self.assertEqual(c.read({'wallclock':{'remaining_seconds':899,'speed_factor':2,'clock_mode':'cpu'}})[0],1798)
        self.assertEqual(c.read({'wallclock':{'remaining_seconds':899,'remaining_real_cpu_seconds':1700}})[0],1700)
    def test_wait_and_engine_elapsed_are_not_cpu(self):
        c=AgentClock(fixture());c.account(.2)
        c.read({'wallclock':{'wall_remaining_seconds':5000,'wait_seconds':600,'run_wall_seconds':1200}})
        self.assertAlmostEqual(c.read({})[0],899.8)
        self.assertEqual(c.read({'wallclock':{'remaining_real_cpu_seconds':700,'wall_remaining_seconds':5000}})[0],700)
    def test_legacy_charged_wait_is_explicit(self):
        c=AgentClock(fixture());cpu,wall,fair=c.read({'wallclock':{'clock_mode':'charged_wait','remaining_seconds':40,'remaining_real_cpu_seconds':80,'wall_remaining_seconds':100}})
        self.assertEqual((cpu,wall,fair),(40,40,False))
    def test_long_engine_gaps_do_not_reduce_cpu_search(self):
        for cls in (ObserverAgent,Enhanced):
            choices=[]
            for gap in (0.,100.):
                a=cls(fixture(),rules_only=True);a.engine_ema=gap;a.cost_ema=[.2,.08,.02,.01];a.wall_ema=[.2,.08,.02,.01]
                a._decisions_left=lambda now:100
                if hasattr(a,'deep_ema'):a.deep_ema=[.4,.4]
                a._pace({'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':700,'clock_mode':'cpu'}},a.planner.nights[0][0])
                choices.append((a.planner.fast_level,a.planner.search_scale,getattr(a.planner,'deep',None)))
            self.assertEqual(choices[0],choices[1]);self.assertEqual(choices[0][0],0)
    def test_wall_protection_still_stops_expensive_search(self):
        a=ObserverAgent(fixture(),rules_only=True)
        a._pace({'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':5}},a.planner.nights[0][0])
        self.assertEqual(a.planner.fast_level,4);self.assertFalse(a.planner.deep)
    def test_model_wait_uses_wall_protection_not_cpu_or_engine_forecast(self):
        a=ObserverAgent(fixture(),rules_only=True);a.last_now=a.planner.nights[0][0];a.engine_ema=500;a.model_wait=500
        self.assertEqual(a._model_wait_budget({'wallclock':{'remaining_real_cpu_seconds':.1,'wall_remaining_seconds':5000}}),30)
        self.assertEqual(a._model_wait_budget({'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':8}}),0)
    def prepare(self,p):
        p.pending={t:{'model':1.,'band_model':1.,'alt':55.,'az':100.,'dir_clean':True,'pred':1.,'fiber':k}
            for k,t in enumerate(p.ids)}
        p.pending_program='DARK';p.pending_duration=900;p.pending_night=0;p.pending_notices=set()
    def add(self,r,p,index,factor,notices=()):
        self.prepare(p)
        hits=[{'target_id':t,'score':p.weight[i]*1.2*factor} for i,t in enumerate(p.ids)]
        result={'action':'observe','observe_index':index,'hits':hits}
        return r.record(result,p.nights[0][0]+timedelta(seconds=index*900),notices)
    def test_every_exposure_is_aggregated_and_duplicates_are_ignored(self):
        p=Planner(fixture());r=ObservationReview(p)
        self.assertTrue(self.add(r,p,2,.8));self.assertFalse(self.add(r,p,2,.8))
        r.checkpoint(p.nights[0][0],True);d=r.summary()
        self.assertEqual(d['valid_exposures'],1);self.assertEqual(sum(g['assigned'] for g in d['by_class_program_duration']),2)
        json.dumps(d,allow_nan=False)
    def test_loss_undoes_group_counts_and_repeated_resync_is_idempotent(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(4):self.add(r,p,i,.8)
        message=[{'record_type':'state_resync','invalidated_window':{'action_index_start':1,'action_index_end_exclusive':3}}]
        r.invalidate(message);r.invalidate(message);r.checkpoint(p.nights[0][0],True)
        self.assertEqual(r.valid_count,2);self.assertEqual(r.invalidated_count,2)
        self.assertEqual(sum(g['assigned'] for g in r.summary()['by_class_program_duration']),4)
        self.assertEqual([x['id'] for x in r.recent],[0,3])
    def test_repair_uses_new_epoch_for_quality_comparisons(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(8):self.add(r,p,i,.8)
        r.repaired();self.add(r,p,8,.4);r.checkpoint(p.nights[0][0],True)
        self.assertEqual(r.valid_count,9);self.assertEqual(r.summary()['epoch'],1)
        self.assertEqual(len(r.recent),1);self.assertNotEqual(r.summary()['cue'],'throughput_candidate')
    def test_recent_drop_requires_multiple_independent_clean_exposures(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(24):self.add(r,p,i,.8 if i<16 else .4)
        r.checkpoint(p.nights[0][0],True)
        self.assertEqual(r.summary()['cue'],'throughput_candidate')
        self.assertEqual(p.factor_lower,[0.,0.])  # diagnostic review never certifies or sums factors
    def test_weather_contamination_is_not_clean_throughput_evidence(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(24):self.add(r,p,i,.8 if i<16 else .4,() if i<16 else [('haze','ALL')])
        r.checkpoint(p.nights[0][0],True)
        self.assertEqual(r.summary()['cue'],'weather_or_earthquake_confounded')
    def test_known_weather_in_other_sector_keeps_clean_field_evidence(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(24):self.add(r,p,i,.8 if i<16 else .4,[('haze','N')])
        r.checkpoint(p.nights[0][0],True)
        self.assertEqual(r.summary()['cue'],'throughput_candidate')

    def test_no_hit_and_zero_score_are_distinct(self):
        p=Planner(fixture());r=ObservationReview(p)
        self.prepare(p);r.record({'action':'observe','observe_index':0,'hits':[]},p.nights[0][0])
        self.assertFalse(r.records[0]['closed']);self.assertEqual(r.records[0]['missed'],2)
        self.prepare(p);r.record({'action':'observe','observe_index':1,'hits':[{'target_id':t,'score':0} for t in p.ids]},p.nights[0][0])
        self.assertTrue(r.records[1]['closed']);self.assertEqual(r.records[1]['missed'],0)
    def test_periodic_audit_does_not_rescan_all_old_records(self):
        p=Planner(fixture());r=ObservationReview(p)
        for i in range(100):self.add(r,p,i,.8)
        r.checkpoint(p.nights[0][0],True)
        self.assertEqual(len(r.recent),64);self.assertEqual(len(r.summary()['recent_exposures']),8)
        self.assertEqual(r.valid_count,100)
    def test_long_season_model_quota_is_not_spent_in_first_night(self):
        p=Planner(fixture());start=p.nights[0][0]
        p.nights=[(start+timedelta(days=i),start+timedelta(days=i,hours=8)) for i in range(180)]
        client=MockClient();a=Advisor(client)
        for i in range(65):
            p.history=[None]*i
            a.ingest({'now_utc':start.isoformat(),'new_messages':[],'active_requests':[]},p)
            a.start_night('same-night',[],[],{'rows':[[0]]*4,'log_review':{'cue':'retain','recent_exposures':[{}]*8}},5000,0)
        self.assertEqual(client.tags.count('anomaly_review'),1)
    def test_night_summaries_keep_repair_epochs_and_undo_invalidated_rows(self):
        p=Planner(fixture());r=ObservationReview(p)
        self.add(r,p,0,.8);self.add(r,p,1,.4);r.repaired();self.add(r,p,2,.8)
        r.invalidate([{'record_type':'state_resync','invalidated_window':{'action_index_start':1,'action_index_end_exclusive':2}}])
        r.checkpoint(p.nights[0][0],True)
        nights=r.summary()['recent_nights'];self.assertEqual([x['epoch'] for x in nights],[0,1])
        self.assertEqual([x['exposures'] for x in nights],[1,1])
        self.assertEqual([x['clean_exposures'] for x in nights],[1,1])

    def test_enhanced_resync_drops_derived_anomaly_evidence_not_report_allowance(self):
        a=Enhanced(fixture(),rules_only=True);p=a.planner
        p.e_hours=[(0,0,[.2])];p.e_ratios.append((0,.2));p.band_obs.append((0,1.,'DARK',True,True))
        a.scale_hours[0]=[.2];a.fault_likely=.9;a.false_since_correct=1
        a.respond({'now_utc':fixture()['survey']['start_utc'],'active_requests':[],
            'new_messages':[{'record_type':'state_resync','invalidated_window':{'action_index_start':0,'action_index_end_exclusive':1},'best_scores':[]}],
            'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':7200}})
        self.assertFalse(p.e_hours);self.assertFalse(p.band_obs);self.assertEqual(a.scale_hours,{0:[1.]})
        self.assertIsNone(a.fault_likely);self.assertEqual(a.false_since_correct,1)

    def test_enhanced_applied_review_expires_without_waiting_for_next_hour(self):
        a=Enhanced(fixture(),rules_only=True);client=MockClient();a.rules_only=False;a.client=client;a.advisor=Advisor(client)
        payload={'now_utc':fixture()['survey']['start_utc'],'new_messages':[],'active_requests':[],
            'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':7200}}
        a.respond(payload)
        a._advice_signature=((),0,False)
        a.fault_likely=.9;a.fault_review_version=a.advisor.ledger_version
        payload['last_result']={'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':1.1}]}
        a.respond(payload);self.assertIsNone(a.fault_likely)

    def test_actual_idle_wait_and_between_turn_engine_work_are_not_charged(self):
        import time,threading
        a=ObserverAgent(fixture(),rules_only=True)
        def waiting(_):
            threading.Event().wait(.12)
            return {'action':'wait'}
        a._respond=waiting
        start=time.monotonic();a.respond({});elapsed=time.monotonic()-start
        self.assertGreaterEqual(elapsed,.1);self.assertLess(a.clock.used,elapsed*.5)
        used=a.clock.used
        cpu=time.process_time()
        while time.process_time()-cpu<.03:sum(i*i for i in range(100))
        self.assertEqual(a.clock.used,used)
        self.assertAlmostEqual(a.clock.read({})[0],900.-used)

    def test_expensive_review_cue_does_not_report_by_itself(self):
        a=ObserverAgent(fixture(),rules_only=True);a.log_review.digest={'cue':'throughput_candidate'}
        self.assertIsNone(a._maybe_report(3,{'now_utc':fixture()['survey']['start_utc']}))

if __name__=='__main__':unittest.main()
