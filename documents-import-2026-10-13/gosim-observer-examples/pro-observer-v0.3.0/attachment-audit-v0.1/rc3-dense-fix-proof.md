# RC3 density-bin KeyError — reproduced and fixed in isolation

2026-10-07, native Python3.12. Source under `work/v0.3-dense-fix`, copied from current frozen V3. No frozen observer runtime changed.

Public synthetic fixture: one visible nonrequired target, flux100, exposure60seconds; existing best score/weight1.2 and factor1; new timed request reward40. Deep search enabled, width10. Before patch:

```
File "outputs/python-pro-v0.3.0/planner.py", line 1836, in plan
    j = bin_best[key][1]
KeyError: (6, 35)
```

The target's active request keeps planning value positive, while its remaining-science density is0. The old code creates `bins[key]=0` but does not set `bin_best[key]` because its representative test requires density>0. Selection later accesses the missing representative.

Minimal fix wraps both density dictionaries' updates in `if dense_val>0`. Positive-density bin construction is unchanged. Request/required anchor streams are unchanged. New regression asserts the saturated target still gets a legal observe assignment, predicted science gain0, and conditional request reward40, with width10; thus the fix does not silently discard the timed action.

Native3.12 complete suite:94 tests PASS in0.412seconds, recorded in `rc3-dense-fix-tests.txt`. No benchmark rerun or improvement claim.

The density proxy still divides current score/weight by hard-coded1.2. That predates this isolated correction; behavior under custom multiplier configurations remains a separate unverified proxy-quality concern, not expanded into this crash fix.
