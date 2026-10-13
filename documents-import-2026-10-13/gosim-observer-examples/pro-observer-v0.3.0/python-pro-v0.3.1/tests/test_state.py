import unittest
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner import Planner
from skymath import altaz_to_radec, local_sidereal_deg
NOW=datetime(2026,10,7,tzinfo=timezone.utc)
def fixture():
    ra,dec=altaz_to_radec(60,180,local_sidereal_deg(NOW,0),30)
    return {'site':{'latitude_deg':30,'longitude_deg':0,'minimum_altitude_deg':20},
      'survey':{'nights':[{'observing_start_utc':NOW.isoformat(),'observing_end_utc':(NOW+timedelta(hours=4)).isoformat()}],'end_utc':(NOW+timedelta(hours=4)).isoformat(),'slot_seconds':300},
      'instrument':{'grid_side':4,'n_fibers':16,'glass_side_deg':.632456,'pitch_deg':.632456,'fov_side_deg':2.529824,'exposure':{'min_duration_seconds':60,'max_duration_seconds':3600}},
      'scoring':{'flux_zero_point':1,'exposure_zero_point_seconds':1000,'q0':1,'airmass_exponent':1,'required':{'observed_factor_threshold':.5},'program':{'bands':{'DARK':.65,'BRIGHT':.4},'multipliers':{'DARK':1.2,'BRIGHT':1.12,'BACKUP':1.06},'mismatch_multiplier':1},'lunar_model':{'maximum_penalty':0,'altitude_exponent':1,'angular_decay_scale_deg':30}},
      'targets':{'columns':['target_id','ra_deg','dec_deg','feature_flux','science_weight','required'],'rows':[['T',ra,dec,1,10,True]]}}
class StateTests(unittest.TestCase):
    def setUp(self): self.p=Planner(fixture())
    def hit(self,index,score,program='DARK'):
        self.p.pending_program=program; self.p.pending_duration=300
        self.p.on_result({'action':'observe','observe_index':index,'hits':[{'target_id':'T','score':score}]},NOW+timedelta(seconds=300*(index+1)),index)
    def resync(self,first,last,score):
        rows=[] if score is None else [{'target_id':'T','best_score':score}]
        self.p._resync({'invalidated_window':{'action_index_start':first,'action_index_end_exclusive':last},'best_scores':rows})
    def test_ambiguous_default_mismatch(self):
        self.hit(0,5.5)
        self.assertEqual(self.p.required_status[0],'unknown')
        self.assertLess(self.p.factor_lower[0],.5); self.assertGreater(self.p.factor_upper[0],.5)
        self.resync(1,1,5.5)
        self.assertEqual(self.p.required_status[0],'unknown')
    def test_confirmed_and_nonaccumulating(self):
        self.hit(0,3); self.hit(1,3)
        self.assertEqual(self.p.required_status[0],'unsatisfied')
        self.assertAlmostEqual(self.p.factor_upper[0],.30000005)
        self.hit(2,6.1)
        self.assertTrue(self.p.required_satisfied(0))
    def test_rounding_at_threshold(self):
        self.hit(0,6)
        self.assertEqual(self.p.required_status[0],'unknown')
        self.hit(1,6.000001)
        self.assertTrue(self.p.required_satisfied(0))
    def test_best_score_and_best_factor_differ(self):
        self.hit(0,6.4,'DARK'); self.hit(1,6.2,'BACKUP')
        self.assertAlmostEqual(self.p.cur[0],.64)
        self.assertGreater(self.p.factor_lower[0],.58)
        self.assertTrue(self.p.required_satisfied(0))
    def test_last_outcome_invalidation_and_repeat(self):
        self.hit(0,3); self.hit(1,6.4)
        self.resync(1,2,3)
        self.assertFalse(self.p.hit_ledger[1]['valid'])
        self.assertEqual(self.p.required_status[0],'unsatisfied')
        self.assertAlmostEqual(self.p.cur[0],.3)
        self.resync(1,2,3)
        self.assertEqual(self.p.required_status[0],'unsatisfied')
    def test_surviving_last_outcome(self):
        self.hit(0,3); self.hit(1,6.4)
        self.resync(0,1,6.4)
        self.assertTrue(self.p.hit_ledger[1]['valid'])
        self.assertTrue(self.p.required_satisfied(0))
    def test_duplicate_no_extra_evidence(self):
        self.hit(0,3); self.hit(0,6.4)
        self.assertEqual(len(self.p.hit_ledger),1)
        self.assertAlmostEqual(self.p.cur[0],.3)
    def test_configurable_threshold(self):
        cfg=fixture(); cfg['scoring']['required']['observed_factor_threshold']=.7
        self.p=Planner(cfg); self.hit(0,6.4)
        self.assertEqual(self.p.required_status[0],'unsatisfied')
    def test_zero_mismatch_cannot_prove_zero_factor(self):
        self.p.mismatch=0
        self.hit(0,0)
        self.assertEqual(self.p.factor_upper[0],1)
        self.assertEqual(self.p.required_status[0],'unknown')
    def test_zero_declared_positive_mismatch_learning(self):
        self.p.multipliers['DARK']=0
        self.p.pending_program='DARK'; self.p.pending_duration=300
        self.p.pending={'T':{'model':1,'band_model':1,'dir_clean':True,'clean':True,'alt':60,'az':180,'pred':.3}}
        self.p.on_result({'action':'observe','observe_index':0,'hits':[{'target_id':'T','score':3}]},NOW+timedelta(seconds=300),0)
        self.assertAlmostEqual(self.p.factor[0],.3)
    def test_zero_required_threshold_initial_confirmation(self):
        cfg=fixture(); cfg['scoring']['required']['observed_factor_threshold']=0
        self.p=Planner(cfg)
        self.assertTrue(self.p.required_satisfied(0))
    def test_legacy_resync(self):
        self.p.state_evidence=False
        self.resync(0,0,5.5)
        self.assertAlmostEqual(self.p.factor[0],5.5/12)
    def test_learning_caches_invalidated(self):
        self.p.samples.append((0,2)); self.p.band_obs.append((0,1,'DARK',True,True))
        self.p.offset=(1,1); self.p.blocked=[(1,1)]
        self.resync(0,1,None)
        self.assertEqual(list(self.p.samples),[]); self.assertEqual(list(self.p.band_obs),[])
        self.assertEqual(self.p.offset,(0,0)); self.assertEqual(self.p.blocked,[])
if __name__=='__main__': unittest.main()
