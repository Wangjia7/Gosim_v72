import copy
from collections import deque
from datetime import timedelta
import json
import io
import time
import unittest
from unittest.mock import patch
from test_normal import fixture
import planner as module
from planner import Planner
from fusion_core.guarded import Planner as CorePlanner
from enhanced_agent import ObserverAgent
from conditions import sky_interval, HealthWatch
from events import EventQueue, validate_event
from runtime import Runtime
from advisor import Advisor
from test_llm import Ready, MockClient
from skymath import parse_utc, format_utc


def event(p,kind='hardware_work',seconds=600,duration=0,identity='camera'):
    start=p.nights[0][0]+timedelta(seconds=seconds)
    quote=f'工程组通知：11/2（UTC）{start:%H:%M} 导星相机作业。'
    if duration:quote=f'工程组通知：11/2（UTC）{start:%H:%M} 到 {(start+timedelta(seconds=duration)):%H:%M} 设备测试。'
    row={'event_id':identity,'kind':kind,'operation':'upsert','start_utc':format_utc(start),
         'end_utc':format_utc(start+timedelta(seconds=duration)), 'source_id':'note',
         'quote':quote,'time_quote':quote,'time_basis':'explicit_utc','confirmation':'confirmed'}
    return row,{'note':quote}


class ConditionsTests(unittest.TestCase):
    def test_repair_validation_waits_through_confounded_weather(self):
        watch=HealthWatch(Planner(fixture()));watch.recovery_pending=True
        watch.state='weather_confounded'
        self.assertFalse(watch.diagnostic_due(1e6));self.assertTrue(watch.recovery_pending)
        watch.state='inconclusive'
        self.assertTrue(watch.diagnostic_due(1e6))
    def test_single_target_diagnostics_progress_to_report_evidence(self):
        p=Planner(fixture());watch=HealthWatch(p);now=p.nights[0][0]
        watch.healthy.append(.5)
        for index in range(3):
            p.pending={'t0':{'model':1.,'dir_clean':True}};p.pending_duration=300;p.pending_program='DARK'
            watch.observe({'action':'observe','observe_index':index,'hits':[{'target_id':'t0','score':.001}]},now+timedelta(seconds=index*900),set())
        self.assertTrue(watch.report_due((now+timedelta(seconds=1801)).timestamp(),2))
    def test_one_sided_saturation_can_release_recovery(self):
        p=Planner(fixture());watch=HealthWatch(p);watch.recovery_pending=True
        p.pending={'t0':{'model':1.,'dir_clean':True}};p.pending_duration=300;p.pending_program='DARK'
        watch.observe({'action':'observe','observe_index':0,'hits':[{'target_id':'t0','score':2.4}]},p.nights[0][0],set())
        self.assertFalse(watch.recovery_pending);self.assertEqual(watch.state,'normal')
    def test_severe_drop_cannot_return_normal(self):
        for cls in (Planner,CorePlanner):
            p=cls.__new__(cls);p.bands={'DARK':.65,'BRIGHT':.4}
            p.band_obs=[(10.,1.,'DARK',True,True)]*4
            for ratio in (.002,.01,.05):
                p.e_ratios=deque([(10.,ratio)]*4)
                self.assertLess(p.clean_e(10.),.1)
                self.assertEqual(p.condition_fit['status'],'identified')
    def test_core_efficiency_fix_does_not_change_science_or_band_state(self):
        p=CorePlanner(fixture());p.band_obs=[(10.,1.,'DARK',True,True)]*4
        p.e_ratios=deque([(10.,.002)]*4);state=copy.deepcopy((p.factor,p.factor_lower,p.cur,p.band_level))
        with patch.dict('os.environ',{'FUSION_IDENTIFIABLE_E':'0'}):old=p.clean_e(10.)
        self.assertEqual(old,1.);self.assertLess(p.clean_e(10.),.1)
        self.assertEqual(state,(p.factor,p.factor_lower,p.cur,p.band_level))
    def test_contradictory_bands_and_backup_are_unknown(self):
        p=Planner.__new__(Planner);p.bands={'DARK':.65,'BRIGHT':.4}
        p.e_ratios=deque([(10.,.002)]*4)
        p.band_obs=[(10.,1.,'DARK',True,True)]*4+[(10.,1.,'BACKUP',True,True)]*4
        self.assertIsNone(p.clean_e(10.));self.assertEqual(p.condition_fit['status'],'inconsistent')
        p.band_obs=[(10.,1.,'BACKUP',True,True)]*4
        self.assertIsNone(p.clean_e(10.))
    def test_mismatch_ambiguity_cannot_constrain_sky(self):
        fit=sky_interval([(0.,1.,'DARK',False,True)]*4,{'DARK':.65,'BRIGHT':.4})
        self.assertEqual(fit['status'],'inconclusive');self.assertEqual(fit['samples'],0)
    def test_quality_has_no_physical_floor(self):
        p=Planner(fixture());p.samples=deque([(1.,.002)]*4);p.all_ratios=deque([.8]*8)
        p.update_scale(1.);self.assertAlmostEqual(p.scale,.002)
    def test_independent_low_reference_and_report_scope(self):
        p=Planner(fixture());watch=HealthWatch(p);now=p.nights[0][0]
        def feed(index,score):
            p.pending={t:{'model':1.,'dir_clean':True} for t in p.ids}
            p.pending_program='DARK';p.pending_duration=900
            watch.observe({'action':'observe','observe_index':index,'hits':[{'target_id':t,'score':score} for t in p.ids]},now+timedelta(seconds=300*index),set())
        feed(0,1.0)
        for i in range(1,4):feed(i,.005)
        self.assertEqual(watch.state,'throughput_candidate')
        self.assertTrue(watch.report_due((now+timedelta(seconds=1000)).timestamp(),2))
        self.assertFalse(watch.report_due((now+timedelta(seconds=1000)).timestamp(),0))
    def test_false_repair_does_not_clear_evidence(self):
        watch=HealthWatch(Planner(fixture()));watch.rows.append({'id':0})
        watch.report_result({'correct':False,'repaired':False},1)
        self.assertEqual(watch.epoch,0);self.assertEqual(len(watch.rows),1)
        watch.report_result({'correct':True,'repaired':True},2)
        self.assertEqual(watch.epoch,1);self.assertFalse(watch.rows);self.assertTrue(watch.recovery_pending)


