"""Best-single-observation replacement costs and bounded existing season auction."""
import unittest
from unittest.mock import patch
from support import NOW, END, LST
import season


def prices(cls=season.OptionPrices):
    args = ([LST], [30.0], [1.0], [(NOW, END)], 0, 30, 20, 16, .6, [1000.0], 1)
    return cls(*args, [12.0]) if cls is season.OptionPrices else cls(*args)


class SeasonReplacementTests(unittest.TestCase):
    def test_option_partial_progress_does_not_reduce_replacement_cost(self):
        with patch.object(season, 'REPLACEMENT', True):
            a, b = prices(), prices()
            a.update([0.0], 0); b.update([0.8], 0)
        self.assertAlmostEqual(a.ratio, b.ratio)
        self.assertGreater(a.ratio, 0)

    def test_marginal_value_reduces_price_without_discounting_cost(self):
        with patch.object(season, 'REPLACEMENT', True):
            a, b = prices(), prices()
            a.update([0.0], 0, best_scores=[0.0])
            b.update([0.8], 0, best_scores=[9.6])
        self.assertAlmostEqual(a.ratio, b.ratio)
        for old, partial in zip(a.price, b.price):
            self.assertAlmostEqual(partial, .2 * old)

    def test_full_factor_with_mismatched_score_still_has_marginal_value(self):
        p = prices()
        p.update([1.0], 0, best_scores=[5.0])
        self.assertEqual(p.units, 1)
        p.update([1.0], 0, force=True, best_scores=[12.0])
        self.assertEqual(p.units, 0)
        self.assertEqual(p.ratio, 0)

    def test_market_cost_also_uses_full_replacement(self):
        with patch.object(season, 'REPLACEMENT', True):
            a, b = prices(season.SeasonPrices), prices(season.SeasonPrices)
            a.update([0.0], 0); b.update([0.8], 0)
        self.assertEqual(a.demand, b.demand)

    def test_expired_budget_preserves_prior_prices_and_requests_retry(self):
        p = prices()
        p.update([0.0], 0)
        before = p.price[:]
        self.assertFalse(p.update([.8], 1, force=True, deadline=lambda: True))
        self.assertEqual(p.price, before)
        self.assertEqual(p.night, 0)

    def test_mid_auction_interrupt_retains_finite_positive_price(self):
        import math
        calls = 0
        def exhausted():
            nonlocal calls
            calls += 1
            return calls >= 3
        p = prices()
        self.assertFalse(p.update([.8], 0, deadline=exhausted))
        self.assertTrue(all(math.isfinite(x) and x > 0 for x in p.price))
        self.assertTrue(p.update([.8], 0, force=True))

    def test_disabled_flag_reproduces_old_demand_for_ablation(self):
        with patch.object(season, 'REPLACEMENT', False):
            a, b = prices(), prices()
            a.update([0.0], 0); b.update([.8], 0)
        self.assertAlmostEqual(b.ratio / a.ratio, .2)

    def test_same_night_correction_invalidates_season_prices(self):
        from support import fixture
        from planner import Planner
        p = Planner(fixture())
        p.long_dirty = False
        p.season_slot = (0, 1)
        p.season_refresh_slot = (0, 1)
        p._resync({'best_scores': [{'target_id': 'T0', 'best_score': 0.0}]})
        self.assertTrue(p.long_dirty)
        self.assertTrue(p.season_progress_dirty)
        self.assertIsNone(p.season_slot)
        self.assertIsNone(p.season_refresh_slot)


if __name__ == '__main__':
    unittest.main()
