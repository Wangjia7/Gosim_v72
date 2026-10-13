# Physical interpretation and executable rules

The challenge represents n² independently assignable square cells in an Alt-Az
gnomonic plane. Read n, area, pitch, gap and field size from initialize. This cell
area is not a real optical fibre aperture or patrol radius. One target per cell;
one cell per target. Geometry is evaluated at exposure start under sidereal
tracking; target altitude must stay legal throughout the exposure.

Quality and sky program band are distinct. Lunar separation, air mass and weather
affect the public quality model; instrument efficiency affects throughput but
does not set the sky program band. Use the official integration formula and
runtime constants. ELG, BGS, LRG, QSO and Star have no extra class multiplier in
this challenge: their public flux, weight and geometry determine the differences.
Real DESI point/extended-source fibre losses are physical context, not a license
to add an undocumented score term.

Scientific gain is max(previous best score, new score) minus previous best score.
Required completion uses the maximum valid raw factor. These maxima can arise
from different exposures. Multiple short exposures do not add raw factors. A
request exposure must start after issuance and finish before its deadline; apply
each overlapping request's own threshold. A request rewards the full minimum
group once. Zero-future-opportunity targets may be impossible under weather or
capacity constraints; do not promise universal completion.

Allocate measured process CPU time using remaining_real_cpu_seconds. API waiting
uses wall_remaining_seconds; do not subtract waiting seconds from CPU seconds.
Generate a legal incumbent before extending search. Shared-library C++ work is
included in process CPU. Replan after every public result or state correction.

Borrow DESI's plan → assign → expose → quick quality review → target-ledger update
loop. The attached historical QuickLook requirement describes observer warnings
and expert alarms; it does not grant access to CCD spectra, FVC positions or
unpublished weather in this simulator.

References: https://fiberassign.readthedocs.io/en/latest/overview.html ;
https://arxiv.org/abs/2306.06309 ; https://arxiv.org/abs/2403.05688 .
