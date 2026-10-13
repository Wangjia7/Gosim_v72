"""Select from public compatibility facts, never card names or hidden truth."""
import math


def initial_route(init):
    instrument = init['instrument']
    score = init['scoring']
    reasons = []
    # Official pro uses these constants in completion gates and required bonuses.
    threshold = float(score['required']['observed_factor_threshold'])
    penalty = float(score['required']['penalty_per_missing'])
    if not math.isclose(threshold, .5, rel_tol=0, abs_tol=1e-9):
        reasons.append('required threshold differs from pro completion gates')
    if not math.isclose(penalty, 50., rel_tol=0, abs_tol=1e-9):
        reasons.append('required penalty differs from pro planning constant')
    # Pro's small fixed neighbour radius and central-fibre sets lose coverage as
    # the grid grows. Numerical enhanced search uses the runtime grid dimensions.
    if int(instrument['n_fibers']) > 16:
        reasons.append('large fibre grid needs expanded geometry search')
    return ('enhanced' if reasons else 'official_pro', reasons)
