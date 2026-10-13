import copy
import json
from pathlib import Path
import unittest
from test_normal import fixture
from fusion_core.guarded import Planner
from planner import Planner as EnhancedPlanner
from inspection import Inspection

class InspectionTests(unittest.TestCase):
    def prepare(self,p):
        p.pending={t:{'fiber':k,'pred':.8,'model':1.,'band_model':1.,'dir_clean':True,'alt':55.,'az':100.}
            for k,t in enumerate(p.ids)}
        p.pending_program='DARK';p.pending_duration=900;p.pending_night=0;p.pending_notices=set();p.pending_cmd=(55.,100.)
    def add(self,p,q,index,score):
        self.prepare(p)
        result={'action':'observe','observe_index':index,'hits':[{'target_id':'t0','score':score}]}
        accepted=q.gate(result);self.assertIsNotNone(accepted)
        q.record(accepted,p.nights[0][0],[])
        p.on_result(accepted,p.nights[0][0],index)
        return json.loads(q.facts[index])
    def test_planned_required_is_not_completed_and_repeats_do_not_stack(self):
        for cls in (Planner,EnhancedPlanner):
            d=fixture();d['targets']['rows'][0][-1]=True;p=cls(d);q=Inspection(p)
            a=self.add(p,q,0,.4);b=self.add(p,q,1,.4)
            self.assertGreater(a['realized_science_gain'],0);self.assertEqual(b['realized_science_gain'],0)
            self.assertFalse(b['measurements'][0]['required_certified'])
            self.assertLess(getattr(p,'factor_lower',p.factor)[0],p.required_threshold)
            self.assertEqual(q.best['t0'],.4)
    def test_retracted_high_score_keeps_facts_and_restores_lower_best(self):
        p=Planner(fixture());q=Inspection(p);self.add(p,q,0,.4);self.add(p,q,1,1.8)
        original=q.facts.copy()
        msg={'record_type':'state_resync','invalidated_window':{'action_index_start':1,'action_index_end_exclusive':2},
             'best_scores':[{'target_id':'t0','best_score':.4}]}
        q.resync([msg]);q.resync([msg]);p._resync(msg)
        self.assertEqual(q.facts,original);self.assertEqual(q.best,{'t0':.4});self.assertEqual(q.invalid,{1})
        self.assertEqual(q.summary()['recent_visits'][0]['id'],0)
        c=self.add(p,q,2,.5)  # comparison uses planner's authoritative state after real resync
        self.assertEqual(q.best['t0'],.5);self.assertAlmostEqual(c['realized_science_gain'],.1)
    def test_resync_recomputes_surviving_marginal_credit_without_rewriting_facts(self):
        p=Planner(fixture());q=Inspection(p);self.add(p,q,0,1.8);self.add(p,q,1,1.2)
        original=q.facts[1];self.assertEqual(q.credits[1],0.)
        q.resync([{'record_type':'state_resync','invalidated_window':{'action_index_start':0,'action_index_end_exclusive':1},
            'best_scores':[{'target_id':'t0','best_score':1.2}]}])
        self.assertEqual(q.facts[1],original);self.assertEqual(q.credits[1],1.2)
        row=q.summary()['recent_visits'][0]
        self.assertEqual(row['realized_science_gain'],0.)
        self.assertEqual(row['credited_science_gain'],1.2)

    def test_duplicate_does_not_consume_next_pending_plan(self):
        p=EnhancedPlanner(fixture());q=Inspection(p);self.add(p,q,3,.4);self.prepare(p)
        pending=copy.deepcopy(p.pending)
        self.assertIsNone(q.gate({'action':'observe','observe_index':3,'hits':[{'target_id':'t0','score':1.9}]}))
        self.assertEqual(p.pending,pending);self.assertEqual(q.best['t0'],.4)
    def test_missing_malformed_and_foreign_hits_do_not_credit(self):
        p=Planner(fixture());q=Inspection(p);self.prepare(p)
        for result in ({'action':'observe','observe_index':1},
          {'action':'observe','observe_index':1,'hits':[{'target_id':'t0','score':float('nan')}]},
          {'action':'observe','observe_index':1,'hits':[{'target_id':'other','score':1}]},
          {'action':'observe','observe_index':1,'hits':[{'target_id':'t0','score':999}]},
          {'action':'observe','observe_index':1,'hits':[{'target_id':'t0','score':1}]*2}):
            self.assertIsNone(q.gate(result))
        self.assertFalse(q.best);self.assertEqual(p.cur,[0.,0.])
    def test_fixed_visits_have_expected_noncausal_judgements(self):
        cases=json.loads((Path(__file__).parent/'scenario_validation.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                d=fixture();d['targets']['rows'][0][-1]=True;p=Planner(d);q=Inspection(p);self.prepare(p)
                p.cur[0]=case.get('before',0)/p.weight[0]
                result={'action':'observe','observe_index':0,'hits':case['hits']}
                q.record(q.gate(result),p.nights[0][0],case.get('weather',[]))
                row=json.loads(q.facts[0]);first=row['measurements'][0]
                self.assertEqual(first['judgement'],case['judgement'])
                for reason in case.get('reasons',[]):self.assertIn(reason,first['reason_codes'])
                if 'required_certified' in case:self.assertEqual(first['required_certified'],case['required_certified'])
                self.assertEqual(row['realized']['actual_fiber_positions'],None)
                json.dumps(q.summary(),allow_nan=False)
    def test_zero_prediction_denominator_is_unknown(self):
        p=Planner(fixture());q=Inspection(p);self.prepare(p)
        for v in p.pending.values():v['pred']=0
        result={'action':'observe','observe_index':0,'hits':[]};q.record(q.gate(result),p.nights[0][0],[])
        self.assertIsNone(q.summary()['recent_visits'][0]['science_gain_efficiency'])