class EventTests(unittest.TestCase):
    def test_mixed_event_answer_keeps_valid_and_discards_uncertain(self):
        e,s=event(self.p);a=Advisor(object());now=self.p.nights[0][0]
        a.ingest({'now_utc':format_utc(now),'operator_messages':[{'message_id':'note','text':s['note']}]},self.p)
        a.sources=s
        answer=a._valid_plan({'bad_night':False,'events':[e,{**e,'event_id':'rumour','confirmation':'uncertain'}]})
        self.assertEqual(len(answer['events']),1);self.assertEqual(a.coverage['events_rejected'],1)
    def test_cross_reference_start_cannot_stand_in_for_end(self):
        e,s=event(self.p,'downtime',600,900)
        source='11/2 03:10 设备测试。\nUTC+02:00 已确认。'
        e.update({'quote':source.splitlines()[0],'time_quote':source,'time_basis':'cross_reference',
                  'local_start':'2026-11-02T03:10:00','utc_offset_minutes':120,
                  'local_end':'2026-11-02T07:10:00','end_utc':'2026-11-02T05:10:00Z'})
        self.q.apply([e],{'note':source});self.assertFalse(self.q.events)
    def test_diagnostic_respects_minimum_longer_than300(self):
        d=fixture();d['instrument']['exposure']['min_duration_seconds']=600
        p=Planner(d);a=Runtime(p).diagnostic(p.nights[0][0],p.nights[0][1])
        self.assertIsNotNone(a);self.assertEqual(a['duration_seconds'],600)
    def setUp(self):self.p=Planner(fixture());self.q=EventQueue(self.p)
    def test_future_event_persists_and_never_reports_early(self):
        e,s=event(self.p);self.q.apply([e],s);start=self.p.nights[0][0].timestamp()
        self.assertIsNone(self.q.due_hardware(start));self.assertIsNotNone(self.q.due_hardware(start+600))
        self.q.reported(self.q.due_hardware(start+600));self.assertIsNone(self.q.due_hardware(start+601))
    def test_unquoted_end_and_year2099_rejected(self):
        e,s=event(self.p,'downtime',600,900);e['end_utc']='2099-01-01T00:00:00Z'
        self.q.apply([e],s);self.assertFalse(self.q.events)
        e['end_utc']=format_utc(self.p.nights[0][0]+timedelta(seconds=2100))
        self.q.apply([e],s);self.assertFalse(self.q.events)
    def test_processed_same_identity_rescheduled(self):
        e,s=event(self.p);self.q.apply([e],s);stamp=self.p.nights[0][0].timestamp()
        self.q.reported(self.q.due_hardware(stamp+600))
        new,ns=event(self.p,seconds=1200);self.q.apply([new],ns)
        self.assertIsNone(self.q.due_hardware(stamp+601));self.assertIsNotNone(self.q.due_hardware(stamp+1200))
    def test_cross_reference_requires_real_offset(self):
        e,s=event(self.p)
        text='工程组通知：11/2 3:10 导星相机作业。\n同一件事，11/2（UTC）1:10。'
        e.update({'quote':text.splitlines()[0],'time_quote':text,'time_basis':'cross_reference',
                  'local_start':'2026-11-02T03:10:00','utc_offset_minutes':120})
        self.q.apply([e],{'note':text});self.assertIn('camera',self.q.events)
        bad={**e,'event_id':'bad','utc_offset_minutes':180};self.q.apply([bad],{'note':text});self.assertNotIn('bad',self.q.events)
    def test_wait_is_cut_at_engineering_boundary(self):
        rt=Runtime(self.p);e,s=event(self.p);rt.events.apply([e],s)
        a=rt.clip_wait({'action':'wait','duration_seconds':1800},self.p.nights[0][0])
        self.assertEqual(parse_utc(a['until_utc']),self.p.nights[0][0]+timedelta(seconds=600))
    def test_known_terrain_does_not_remove_existing_constraint(self):
        p=self.p;p.terrain={'N'}
        e,s=event(p,'terrain',0);e['directions']=['N'];e['min_altitude_deg']=20
        q=EventQueue(p);q.apply([e],s);p.events=q
        self.assertEqual(p._direction_factor(30,0),0.)
    def test_zero_run_waits_between_independent_probes(self):
        rt=Runtime(self.p);now=self.p.nights[0][0];rt.health.state='unavailable_candidate'
        rt.health.zero_run=2;rt.health.last_probe=now.timestamp()
        agent=ObserverAgent(fixture(),rules_only=True)
        a,_=rt.before_plan(agent,{},now+timedelta(seconds=300),self.p.nights[0][1])
        self.assertEqual(a['action'],'wait')
    def test_cancel_before_upsert_and_duplicate_are_idempotent(self):
        e,s=event(self.p);cancel={**e,'operation':'cancel','quote':'工程组取消导星相机作业。'}
        self.q.apply([cancel],{'note':cancel['quote']});self.q.apply([e],s);self.q.apply([e],s)
        self.assertIsNone(self.q.due_hardware(self.p.nights[0][0].timestamp()+700));self.assertEqual(len(self.q.events),1)
    def test_correction_supersedes_old_time(self):
        e,s=event(self.p);self.q.apply([e],s)
        new,ns=event(self.p,seconds=1200,identity='camera-new');new['replaces']='camera'
        self.q.apply([new],ns);stamp=self.p.nights[0][0].timestamp()
        self.assertIsNone(self.q.due_hardware(stamp+700));self.assertEqual(self.q.due_hardware(stamp+1200)['event_id'],'camera-new')
    def test_invalid_quote_rumour_and_wrong_utc_rejected(self):
        e,s=event(self.p);e['start_utc']=format_utc(self.p.nights[0][0]+timedelta(seconds=900))
        self.q.apply([e],s);self.assertFalse(self.q.events)
        e,s=event(self.p);e['quote']='听说 '+e['quote'];s['note']=e['quote'];self.q.apply([e],s);self.assertFalse(self.q.events)
    def test_lamps_wait_not_report_and_cut_future_window(self):
        rt=Runtime(self.p);e,s=event(self.p,'lamp_test',600,900);rt.events.apply([e],s)
        start=self.p.nights[0][0];end=self.p.nights[0][1]
        self.assertEqual(rt.events.next_boundary(start.timestamp(),end.timestamp()),start.timestamp()+600)
        a,_=rt.before_plan(ObserverAgent(fixture(),rules_only=True),{},start+timedelta(seconds=700),end)
        self.assertEqual(a['action'],'wait');self.assertEqual(parse_utc(a['until_utc']),start+timedelta(seconds=1500))
    def test_full_text_tail_and_expired_preference_keep_event(self):
        p=self.p;e,s=event(p);raw='普通交接。\n'*1000+s['note']
        class Mock:
            def submit(self,tag,system,user,left):
                if tag!='operator_nlp':return Ready({'ledger_version':user['ledger_version'],'fault_likely':0.,'diagnosis':'normal','recommendation':'retain'})
                text=''.join(x['text'] for x in user['sources'] if x['source_id']=='note')
                return Ready({'bad_night':False,'events':[e] if e['quote'] in text else [],'sources':[]})
            def collect(self,c):return c.answer
        a=Advisor(Mock());payload={'now_utc':format_utc(p.nights[0][0]),'active_requests':[{'request_id':'note','reason':raw,'deadline_utc':format_utc(p.nights[0][0]+timedelta(seconds=30))}]}
        a.ingest(payload,p);q=EventQueue(p)
        while a.pending_texts:
            plan,_=a.start_night('2026-11-02',[],[],{'rows':[]},300,1)
            if plan:q.apply(plan['events'],plan['event_sources'])
        self.assertIn('camera',q.events);self.assertGreater(a.coverage['chunks_submitted'],1)
        self.assertEqual(a.coverage['chunks_accepted'],a.coverage['chunks_submitted'])
    def test_resync_preserves_common_queue(self):
        p=CorePlanner(fixture());rt=Runtime(p);e,s=event(p);rt.events.apply([e],s)
        p._resync({'best_scores':[]})
        self.assertIs(p.events,rt.events);self.assertIs(p.obligations,rt.obligations)


