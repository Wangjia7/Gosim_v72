# Acceptance feasibility audit — public L1/L2 only

Retrieved/inspected 2026-10-07. No truth files, L3/L4, requests catalog, fault schedule, weather realization, judge execution, or external packages used. This is a lightweight analytic resource relaxation, not an achievable schedule or a performance prediction.

## Conclusion

The public inputs **do not rule out the 30% acceptance threshold** (L1 total 8,107.54; L2 total 8,122.8469). They also do not establish that it is attainable. The unconditional science ceilings are 8,517.6 and 9,391.2 respectively, already above those total-score thresholds. Unknown future report/request rewards prevent turning the science ceiling into an unconditional total ceiling from this input subset. Conversely, required/uniformity penalties can lower total score.

At an illustrative constant exposure quality of 0.5, an optimistic fiber-time allocation allows science 8,000.885 on L1 and 8,786.086 on L2. L1's science-only gap to the requested total threshold is then 106.655; this is not an impossibility result because actual quality is not proven bounded by 0.5, and positive score components are omitted. At quality 1.0 the relaxation saturates every catalog target with substantial unused fiber-time. Thus the raw number of fibers and total nighttime alone cannot explain or certify the remaining acceptance gap.

## Verified formula and quality-bound limitation

`runner/challenge/v4_scorer.py:350–402` integrates quality as

`Q = mean(efficiency * transparency * sky_quality * lunar / seeing / airmass^beta) / q0`

and sets `factor=min(flux*T*Q/(flux_zero_point*exposure_zero_point_seconds),1)` and `science=weight*factor*program_multiplier`. Here `q0=0.68`, the normalization product is 450, beta is 0.6, and the largest declared multiplier is 1.2. Lunar quality is clamped to [0,1] at lines80–94. Replacement/best-score semantics cap each target's science by `1.2*weight` regardless of repeats.

**A finite universal Q upper bound cannot be established from the allowed public catalog/site/calendar/scoring inputs.** Seeing occurs in the denominator; the inspected weather loader (weather_simulator.py:225–234) checks presence, not a positive numeric lower bound. Directional multipliers also enter the numerator/denominator. Therefore treating `1/q0` as a verified quality ceiling would be incorrect. It is only the idealized value when efficiency/transparency/sky/seeing/airmass/lunar all equal 1. No hidden weather extrema were inspected. The unconditional factor cap of 1 remains sufficient for the catalog science ceiling.

## Fractional fiber-time relaxation

For an assumed constant quality Q, let saturation cost `c_i=450/(flux_i*Q)` fiber-seconds, value `v_i=1.2*weight_i`, and fraction `x_i in [0,1]`. Maximize `sum(v_i*x_i)` subject to `sum(c_i*x_i)<=16*sum(public night_seconds)`. Sorting by `v_i/c_i` solves this fractional knapsack. Science is linear in duration until saturation, so this is a genuine upper bound **conditional on proving Q is a per-exposure upper bound**. We have not proved that assumption for any tabulated Q.

The relaxation ignores pointing geometry, attainable altitudes, Moon, simultaneous assignment constraints, visibility distribution, weather closures, faults, repeat losses, minimum/maximum exposure duration, and indivisible actions. It also lets every target select the 1.2 multiplier. All of those choices deliberately favor an optimistic result. CPU budget constrains finding a schedule rather than physical fiber-time; the table makes no assertion that a schedule can be found under 900 normalized CPU seconds.

| Card | Assumed Q | Available fiber-seconds | Cost to saturate all targets | Relaxed science |
|---|---:|---:|---:|---:|
| L1 | 0.500000 | 14,068,800 | 16,702,613 | 8,000.885 |
| L1 | 1.000000 | 14,068,800 | 8,351,306 | 8,517.600 |
| L1 | 1.470588 | 14,068,800 | 5,678,888 | 8,517.600 |
| L2 | 0.500000 | 15,494,400 | 18,383,618 | 8,786.086 |
| L2 | 1.000000 | 15,494,400 | 9,191,809 | 9,391.200 |
| L2 | 1.470588 | 15,494,400 | 6,250,430 | 9,391.200 |

## Implication for experiments

The evidence supports prioritizing actual assignment occupancy, geometry-aware center refinement, marginal replacement gain, and avoiding poor-quality repeated exposures over an argument that total observing time makes acceptance impossible. Which lever produces a measured gain remains a hypothesis. The table cannot distinguish geometry losses from quality losses in a realized run, and should not be used to promise a 30% improvement.

## Provenance

Paths below are relative to `/Users/jqwang/Documents/gosim-observer-examples/`; only the named public/config files were opened.

- `L1/public/targets.csv`: `e6a451caaf075402a1e130b3411b3c1b70c8cc64484a5496e99a92b24cd30348`
- `L1/public/v4_night_calendar.csv`: `9aa147ecf804e3473d73a32cce6ab4065e282ec0a974dbaf5e3c9f10a93a0a0e`
- `L1/config/v4_score_config.json`: `8b2dd879a684e8dc51e2a3f33dfe6301c277b7f0ee95415c6649498d3a8784cd`
- `L1/config/v4_fiber_config.json`: `85fc175cb198b1c65d33a123cfbc8b6c1deb10778eef0dbfa659156918e23c8f`
- `L2/public/targets.csv`: `a85d6f8571be0e1f06c11a34943f786e21feccb32b240f8a17c5d68744ed39db`
- `L2/public/v4_night_calendar.csv`: `e6149422d04de96c469aaaa18b9116c7c11ce1b976c0a42ad983208fcdd89484`
- `L2/config/v4_score_config.json`: `8b2dd879a684e8dc51e2a3f33dfe6301c277b7f0ee95415c6649498d3a8784cd`
- `L2/config/v4_fiber_config.json`: `85fc175cb198b1c65d33a123cfbc8b6c1deb10778eef0dbfa659156918e23c8f`
- `runner/challenge/v4_scorer.py`: `46154188eb409fb8408845d0a40ea07c143e1bb1f297f7ee79ab1559ac24cd66`
- `runner/challenge/weather_simulator.py`: `41c82b106c88ea6eee0348b48801cdad2043379cadf34d8547c7bf45705af098`

Computation used standard-library CSV/JSON and fractional sorting; process CPU 0.0724 seconds.