class ObligationTests(unittest.TestCase):
    def test_sequence_cpu_deadline_returns_fallback(self):
        p=Planner(fixture());o=Runtime(p).obligations;now=p.nights[0][0].timestamp()
        self.assertIsNone(o.sequence([0,1],.5,now,now+900,deadline=time.process_time()-1))
    def test_distinct_fibres_share_visit_occupation(self):
        p=Planner(fixture());o=Runtime(p).obligations;now=p.nights[0][0].timestamp()
        o.target_options=lambda i,t,s,e:[(s,e,300)]
        visits=o.sequence([0,1],.5,now,now+300)
        self.assertIsNotNone(visits);self.assertEqual(o.occupied_seconds(visits),300)
    def test_unmanaged_request_keeps_legacy_gain(self):
        p=CorePlanner(fixture());o=Runtime(p).obligations;now=p.nights[0][0]
        p.on_requests([self.request(p)],now)
        expected=p.request_value(0,900,1.,now.timestamp())
        o.active=True;o.urgent_required={1}
        self.assertEqual(p.request_value(0,900,1.,now.timestamp()),expected)
    def test_wait_within_bucket_updates_actual_stamp(self):
        p=Planner(fixture());o=Runtime(p).obligations;now=p.nights[0][0]
        r=self.request(p,deadline=180)
        o.refresh([r],now,1);o.refresh([r],now+timedelta(seconds=150),1)
        self.assertEqual(o.stamp,(now+timedelta(seconds=150)).timestamp())
        self.assertEqual(o.guide(0,60,1.),0.)
    def test_landing_probability_cannot_multiply_group_reward(self):
        p=Planner(fixture());o=Runtime(p).obligations;now=p.nights[0][0]
        o.refresh([self.request(p,minimum=2)],now,1)
        guides=sum(o.guide(i,600,1.)*3 for i in (0,1))
        actual=o.field_adjustment({5:0,6:1},600,lambda i:1.,{5:4.,6:4.},{0:3.,1:3.})+guides
        self.assertAlmostEqual(actual,1000.)
    def request(self,p,minimum=1,deadline=600):
        now=p.nights[0][0]
        return {'request_id':'r','target_ids':p.ids,'minimum_completed':minimum,'remaining_count':minimum,
                'completion_factor_threshold':.5,'completion_reward':1000.,'issued_at_utc':format_utc(now),
                'deadline_utc':format_utc(now+timedelta(seconds=deadline))}
    def test_select_minimal_viable_subset_and_no_predicted_credit(self):
        p=Planner(fixture());rt=Runtime(p);r=self.request(p)
        rt.obligations.refresh([r],p.nights[0][0],1)
        self.assertEqual(len(rt.obligations.groups),1);self.assertEqual(len(rt.obligations.groups[0]['subset']),1)
        self.assertEqual(p.factor,[0.,0.]);self.assertEqual(p.cur,[0.,0.])
    def test_jointly_impossible_sequence_has_no_reservation(self):
        p=Planner(fixture());p.ra[1]=p.ra[0];p.dec[1]=p.dec[0]
        o=Runtime(p).obligations;o.stamp=p.nights[0][0].timestamp()
        o.target_options=lambda i,t,s,e:[(s,e,300)]
        self.assertIsNone(o.sequence([0,1],.5,o.stamp,o.stamp+500))
        self.assertIsNotNone(o.sequence([0,1],.5,o.stamp,o.stamp+600))
    def test_downtime_removes_entire_exposure_windows(self):
        p=Planner(fixture());rt=Runtime(p);e,s=event(p,'downtime',0,3600);rt.events.apply([e],s)
        rt.obligations.refresh([self.request(p,deadline=1800)],p.nights[0][0],1)
        self.assertFalse(rt.obligations.groups)
    def test_factor_not_subtracted_from_needed_single_exposure(self):
        p=Planner(fixture());o=Runtime(p).obligations;start=p.nights[0][0].timestamp()
        initial=o.target_options(0,.5,start,start+3600)
        p.factor[0]=.49;o.options={}
        self.assertEqual(initial,o.target_options(0,.5,start,start+3600))
    def test_group_bonus_once_and_no_bonus_crossing_deadline(self):
        p=Planner(fixture());o=Runtime(p).obligations;now=p.nights[0][0]
        o.refresh([self.request(p,minimum=2)],now,1)
        self.assertEqual(len(o.groups),1)
        # Guide subtraction followed by one complete-group bonus.
        self.assertAlmostEqual(o.field_adjustment({5:0,6:1},600,lambda i:1.)+sum(o.guide(i,600,1.) for i in [0,1]),1000.)
        self.assertEqual(o.guide(0,1801,1.),0.)
    def test_active_group_native_python_equivalence(self):
        if module.LIB is None:self.skipTest('native unavailable')
        d=fixture();p=Planner(d);rt=Runtime(p);r=self.request(p,minimum=2)
        p.on_requests([r]);rt.obligations.refresh([r],p.nights[0][0],1)
        p.lambda_frac=0;p.cpu_turn_budget=10
        native=p.plan(p.nights[0][0],p.nights[0][1],0,0)
        q=Planner(d);rq=Runtime(q);q.on_requests([r]);rq.obligations.refresh([r],q.nights[0][0],1)
        q.lambda_frac=0;q.cpu_turn_budget=10
        with patch.object(module,'LIB',None):python=q.plan(q.nights[0][0],q.nights[0][1],0,0)
        self.assertEqual(native,python)
        self.assertEqual(p.pending,q.pending)
    def test_limited_cpu_retains_legal_fallback(self):
        p=Planner(fixture());o=Runtime(p).obligations
        o.refresh([self.request(p)],p.nights[0][0],0.)
        self.assertGreaterEqual(o.cpu,0.);self.assertTrue(all(a<b for a,b,i in o.reservations))


class PipelineTests(unittest.TestCase):
    def test_science_forecast_retains_gain_above_mismatch_plateau(self):
        p,rt,now=self.guard_fixture();p.cur[0]=1.1
        p.pending={'t0':{'pred':1.,'pred_score_factor':.97,'pred_multiplier':1.2,'p':2.}}
        action={'program':'DARK','duration_seconds':600}
        self.assertAlmostEqual(rt.forecast(action,[],now)[0],2*(.97*1.2-1.1))
        p.pending['t0']['pred_multiplier']=p.mismatch
        self.assertEqual(rt.forecast(action,[],now)[0],0.)
    def test_guard_credits_only_full_remaining_request_completion(self):
        for minimum,accepted in [(1,True),(2,False)]:
            p,rt,now=self.guard_fixture();p.cur=[.9,.9]
            self.fake_search(p,rt,{'t0':1.},{'t1':.8});search=p.plan
            def metadata(*args):
                action=search(*args)
                for v in p.pending.values():v['pred_multiplier']=1.2 if not rt.obligations.active else p.mismatch
                return action
            p.plan=metadata;r=ObligationTests().request(p,minimum=minimum)
            if minimum==1:r['target_ids']=['t1']
            action=rt.plan(now,p.nights[0][1],0,0,[r])
            self.assertEqual(set(action['assignments'].values()),{'t1'} if accepted else {'t0'})
    def test_partial_progress_does_not_accept_equal_gain_longer_visit(self):
        p,rt,now=self.guard_fixture();p.rate_ema=.001
        self.fake_search(p,rt,{'t0':.8},{'t1':.8});search=p.plan
        def longer(*args):
            action=search(*args)
            if rt.obligations.active:action['duration_seconds']=900;p.pending_duration=900
            return action
        p.plan=longer;r=ObligationTests().request(p,minimum=2,deadline=1200);r['target_ids']=['t1']
        action=rt.plan(now,p.nights[0][1],0,0,[r])
        self.assertEqual(set(action['assignments'].values()),{'t0'})
    def test_request_objective_no_duplicates_expiry_or_partial_reward(self):
        p,rt,now=self.guard_fixture();p.pending={'t0':{'pred':.8,'p':.5}}
        action={'program':'DARK','duration_seconds':600};r=ObligationTests().request(p)
        f=rt.forecast(action,[r],now)
        self.assertAlmostEqual(rt.objective(f,action,[r,r],0.),f[0]+.5*r['completion_reward'])
        r['minimum_completed']=2;r['remaining_count']=2;r['target_ids']=['t0','t0']
        f=rt.forecast(action,[r],now);self.assertEqual(f[2][r['request_id']],1)
        self.assertEqual(rt.objective(f,action,[r],0.),f[0])
        r=ObligationTests().request(p);r['deadline_utc']=format_utc(now+timedelta(seconds=300))
        f=rt.forecast(action,[r],now);self.assertEqual(rt.objective(f,action,[r],0.),f[0])
        r=ObligationTests().request(p);r['remaining_count']=0
        f=rt.forecast(action,[r],now);self.assertEqual(rt.objective(f,action,[r],0.),f[0])
    def test_public_required_penalty_uses_physical_landing_chance(self):
        d=fixture();d['targets']['rows'][0][-1]=True;d['scoring']['required']['penalty_per_missing']=123
        p=Planner(d);rt=Runtime(p);now=p.nights[0][0]
        p.pending={'t0':{'pred':.8,'p':.5}}
        action={'program':'DARK','duration_seconds':600};f=rt.forecast(action,[],now)
        self.assertEqual(f[1],{0});self.assertAlmostEqual(rt.objective(f,action,[],0.),f[0]+61.5)
    def test_nominal_metadata_matches_planning_safe_factor(self):
        for cls in (Planner,CorePlanner):
            p=cls(fixture());now=p.nights[0][0];action=p.plan(now,p.nights[0][1],0,0)
            for v in p.pending.values():
                self.assertAlmostEqual(v['pred_score_factor'],min(1.,v['pred']*.97))
                self.assertIn(v['pred_multiplier'],{p.multipliers[action['program']],p.mismatch})
    def test_diagnostic_uses_agent_elapsed_hours(self):
        p=Planner(fixture());rt=Runtime(p);now=p.nights[0][0];seen=[]
        original=p.plan
        def search(a,b,n,h):seen.append(h);return original(a,b,n,h)
        p.plan=search;rt.diagnostic(now,p.nights[0][1],24.5)
        self.assertEqual(seen,[24.5])
    def test_no_action_diagnostic_does_not_duplicate_efficiency_samples(self):
        p=Planner(fixture());rt=Runtime(p);now=p.nights[0][0]
        p.e_hours=[[0.,0.,[.8]]]
        def empty(*args):p.e_hours[-1][2].append(.8);p.e_hours.append([1.,0.,[.8]]);return None
        p.plan=empty;action=rt.diagnostic(now,p.nights[0][1])
        self.assertEqual(p.e_hours,[[0.,0.,[.8]]]);self.assertEqual(action['action'],'observe')
    def test_diagnostic_reuses_science_field_and_preserves_time_price(self):
        for cls in (Planner,CorePlanner):
            p=cls(fixture());rt=Runtime(p);now=p.nights[0][0];p.rate_ema=.001
            p.pending_notices={('old','N')};p.notices={('overcast','S')}
            rt.obligations.active=True
            action=rt.diagnostic(now,p.nights[0][1])
            self.assertEqual(action['action'],'observe')
            self.assertEqual(action['reason'],'short science health diagnostic')
            self.assertGreater(len(action['assignments']),1)
            self.assertLessEqual(action['duration_seconds'],300)
            self.assertEqual(set(action['assignments'].values()),set(p.pending))
            self.assertEqual(p.rate_ema,.001);self.assertTrue(rt.obligations.active)
            self.assertEqual(p.pending_notices,p.notices)
    def test_failed_science_diagnostic_retains_single_target_fallback(self):
        p=Planner(fixture());rt=Runtime(p);now=p.nights[0][0];p.rate_ema=.2
        def failure(*args):p.rate_ema=99.;p.pending={};p.e_hours.append([0.,0.,[.8]]);raise ValueError('numeric search')
        p.plan=failure
        action=rt.diagnostic(now,p.nights[0][1])
        self.assertEqual(action['action'],'observe');self.assertEqual(len(action['assignments']),1)
        self.assertEqual(set(action['assignments'].values()),set(p.pending));self.assertEqual(p.rate_ema,.2)
        self.assertEqual(p.e_hours,[])
    def test_secondary_search_starts_from_same_time_price(self):
        p,rt,now=self.guard_fixture();p.rate_ema=10.
        seen=[]
        self.fake_search(p,rt,{'t0':.6},{'t0':.8,'t1':.8})
        search=p.plan
        def recording(*args):
            seen.append(p.rate_ema)
            action=search(*args);p.rate_ema=seen[-1]+1
            return action
        p.plan=recording
        rt.plan(now,p.nights[0][1],0,0,[])
        self.assertEqual(seen,[10.,10.]);self.assertEqual(p.rate_ema,11.)
    def test_successful_old_nlp_answer_is_discarded_after_correction(self):
        p=Planner(fixture());a=Advisor(MockClient())
        a.plan_applied=False;a.fault_applied=True;a.text_hashes={'note':'new'}
        a.plan_call=Ready({'bad_night':False,'events':[]})
        a.plan_call.batch=[{'source_id':'note','digest':'old','attempt':0}]
        a.pending_texts=deque([{'source_id':'note','digest':'new'}])
        with patch.object(a,'_valid_plan',side_effect=AssertionError('stale validation')):
            plan,fault=a.poll()
        self.assertIsNone(plan);self.assertIsNone(fault)
        self.assertEqual(len(a.pending_texts),1)
    def guard_fixture(self):
        p=Planner(fixture());rt=Runtime(p);rt.obligations.active=True;p.cpu_turn_budget=1.
        return p,rt,p.nights[0][0]
    def fake_search(self,p,rt,base,proposal):
        def search(*args):
            factors=proposal if rt.obligations.active else base
            if factors is None:
                p.pending={};raise ValueError('candidate failed')
            p.pending={t:{'pred':f,'model':1.,'band_model':1.} for t,f in factors.items()}
            p.pending_duration=600;p.pending_program='DARK';p.pending_night=0
            p.pending_notices=set();p.pending_cmd=(55.,100.);p.rate_ema=2. if rt.obligations.active else 1.
            return {'action':'observe','duration_seconds':600,'program':'DARK','pointing':{'alt_deg':55.,'az_deg':100.},
                    'assignments':{str(k):t for k,t in enumerate(factors)}}
        p.plan=search
    def test_pareto_guard_protects_existing_request_progress(self):
        p,rt,now=self.guard_fixture();self.fake_search(p,rt,{'t0':.8,'t1':.8},{'t0':.9})
        request=ObligationTests().request(p,minimum=2)
        action=rt.plan(now,p.nights[0][1],0,0,[request])
        self.assertEqual(set(action['assignments'].values()),{'t0','t1'})
        self.assertEqual(p.rate_ema,1.);self.assertEqual(rt.joint_accepted,0)
    def test_pareto_guard_accepts_actual_forecast_improvement(self):
        p,rt,now=self.guard_fixture();self.fake_search(p,rt,{'t0':.6},{'t0':.8,'t1':.8})
        action=rt.plan(now,p.nights[0][1],0,0,[])
        self.assertEqual(len(action['assignments']),2);self.assertEqual(rt.joint_accepted,1)
        self.assertEqual(p.factor,[0.,0.])
    def test_failed_secondary_search_restores_legal_incumbent(self):
        p,rt,now=self.guard_fixture();self.fake_search(p,rt,{'t0':.8},None)
        action=rt.plan(now,p.nights[0][1],0,0,[])
        self.assertEqual(len(action['assignments']),1);self.assertEqual(set(p.pending),{'t0'})
        self.assertEqual(p.rate_ema,1.);self.assertEqual(rt.joint_errors,1)
    def test_full_mock_http_to_queue_to_lamp_wait_and_one_report(self):
        from fusion_core.agent import ObserverAgent as CoreAgent
        from llm_client import LLMClient
        for cls in (ObserverAgent,CoreAgent):
            agent=cls(fixture(),rules_only=False);p=agent.planner
            lamp,ls=event(p,'lamp_test',240,180,'lamp');work,ws=event(p,seconds=600)
            raw=('普通交接。\n'*1000)+ls['note']+'\n'+ws['note']
            calls=[]
            def response(request,timeout):
                body=json.loads(request.data);user=json.loads(body['messages'][-1]['content'])
                system=body['messages'][0]['content']
                if 'Workflow operator_nlp' in system:
                    calls.append('operator_nlp')
                    texts=''.join(s['text'] for s in user['sources'] if s['source_id']=='note')
                    self.assertIn(ws['note'],texts)
                    answer={'bad_night':False,'events':[lamp,work],'sources':[]}
                else:
                    calls.append('anomaly_review');answer={'ledger_version':user['ledger_version'],
                        'fault_likely':0.,'diagnosis':'normal','recommendation':'retain'}
                return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}).encode())
            now=p.nights[0][0]
            request={'request_id':'note','target_ids':p.ids,'minimum_completed':1,'remaining_count':1,
                'completion_reward':0.,'completion_factor_threshold':.5,'issued_at_utc':format_utc(now),
                'deadline_utc':format_utc(now+timedelta(hours=2)),'reason':raw}
            def payload(moment,last=None):return {'now_utc':format_utc(moment),'active_requests':[request],
                'last_result':last,'new_messages':[],'latest_bulletin':{'notices':[]},
                'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':7200}}
            with patch('urllib.request.urlopen',side_effect=response):
                first=agent.respond(payload(now))
                if first['action']=='observe':self.assertLessEqual(first['duration_seconds'],240)
                hits=[{'target_id':t,'score':.1} for t in p.pending]
                last={'action':'observe','observe_index':0,'hits':hits} if hits else None
                wait=agent.respond(payload(now+timedelta(seconds=240),last))
                self.assertEqual(wait['action'],'wait');self.assertEqual(agent.reports,0)
                report=agent.respond(payload(now+timedelta(seconds=600)))
                self.assertEqual(report['action'],'report');self.assertEqual(agent.reports,1)
                again=agent.respond(payload(now+timedelta(seconds=600)))
                self.assertNotEqual(again['action'],'report');self.assertEqual(agent.reports,1)
            self.assertIn('operator_nlp',calls);self.assertIn('anomaly_review',calls)
            self.assertEqual(agent.advisor.coverage['chunks_submitted'],agent.advisor.coverage['chunks_accepted'])

if __name__=='__main__':unittest.main()
