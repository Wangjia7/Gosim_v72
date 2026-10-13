"""Planner of the pro agent: pointing, fibre assignment, duration and program in one search.

Per decision (plan):
1. Visible targets with something left to gain are ranked with a cheap proxy; the best POOL go on.
2. The gain of one exposure of duration T for target i is
       weight * (reach(T) * program multiplier - best so far)
     + REQUIRED_BONUS * P(required target reaches factor 0.5)   (discounted while its sky is far from its best)
     + request bonus  * P(request target reaches its threshold)
   times an urgency factor for targets with few nights left.
3. Candidate fields: the N_ANCHORS best targets centred on each of the 16 fibres, plus the N_DENSE densest
   patches of remaining science. Every fibre gets the target with the largest gain there, for each
   duration; the winner maximises  total gain - lambda * T  (lambda = time price, scaled by the card's
   time scarcity), and is then refined by small pointing shifts.
4. Program: the one with the largest expected score, using a band level fitted to saturated hits.
5. The command is the chosen centre minus the learned pointing offset (Hard-mode cards).

Learning from results: unsaturated hits give the quality level (scale); saturated hits show the program
multiplier exactly and so bracket the band level; E = quality level / band level is the instrument-fault
signal (clean_e); hit/miss patterns reveal the pointing offset. The planner only uses the public catalogue,
the public score formula, bulletins and its own results. Standard library only.
"""
from __future__ import annotations

import bisect
import heapq
import json
import math
import os
import time
from switches import WALL
from collections import deque
from datetime import datetime, timedelta

import bandfit
import season
from dutylog import DutyLog
from longplan import WeatherModel, quality_interval
from pointing import PointingModel
from skymath import (
    SIDEREAL_DEG_PER_SECOND,
    FiberGrid,
    altaz_to_radec,
    Moon,
    local_sidereal_deg,
    max_hour_angle_deg,
    normalized_airmass,
    parse_utc,
    radec_to_altaz,
    shift_altaz,
    tangent_offsets,
    wrap180,
)


def _env(name: str, default):
    return type(default)(os.environ.get(f"V5_{name}", os.environ.get(f"PRO_{name}", default)))


# --- search -------------------------------------------------------------------------------------------
LAMBDA_FRAC = _env("LAMBDA_FRAC", 0.45)       # price of telescope time, as a share of the recent best gain rate
LAMBDA_EMA = _env("LAMBDA_EMA", 0.03)
SCARCITY_REF = _env("SCARCITY_REF", 0.86)     # tuning constant: scarcity at which time is priced fully
SCARCITY_POWER = _env("SCARCITY_POWER", 1.0)  # time price x min(1, scarcity / SCARCITY_REF) ** power
TYPICAL_Q = 0.6
N_ANCHORS = _env("N_ANCHORS", 12)             # targets tried as field centres per decision (full speed)
N_DENSE = _env("N_DENSE", 20)                  # plus centres in the densest patches of remaining science
DENSE_BIN_DEG = _env("DENSE_BIN_DEG", 2.5)
REFINE = _env("REFINE", 0.1)                 # local pointing search step (deg); 0 = off
REFINE_ROUNDS = _env("REFINE_ROUNDS", 4)
REFINE_FIXED_T = _env("REFINE_FIXED_T", 1)
REFINE_STEPS = tuple((dn * REFINE, de * REFINE) for dn in (-1, 0, 1) for de in (-1, 0, 1) if dn or de) if REFINE > 0 else ()
POOL = _env("POOL", 600)                      # candidates kept after the cheap proxy ranking
DEEP_ANCHORS = _env("DEEP_ANCHORS", 24)        # deep search (when the CPU budget allows it): more anchors ...
DEEP_DENSE = _env("DEEP_DENSE", 40)            # ... more density anchors ...
DEEP_POOL = _env("DEEP_POOL", 1000)            # ... and a larger candidate pool
MAX_ANCHOR_FIBERS = _env("MAX_ANCHOR_FIBERS", 25)   # fibre placements tried per anchor on large grids
EDGE_MARGIN_DEG = _env("EDGE_MARGIN_DEG", 0.04)   # keep targets this far inside their fibre cell
DURATIONS = tuple(int(t) for t in os.environ.get("V5_DURATIONS", "300,450,600,750,900,1200,1500,1800,2400,3000,3600").split(","))
LEVEL_DURATIONS = (DURATIONS, (300, 600, 900, 1200, 1800, 2400, 3600), (450, 900, 1800, 3600), (900, 1800))
MIN_T = _env("MIN_T", 0)                      # shortest exposure considered (unless the night is ending)
MIN_VISIBLE_SECONDS = 600
# Local successor ablations; existing V5 tunables keep their precedence.
GEOMETRY = int(os.environ.get('PRO_GEOMETRY', '1'))
TEMPORAL = int(os.environ.get('PRO_TEMPORAL', '1'))
PROGRAM_AWARE = int(os.environ.get('PRO_PROGRAM_AWARE', '1'))
EVENT_DURATIONS = int(os.environ.get('PRO_EVENT_DURATIONS', '1'))
GAIN_CACHE = int(os.environ.get('PRO_GAIN_CACHE', '1'))
EXACT_TOPK = int(os.environ.get('PRO_EXACT_TOPK', '6'))
EVENT_MAX = int(os.environ.get('PRO_EVENT_MAX', '24'))
EVENT_LIMIT = int(os.environ.get('PRO_EVENT_LIMIT', '24'))
SPECIAL_ANCHORS = int(os.environ.get('PRO_SPECIAL_ANCHORS', '3'))
SCIENCE_ANCHORS = int(os.environ.get('PRO_SCIENCE_ANCHORS', '32'))
SCIENCE_TIME_PRICE = int(os.environ.get('PRO_SCIENCE_TIME_PRICE', '0'))
SEASON_REFRESH = int(os.environ.get('PRO_SEASON_REFRESH', '1'))
ALT_MARGIN_DEG = 0.6                          # keep targets this far above the altitude limit
# --- value --------------------------------------------------------------------------------------------
PLAN_FACTOR_SAFETY = _env("PLAN_FACTOR_SAFETY", 0.97)   # plan as if the sky were 3% worse than estimated
REQUIRED_BONUS = _env("REQUIRED_BONUS", 80.0)  # planning value of rescuing one required target (penalty 50)
REQ_P_LO = _env("REQ_P_LO", 0.95)             # P(success) ramps from 0 at this share of the needed reach ...
REQ_P_HI = _env("REQ_P_HI", 1.35)             # ... to 1 at this share
REQUEST_MULT = _env("REQUEST_MULT", 10.0)
REQ_FEASIBLE = _env("REQ_FEASIBLE", 1)         # drop a request whose open targets cannot rise in time to meet its minimum
WAIT_TO_RISE = _env("WAIT_TO_RISE", 1)         # nothing up: wait until the first valuable target rises, not a full slot
REQ_CALIB_POWER = _env("REQ_CALIB_POWER", 0.0)  # per-target calibration after failed tries (0 = off; did not help)
FORECAST_DISCOUNT = _env("FORECAST_DISCOUNT", 0.2)
REQ_CALENDAR = _env("REQ_CALENDAR", 0)        # compare with the best future night (public ephemeris), not an ideal sky
REQ_TIMING = _env("REQ_TIMING", 0.85)         # attempt a required target when its sky model is >= this share of its best ...
REQ_TIMING_NIGHTS = _env("REQ_TIMING_NIGHTS", 5)   # ... unless fewer nights than this are left for it
REQ_TIMING_DISCOUNT = _env("REQ_TIMING_DISCOUNT", 0.3)      # required bonus x this while a better moment will come
URGENCY = _env("URGENCY", 1.5)               # gain x (1 + URGENCY / nights left for the target)
PARTIAL_DISCOUNT = _env("PARTIAL_DISCOUNT", 1.0)   # <1: discount partial exposures of targets the season plan will complete (off: helped on 4 cards, hurt on 8 others)
PARTIAL_DONE = _env("PARTIAL_DONE", 0.9)      # reach below this counts as partial
PARTIAL_NIGHTS = _env("PARTIAL_NIGHTS", 3)    # no discount when fewer nights than this are left for the target
PLAN_UTIL = _env("PLAN_UTIL", 0.55)           # share of fibre-time that ends up useful (for the season plan)
PLAN_Q = _env("PLAN_Q", 0.7)                  # typical quality for the season plan
KAPPA = _env("KAPPA", 1.0)                    # convex shaping of science value (1 = linear)
TIMING_BETA = _env("TIMING_BETA", 0.0)        # science gain x (sky model / the target's best) ** this: wait for transit
TIMING_NIGHTS = _env("TIMING_NIGHTS", 10.0)   # ... fading out over the target's last nights
REACH_BETA = _env("REACH_BETA", 0.0)          # science gain x (reach now / reach at the target's best moment, same T) ** this:
                                              # a target that saturates anyway loses nothing now; a faint one waits for a good sky
WX_BETA = _env("WX_BETA", 0.0)                # science gain x (reach now / reach under a typical night's sky, same T) ** this:
WX_Q = _env("WX_Q", 0.5)                      # "typical night" = this quantile of the past nights' median quality ratios
WX_NIGHTS = int(_env("WX_NIGHTS", 30))        # ... over the last this many observed nights
WX_MIN_NIGHTS = 5
SEASON_GAMMA = _env("SEASON_GAMMA", 1.0)          # gain x (season price of the target's sky region) ** this (season.py; 0 = off)
SEASON_MODE = os.environ.get("V5_SEASON_MODE", "option")   # "option": now vs best later block; "market": demand balance
MONITOR_T = _env("MONITOR_T", 300)            # nothing has value: a short exposure of whatever is up, for the fault
MONITOR_ANCHORS = 40                          # detector only (a fault lasts until reported); anchors tried per field
REQUIRED_SAFE_FACTOR = 0.62                   # a required target counts as safe at this estimated factor
DONE_FACTOR = 0.95                            # other targets are done at this factor
# --- pointing offset (Hard-mode cards: a fixed, unannounced offset; its size is not published) ---
OFFSET_STEPS = 16                             # coarse grid half-width in steps of pitch/12 (about a third of the field);
                                              # the grid widens by half whenever the best offset sits on its edge
OFFSET_MIN_MISSES = 6                         # start estimating after this many assigned-but-missed targets
OFFSET_REFINE_EVERY = 10                      # observes between fine searches
OFFSET_FINE_EVIDENCE = 150                    # observes used by the fine search
OFFSET_MARGIN = 8                             # adopt an offset only if it explains this many more outcomes
# offset box: every hit (and some misses) bounds the true pointing offset; plan to the box instead of a fixed edge
EDGE_BOX = _env("EDGE_BOX", 1)                # 1 = on (0 = the fixed EDGE_MARGIN_DEG rule)
EDGE_ASSUME = _env("EDGE_ASSUME", 0.02)       # starting half-width of the box around the learned offset (deg)
EDGE_FLOOR = _env("EDGE_FLOOR", 0.002)        # always keep targets this far inside their glass (linearisation)
EDGE_P_MIN = _env("EDGE_P_MIN", 0.3)          # do not assign a target whose chance to land on its glass is lower
EDGE_TOL = 0.0005                             # slack added to every bound (deg)
EDGE_MAX = 0.15                               # widest box after contradictions (deg)
# --- learning -----------------------------------------------------------------------------------------
SKY_MEMORY_HOURS = 2.0                        # quality samples older than this are stale
BAND_OPT = _env("BAND_OPT", 1.0)              # declare programs as if the band were this much better (higher programs pay more)
BAND_HALF_LIFE = _env("BAND_HALF_LIFE", 0.0)  # hours; recent saturated hits count more when fitting the band (0 = equal)
BAND_MEMORY_HOURS = 2.0                       # saturated hits used to fit the band level
BAND_FALLBACK = _env("BAND_FALLBACK", 0)      # with few recent saturated hits, fit the last 8 within BAND_FALLBACK_HOURS
BAND_FALLBACK_HOURS = _env("BAND_FALLBACK_HOURS", 12.0)
BAND_CONT = _env("BAND_CONT", 0)              # tie-break the band fit towards the previous fitted level
BAND_CLASSIFY = _env("BAND_CLASSIFY", 1)      # judge match/mismatch of unsaturated hits from the fitted band level
CLOSED_KINDS = {"rain", "storm"}
SKY_WEATHER_KINDS = {"rain", "storm", "overcast", "haze", "cold_snap"}
WEATHER_GATE = _env("WEATHER_GATE", 0)        # no fault evidence from hours with announced all-sky weather
NEUTRAL_KINDS = {"earthquake"}                # announced; per the guide it lowers instrument efficiency, not the sky
BLOCKING_KINDS = {"terrain_obstruction", "rocket_launch"}
DIRECTION_AZ = {"N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0}
DUMP_HITS = os.environ.get("V5_DUMP_HITS", "")   # development only: per-exposure hit dump (see _dump_exposure)
LP_WEATHER = os.environ.get('V6_LP_WEATHER', '0') == '1'
LP_MOON = os.environ.get('V6_LP_MOON', '0') == '1'
LP_EVENTS = os.environ.get('V6_LP_EVENTS', '0') == '1'
POINT_MODEL = os.environ.get('V6_POINT_MODEL', '0') == '1'
DIAG = os.environ.get('V6_DIAG', '0') == '1'
DESI_HA = os.environ.get('V6_DESI_HA', '0') == '1'
GROUP_REQUESTS = os.environ.get('V6_GROUP_REQUESTS', '0') == '1'
REWARD_SPLIT = os.environ.get('V6_REWARD_SPLIT', '0') == '1' or DESI_HA or GROUP_REQUESTS
from rolling import RequestPlan, goal_gain, start_windows, design_weight, GROUP_BOOST


def _az_distance(a: float, b: float) -> float:
    return abs(wrap180(a - b))


DL_HORIZON = os.environ.get('V6_DL_HORIZON', '0') == '1'
DL_FLAT = os.environ.get('V6_DL_FLAT', '0') == '1'
DL_REQ = os.environ.get('V6_DL_REQ', '0') == '1'
DL_FAULT = os.environ.get('V6_DL_FAULT', '0') == '1'


class Planner:
    def __init__(self, init: dict, log=lambda text: None):
        self.log = log
        site = init["site"]
        self.lat = float(site["latitude_deg"])
        self.lon = float(site["longitude_deg"])
        self.min_alt = float(site["minimum_altitude_deg"])
        self.dutylog = DutyLog(site.get('utc_offset_hours', 0), self.min_alt, log) if (DL_HORIZON or DL_FLAT or DL_FAULT or int(os.environ.get('V6_FAULT_FIX', '0')) > 0 or os.environ.get('V6_FAULT_DEEP', '0') == '1') else None
        self.nights = [(parse_utc(n["observing_start_utc"]), parse_utc(n["observing_end_utc"])) for n in init["survey"]["nights"]]
        self.weather = WeatherModel(init['survey']['nights']) if LP_WEATHER else None
        self.long_dirty = False
        self.requests = []
        self.group_plan = RequestPlan(self) if GROUP_REQUESTS else None
        self.weather_sample = None
        self.diag_night = None
        self.diag = {'evaluated': 0, 'edge_rejected': 0, 'assigned': 0, 'hits': 0,
                     'cpu': 0.0, 'point_cpu': 0.0, 'season_cpu': 0.0, 'reprices': 0}
        self.survey_end = parse_utc(init["survey"]["end_utc"])
        self.slot_seconds = int(init["survey"]["slot_seconds"])
        instrument = init["instrument"]
        self.grid = FiberGrid(instrument)
        self.pointing = PointingModel(self.grid) if POINT_MODEL else None
        # fibre placements tried per anchor: the central fibres first, then an even spread over the grid
        by_centre = sorted(range(self.grid.n), key=lambda f: (sum(c * c for c in self.grid.fiber_center(f)), f))
        self.central4 = tuple(by_centre[:4])
        self.anchor_fibers = self._spread_fibers(MAX_ANCHOR_FIBERS)
        self.neighbour_radius = self.grid.fov / math.sqrt(2.0) + 0.35
        self.min_exposure = int(instrument["exposure"]["min_duration_seconds"])
        self.max_exposure = int(instrument["exposure"]["max_duration_seconds"])
        score = init["scoring"]
        self.f0t0 = float(score["flux_zero_point"]) * float(score["exposure_zero_point_seconds"])
        self.q0 = float(score["q0"])
        self.airmass_exponent = float(score["airmass_exponent"])
        self.bands = score["program"]["bands"]
        self.multipliers = score["program"]["multipliers"]
        self.mismatch = float(score["program"]["mismatch_multiplier"])
        bandfit.configure(self.bands, self.multipliers, self.mismatch)
        self.lunar_model = score["lunar_model"]

        columns = init["targets"]["columns"]
        col = {name: columns.index(name) for name in columns}
        rows = init["targets"]["rows"]
        self.ids = [row[col["target_id"]] for row in rows]
        self.index_of = {target_id: i for i, target_id in enumerate(self.ids)}
        self.ra = [float(row[col["ra_deg"]]) for row in rows]
        self.dec = [float(row[col["dec_deg"]]) for row in rows]
        self.flux = [float(row[col["feature_flux"]]) for row in rows]
        self.weight = [float(row[col["science_weight"]]) for row in rows]
        self.required = [bool(row[col["required"]]) for row in rows]
        self.sin_dec = [math.sin(math.radians(float(row[col["dec_deg"]]))) for row in rows]
        self.cos_dec = [math.cos(math.radians(float(row[col["dec_deg"]]))) for row in rows]
        self.sin_lat = math.sin(math.radians(self.lat))
        self.cos_lat = math.cos(math.radians(self.lat))
        self.hmax = [max_hour_angle_deg(d, self.lat, self.min_alt + ALT_MARGIN_DEG) for d in self.dec]
        self.state_evidence = bool(int(os.environ.get('PRO_STATE_EVIDENCE', '1')))
        self.required_threshold = float(score.get('required', {}).get('observed_factor_threshold', 0.5))
        self.required_penalty = float(score.get('required', {}).get('penalty_per_missing', 50))
        self.score_config_uniformity_threshold = float(score.get('uniformity', {}).get('observed_factor_threshold', 0.5))
        self.request_records = []
        self.requests_by_target = {}
        self.factor_lower = [0.0] * len(rows)
        self.factor_upper = [0.0] * len(rows)
        self.required_status = ['confirmed' if self.required_threshold <= 0 else 'unsatisfied'] * len(rows)
        self.hit_ledger = {}
        self.invalidated_observes = set()
        self.pending_start = None
        self.result_context = {}
        self.cpu_components = {}
        self.decision_record = {}
        self.season_progress_dirty = False
        self.season_refresh_slot = None
        self.factor = [0.0] * len(rows)          # best estimated exposure factor so far
        self.cur = [0.0] * len(rows)             # best realised score / weight so far
        self.rate_ema = 0.0                      # recent best gain rate (the time price follows it)
        self.e_hours: list = []                  # (hour, night, [E samples]): quality level / band level
        self.e_ratios: deque = deque(maxlen=400)   # (hours, quality ratio) of hits outside announced directional events
        self.misses = [0] * len(rows)            # assigned but not hit (e.g. too close to a fibre edge)
        self.vcache = None                       # value(i) per target; None = rebuild all
        self.vdirty: set = set()
        self.next_up = None                      # set by plan() when nothing is up: seconds until something rises
        self.wall_action_cost = 0.0
        self.last_plan_gain = 0.0
        self.attempts = [0] * len(rows)          # required hits that still ended below factor 0.5
        self.active = [i for i in range(len(rows)) if self.hmax[i] > 0.0]
        self.alt_a = [self.sin_lat * s for s in self.sin_dec]
        self.alt_b = [self.cos_lat * c * math.cos(math.radians(r)) for c, r in zip(self.cos_dec, self.ra)]
        self.alt_c = [self.cos_lat * c * math.sin(math.radians(r)) for c, r in zip(self.cos_dec, self.ra)]
        self.sin_alt_limit = math.sin(math.radians(self.min_alt + ALT_MARGIN_DEG))
        self._build_index()
        self._build_windows()
        # best sky model a target can ever get: at transit, Moon down (used to time faint required targets)
        self.ideal_model = [1.0 / (self.q0 * normalized_airmass(max(1.0, 90.0 - abs(d - self.lat))) ** self.airmass_exponent)
                            for d in self.dec]
        self._build_required_calendar()
        # Time scarcity: fibre-seconds the catalogue needs (typical sky) / night seconds on offer. A time-rich
        # season should price telescope time lower than a tight one.
        night_seconds = sum((end - start).total_seconds() for start, end in self.nights)
        need = sum(min(self.max_exposure, self.f0t0 / (max(f, 1e-3) * TYPICAL_Q)) for f in self.flux) / self.grid.n
        self.scarcity = need / max(1.0, night_seconds)
        self.lambda_frac = LAMBDA_FRAC * min(1.0, max(0.2, self.scarcity / SCARCITY_REF) ** SCARCITY_POWER)
        log(f"planner: scarcity {self.scarcity:.2f}, time price fraction {self.lambda_frac:.2f}")
        self.smult = [1.0] * len(rows)          # season price multiplier per target (1 = off)
        self.season_night = -1
        self.season_slot = None
        self.design_slot = None
        self.design_priority = None
        self.season = None
        if SEASON_GAMMA > 0.0:
            t_need = [min(self.max_exposure, self.f0t0 / (max(f, 1e-3) * PLAN_Q)) for f in self.flux]
            args = (self.ra, self.dec, self.flux, self.nights, self.lon, self.lat, self.min_alt,
                    self.grid.n, self.grid.glass, t_need, self.airmass_exponent)
            if SEASON_MODE == "option":
                extra = {'desi_design': True} if DESI_HA else {}
                if LP_WEATHER:
                    extra['night_factors'] = self.weather.predict(parse_utc(init['survey']['start_utc']))
                    extra['quality_ref'] = PLAN_Q
                if LP_MOON:
                    extra['lunar_model'] = self.lunar_model
                t0 = time.process_time()
                self.season = season.OptionPrices(*args, [max(self.multipliers.values()) * w for w in self.weight], **extra)
                self.diag['season_cpu'] += time.process_time() - t0
            else:
                self.season = season.SeasonPrices(*args)

        self.scale = 1.0                         # learned sky quality relative to the clear-sky model
        self.prior_scale = 1.0                   # long-run median, used when recent samples are missing
        self.samples: deque = deque(maxlen=24)   # (hours, ratio) of recent unsaturated hits
        self.all_ratios: deque = deque(maxlen=400)
        self.night_ratios: list = []             # quality ratios of the current night
        self.night_medians: deque = deque(maxlen=WX_NIGHTS)   # median ratio of each past night (weather is night-level)
        self.ratio_night = -1
        self.good_scale = 0.0                    # a typical night's quality ratio (WX_Q quantile), 0 = not known yet
        self.pending_night = -1
        self.pending_cmd = None
        self.bad_forecast = False                # set by the agent from tonight's forecast
        self.req_calib: dict = {}                # required target -> achieved / predicted on its last failed try
        self.offset = (0.0, 0.0)                 # learned pointing offset (deg): actual = command + offset
        self.offset_evidence: deque = deque(maxlen=400)   # (command, [(alt, az, fiber, hit)]) per observe
        self.offset_scores = None
        self.offset_step = self.grid.pitch / 12.0
        self.offset_steps = OFFSET_STEPS
        self.offset_grid = self._make_offset_grid()
        self.offset_misses = 0
        self.offset_updates = 0
        self.box_half = EDGE_ASSUME               # offset box (deg, absolute): [alt lo, alt hi, az lo, az hi]
        self.box = [-EDGE_ASSUME, EDGE_ASSUME, -2.0 * EDGE_ASSUME, 2.0 * EDGE_ASSUME]
        self.band_level = None
        self.band_obs: deque = deque(maxlen=300)    # (hours, model, program, matched, direction-clean) of saturated hits
        self.pending: dict[str, dict] = {}       # target_id -> prediction for the observe in flight
        self.pending_program = "BACKUP"
        self.pending_duration = 0
        self.pending_notices: set = set()
        self.exposure_r = None                   # fault signal of the last exposure (see on_result)
        self.exposure_bounds = None              # (eff lo, eff hi, kind) of the last exposure (bandfit.py)
        self.exposure_meta = None
        self.exposure_closed = False             # the last exposure scored zero everywhere (dome shut)
        self.blocked: list[tuple[float, float]] = []          # (az, alt) where a hit scored zero
        self.notices: set[tuple[str, str]] = set()
        self.terrain: set[str] = set()
        self.extra_avoid: set[str] = set()       # directions an advisor asked to avoid tonight
        self.duration_scale = 1.0
        self.fast_level = 0
        self.deep = False                        # level 0 with the wider DEEP_* search (set by the agent's pace)
        self.request_bonus: dict[int, float] = {}
        self.request_threshold: dict[int, float] = {}
        self.reach_cache: dict = {}
        # season plan: targets worth completing (value density w*flux above a cut that fills the capacity)
        self.density_order = sorted(range(len(rows)), key=lambda i: -self.weight[i] * self.flux[i])
        self.planned = [False] * len(rows)
        self.plan_night = -1

    # --- precomputation --------------------------------------------------------------------------

    def _spread_fibers(self, limit: int) -> tuple:
        """All fibres for small grids; for large ones an evenly spaced subset (every k-th row and column)."""
        side = self.grid.side
        if self.grid.n <= limit:
            return tuple(range(self.grid.n))
        k = max(1, int(math.ceil(side / math.sqrt(limit))))
        picks = [r * side + c for r in range(k // 2, side, k) for c in range(k // 2, side, k)]
        return tuple(dict.fromkeys(list(self.central4) + picks))

    def _build_index(self) -> None:
        self.cells: dict[int, list[tuple[float, int]]] = {}
        for i in self.active:
            self.cells.setdefault(int(math.floor(self.dec[i])), []).append((self.ra[i], i))
        for band in self.cells.values():
            band.sort()
        self.cell_ras = {key: [ra for ra, _ in band] for key, band in self.cells.items()}

    def _build_required_calendar(self) -> None:
        """Per night, the best public sky model (airmass + Moon, no weather) a required target can get.
        Uses only geometry and the lunar ephemeris: when the target is highest during that night's window."""
        self.night_best = {}
        if not REQ_CALENDAR:
            return
        lsts = [(start, local_sidereal_deg(start, self.lon), (end - start).total_seconds()) for start, end in self.nights]
        moons: dict = {}
        for i in range(len(self.ids)):
            if not self.required[i] or self.hmax[i] <= 0.0:
                continue
            row = []
            for k, (start, l0, span) in enumerate(lsts):
                # seconds after night start when hour angle is closest to 0
                ha0 = wrap180(l0 - self.ra[i])
                t = min(max(-ha0 / SIDEREAL_DEG_PER_SECOND, 0.0), span)
                ha = wrap180(ha0 + t * SIDEREAL_DEG_PER_SECOND)
                if abs(ha) > self.hmax[i]:
                    row.append(0.0)
                    continue
                key = (k, int(t // 1800))
                moon = moons.get(key)
                if moon is None:
                    moment = start + timedelta(seconds=(key[1] + 0.5) * 1800)
                    moon = moons[key] = Moon(moment, local_sidereal_deg(moment, self.lon), self.lat, self.lunar_model)
                alt, _ = radec_to_altaz(self.ra[i], self.dec[i], l0 + t * SIDEREAL_DEG_PER_SECOND, self.lat)
                row.append(moon.lunar_factor(self.ra[i], self.dec[i])
                           / (self.q0 * normalized_airmass(max(alt, 1.0)) ** self.airmass_exponent))
            self.night_best[i] = row

    def best_future_model(self, i: int, night_index: int) -> float:
        row = self.night_best.get(i)
        if not row or night_index + 1 >= len(row):
            return 0.0
        return max(row[night_index + 1:])

    def neighbours(self, ra: float, dec: float, radius: float) -> list[int]:
        found = []
        if GEOMETRY:
            # Conservative RA extent of a spherical cap, including caps containing a pole.
            width = 180.0 if abs(dec) + radius >= 90.0 else math.degrees(math.asin(min(
                1.0, math.sin(math.radians(radius)) / max(1e-15, math.cos(math.radians(dec))))))
        else:
            cos_dec = max(0.05, math.cos(math.radians(min(89.0, abs(dec) + radius))))
            width = radius / cos_dec
        for key in range(int(math.floor(dec - radius)), int(math.floor(dec + radius)) + 1):
            band = self.cells.get(key)
            if not band:
                continue
            ras = self.cell_ras[key]
            spans = [(0.0, 360.0)] if width >= 180.0 else [(ra - width, ra + width)]
            if spans[0][0] < 0:
                spans = [(0.0, spans[0][1]), (spans[0][0] + 360.0, 360.0)]
            elif spans[0][1] >= 360:
                spans = [(spans[0][0], 360.0), (0.0, spans[0][1] - 360.0)]
            for low, high in spans:
                for k in range(bisect.bisect_left(ras, low), bisect.bisect_right(ras, high)):
                    found.append(band[k][1])
        return found


    def _build_windows(self) -> None:
        """Season windows with enough visibility for the configured minimum exposure.
        The temporal-off ablation retains the original 20-minute filter.
        """
        need = (self.min_exposure if TEMPORAL else 20 * 60) * SIDEREAL_DEG_PER_SECOND
        spans = [(local_sidereal_deg(start, self.lon), (end - start).total_seconds() * SIDEREAL_DEG_PER_SECOND)
                 for start, end in self.nights]
        self.first_night = [len(self.nights)] * len(self.ra)
        self.last_night = [-1] * len(self.ra)
        self.feasible_windows = [[] for _ in self.ra]
        for i in self.active:
            h = self.hmax[i]
            for k, (l0, span) in enumerate(spans):
                if h >= 180.0:
                    overlap = span
                else:
                    a = (self.ra[i] - h - l0) % 360.0
                    overlap = max(0.0, min(span, a + 2 * h) - a) + max(0.0, min(span, a - 360.0 + 2 * h))
                if overlap >= need:
                    self.feasible_windows[i].append((k, overlap / SIDEREAL_DEG_PER_SECOND))
                    if self.first_night[i] > k:
                        self.first_night[i] = k
                    self.last_night[i] = k


    # --- messages and results --------------------------------------------------------------------

    def on_messages(self, messages: list, latest_bulletin) -> None:
        if self.dutylog is not None:
            revision = self.dutylog.version
            self.dutylog.ingest(messages)
            if self.dutylog.version != revision:
                self.reach_cache.clear()
        for message in messages:
            kind = message.get("record_type")
            if kind == "bulletin" and message.get("initial"):
                for notice in message.get("notices", []):
                    if notice.get("event_kind") == "terrain_obstruction":
                        self.terrain.add(notice.get("direction", ""))
            elif kind == "state_resync":
                self._resync(message)
        bulletin = latest_bulletin or {}
        self.notices = {(n.get("event_kind", ""), n.get("direction", "")) for n in bulletin.get("notices", [])
                        if n.get("event_kind") != "terrain_obstruction"}

    def required_satisfied(self, i: int) -> bool:
        return (self.required_status[i] == "confirmed" if self.state_evidence
                else self.factor[i] >= self.required_threshold)

    def needs_required(self, i: int) -> bool:
        return self.required[i] and not self.required_satisfied(i)

    def _factor_bounds(self, i: int, score: float, program=None):
        """Bounds from six-decimal public contributions and possible program multipliers."""
        if self.weight[i] <= 0 or not math.isfinite(score):
            return 0.0, 1.0
        multipliers = ([self.multipliers[program]] if program in self.multipliers
                       else list(self.multipliers.values())) + [self.mismatch]
        lo_score, hi_score = max(0.0, score - 0.5e-6), max(0.0, score + 0.5e-6)
        possible = [(lo_score / (self.weight[i] * m), hi_score / (self.weight[i] * m))
                    for m in multipliers if m > 0 and lo_score <= self.weight[i] * m]
        if any(m == 0 for m in multipliers) and lo_score == 0:
            return 0.0, 1.0  # a zero-multiplier exposure can hide any raw factor
        if not possible:
            return 0.0, 1.0  # inconsistent evidence must not fabricate certainty
        return min(1.0, min(x[0] for x in possible)), min(1.0, max(x[1] for x in possible))

    def _refresh_required(self, i: int) -> None:
        self.required_status[i] = ("confirmed" if self.factor_lower[i] >= self.required_threshold
                                   else "unsatisfied" if self.factor_upper[i] < self.required_threshold
                                   else "unknown")

    def _record_hits(self, result, now):
        index = result.get("observe_index")
        if index is None:
            upcoming = self.result_context.get("observe_action_index")
            index = upcoming - 1 if isinstance(upcoming, int) and not isinstance(upcoming, bool) and upcoming > 0 else None
        if not isinstance(index, int) or isinstance(index, bool):
            return None  # legacy feedback can still train the heuristic without official evidence IDs
        if index in self.hit_ledger:
            return False
        hits = {}
        for row in result.get("hits", []):
            target_id = row.get("target_id")
            score = float(row.get("score", 0.0))
            if target_id not in self.index_of or not math.isfinite(score):
                continue
            hits[target_id] = score
        start = self.pending_start or now - timedelta(seconds=self.pending_duration)
        entry = {"observe_index": index, "program": self.pending_program,
                 "start_utc": start.isoformat(), "end_utc": now.isoformat(),
                 "hits": hits, "factor_estimates": {}, "valid": index not in self.invalidated_observes}
        self.hit_ledger[index] = entry
        if entry["valid"]:
            for target_id, score in hits.items():
                i = self.index_of[target_id]
                lo, hi = self._factor_bounds(i, score, entry["program"])
                self.factor_lower[i] = max(self.factor_lower[i], lo)
                self.factor_upper[i] = max(self.factor_upper[i], hi)
                self.cur[i] = max(self.cur[i], score / self.weight[i])
                self.vdirty.add(i)
                self._refresh_required(i)
        return entry

    def budget_expired(self):
        return (time.process_time() >= getattr(self, "cpu_deadline", float("inf"))
                or time.monotonic() >= getattr(self, "wall_deadline", float("inf")))

    def remaining_opportunities(self, i, night_index, duration):
        """Future geometric slots long enough for this useful exposure, not calendar distance."""
        return sum(k > night_index and span >= duration for k, span in self.feasible_windows[i])

    def duration_candidates(self, seconds_left, level=0, events=()):
        """Declared legal durations; the engine may clip the last exposure shorter."""
        if seconds_left <= 0:
            return []
        low, high = self.min_exposure, self.max_exposure
        if seconds_left < low:
            return [low]
        cap = min(high, int(seconds_left))
        values = {t for t in LEVEL_DURATIONS[min(level, 3)] if low <= t <= cap and t >= MIN_T}
        # Include bounds when the coarse grid cannot represent this instrument/window.
        if not values:
            values.update((low, cap))
        for event in events:
            if math.isfinite(event):
                for t in (math.floor(event), math.ceil(event)):
                    if low <= t <= cap:
                        values.add(int(t))
        return sorted(values)

    def request_gain(self, i, start, actual_duration, factor, probabilistic=False):
        """Per-target request proxy, never credit outside the full request interval."""
        end = start + timedelta(seconds=actual_duration)
        return sum(float(r["completion_reward"]) / r["remaining"] * self._request_probability(
            factor, float(r["completion_factor_threshold"]), probabilistic)
            for r in getattr(self, "requests_by_target", {}).get(i, [])
            if r["start"] <= start and end <= r["deadline"])

    def aggregate_request_gain(self, pick, start, actual_duration, factors, probabilistic=False):
        """Full official reward, or explicitly soft capped progress when probabilistic."""
        end = start + timedelta(seconds=actual_duration)
        picked = set(pick)
        total = 0.0
        for r in getattr(self, "request_records", []):
            if not r["start"] <= start or end > r["deadline"]:
                continue
            count = sum(self._request_probability(factors.get(i, 0.0),
                        float(r["completion_factor_threshold"]), probabilistic)
                        for i in picked & r["indices"])
            credit = min(1.0, count / r["remaining"]) if probabilistic else float(count >= r["remaining"])
            total += float(r["completion_reward"]) * credit
        return total

    @staticmethod
    def _request_probability(factor, threshold, probabilistic):
        if not probabilistic or threshold <= 0:
            return float(factor >= threshold)
        ratio = factor / max(1e-12, threshold)
        return min(1.0, max(0.0, (ratio - REQ_P_LO) / (REQ_P_HI - REQ_P_LO)))

    def set_result_context(self, payload):
        self.result_context = {'observe_action_index': payload.get('observe_action_index')}

    def on_requests(self, requests: list, now: datetime | None = None) -> None:
        """Turn the current all-or-nothing request rewards into per-target planning values."""
        self.requests = requests
        old = self.request_bonus
        self.request_bonus = {}
        self.request_threshold = {}
        self.request_records = []
        self.requests_by_target = {}
        for request in requests:
            # A request that already met its minimum still appears until its deadline
            # with remaining_count 0; its reward is settled, so it adds no value.
            remaining = int(request.get("remaining_count", request["minimum_completed"]))
            if remaining <= 0:
                continue
            completed = set(request.get("completed_target_ids", []))
            unit = REQUEST_MULT * float(request["completion_reward"]) / remaining
            threshold = float(request["completion_factor_threshold"])
            record = dict(request)
            record["start"] = parse_utc(request["issued_at_utc"]) if request.get("issued_at_utc") else self.nights[0][0]
            record["deadline"] = parse_utc(request["deadline_utc"]) if request.get("deadline_utc") else self.survey_end
            record["remaining"] = remaining
            record["indices"] = {self.index_of[t] for t in request["target_ids"] if t in self.index_of and t not in completed}
            self.request_records.append(record)
            for target_id in request["target_ids"]:
                if target_id in completed or target_id not in self.index_of:
                    continue
                i = self.index_of[target_id]
                self.requests_by_target.setdefault(i, []).append(record)
                # Overlapping requests: the marginal rewards add up; the combined gain is
                # only collectible at the highest threshold of the contributing requests.
                self.request_bonus[i] = self.request_bonus.get(i, 0.0) + unit
                self.request_threshold[i] = max(self.request_threshold.get(i, 0.0), threshold)
                if self.hmax[i] > 0.0 and i not in self.active:
                    self.active.append(i)
        if old != self.request_bonus:
            self.vdirty.update(old)
            self.vdirty.update(self.request_bonus)


    def _request_reachable(self, request: dict, open_ids: list, now: datetime) -> int:
        """How many of a request's open targets are above the altitude limit for MIN_VISIBLE_SECONDS at some
        night time before its deadline (cached per request, open set and hour)."""
        if GROUP_REQUESTS and not (DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain):
            deadline = parse_utc(request['deadline_utc'])
            key = (request.get('request_id'),tuple(open_ids),deadline,int(now.timestamp()//3600))
            if key in self.reach_cache:
                return self.reach_cache[key]
            count = sum(any(start_windows(self.ra[self.index_of[tid]], self.hmax[self.index_of[tid]],
                        max(now,start), min(end,deadline), self.lon, MIN_VISIBLE_SECONDS)
                        for start,end in self.nights if end>now and start<deadline) for tid in open_ids)
            if len(self.reach_cache)>256: self.reach_cache.clear()
            self.reach_cache[key] = count
            return count
        key = (request.get("request_id"), tuple(open_ids), int(now.timestamp() // 3600))
        cache = self.reach_cache
        if key in cache:
            return cache[key]
        deadline = parse_utc(request["deadline_utc"])
        step = timedelta(seconds=300)
        dt = MIN_VISIBLE_SECONDS * SIDEREAL_DEG_PER_SECOND
        lim = self.sin_alt_limit
        count = 0
        for target_id in open_ids:
            i = self.index_of[target_id]
            a, b, c = self.alt_a[i], self.alt_b[i], self.alt_c[i]
            seen = False
            for start, end in self.nights:
                if seen or start >= deadline:
                    break
                t, stop = max(start, now), min(end, deadline) - timedelta(seconds=MIN_VISIBLE_SECONDS)
                while t <= stop:
                    lst = math.radians(local_sidereal_deg(t, self.lon))
                    if (a + b * math.cos(lst) + c * math.sin(lst) >= lim
                            and a + b * math.cos(lst + math.radians(dt)) + c * math.sin(lst + math.radians(dt)) >= lim):
                        if DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain:
                            points = [radec_to_altaz(self.ra[i], self.dec[i], math.degrees(lst) + d, self.lat) for d in (0., dt * .5, dt)]
                            if any(alt < self.dutylog.horizon(az) for alt, az in points):
                                t += step
                                continue
                        seen = True
                        break
                    t += step
            count += seen
        if len(cache) > 256:
            cache.clear()
        cache[key] = count
        return count

    def _resync(self, message: dict) -> None:
        """Invalidate announced observations and replay surviving public evidence."""
        best = {row["target_id"]: float(row["best_score"]) for row in message.get("best_scores", [])}
        top = max(self.multipliers.values())
        if not self.state_evidence:
            for i, target_id in enumerate(self.ids):
                score = best.get(target_id, 0.0)
                self.factor[i] = min(1.0, score / (self.weight[i] * top)) if score > 0 else 0.0
                self.cur[i] = score / self.weight[i]
        else:
            window = message.get("invalidated_window", {})
            first = int(window.get("action_index_start", 0))
            last = int(window.get("action_index_end_exclusive", first))
            self.invalidated_observes.update(range(first, last))
            self.factor_lower = [0.0] * len(self.ids)
            self.factor_upper = [0.0] * len(self.ids)
            self.factor = [0.0] * len(self.ids)
            for index, entry in self.hit_ledger.items():
                entry["valid"] = index not in self.invalidated_observes
                if not entry["valid"]:
                    continue
                for target_id, score in entry["hits"].items():
                    i = self.index_of[target_id]
                    lo, hi = self._factor_bounds(i, score, entry["program"])
                    self.factor_lower[i] = max(self.factor_lower[i], lo)
                    self.factor_upper[i] = max(self.factor_upper[i], hi)
                    self.factor[i] = max(self.factor[i], entry["factor_estimates"].get(target_id, lo))
            for i, target_id in enumerate(self.ids):
                score = best.get(target_id, 0.0)
                self.cur[i] = score / self.weight[i]
                if target_id in best:
                    lo, hi = self._factor_bounds(i, score)
                    self.factor_lower[i] = max(self.factor_lower[i], lo)
                    self.factor_upper[i] = max(self.factor_upper[i], hi)
                    self.factor[i] = max(self.factor[i], lo)
                self._refresh_required(i)
            # Learning caches contain observations from the invalidated interval; reset conservatively.
            self.forget_quality_history()
            self.band_obs.clear()
            self.band_level = None
            self.scale = 1.0
            self.offset_evidence.clear()
            self.offset_scores = None
            self.offset_misses = self.offset_updates = 0
            self.offset = (0.0, 0.0)
            self.blocked = []
            self.misses = [0] * len(self.ids)
            self.attempts = [0] * len(self.ids)
            self.req_calib = {}
            self.rate_ema = 0.0
        self.active = [i for i in range(len(self.ids)) if self.hmax[i] > 0.0]
        self.vcache = None
        self.vdirty.clear()
        self.long_dirty = True
        self.season_slot = None
        self.design_slot = None
        self.season_progress_dirty = True
        self.season_refresh_slot = None
        if self.weather is not None:
            previous_forecast = self.weather.forecast
            self.weather = WeatherModel(self.weather.nights)
            self.weather.forecast = previous_forecast
        if self.group_plan is not None:
            self.group_plan.cache_key = None
        self.night_ratios = []
        self.night_medians.clear()
        self.good_scale = 0.0
        self.exposure_bounds = self.exposure_r = None
        self.box_half = EDGE_ASSUME
        self.box = [-EDGE_ASSUME, EDGE_ASSUME, -2 * EDGE_ASSUME, 2 * EDGE_ASSUME]
        if self.pointing is not None:
            self.pointing = PointingModel(self.grid)
        self.pending = {}
        self.pending_start = None
        self.log(f"state_resync: {len(best)} targets keep a score; evidence replayed")


    def site_closed(self) -> bool:
        return any(kind in CLOSED_KINDS and direction == "ALL" for kind, direction in self.notices)

    def all_sky_weather(self) -> bool:
        return any(direction == "ALL" and kind in SKY_WEATHER_KINDS for kind, direction in self.notices)

    def all_sky_notice(self) -> bool:
        return any(direction == "ALL" and kind not in NEUTRAL_KINDS for kind, direction in self.notices)

    def on_result(self, result, now: datetime, hours: float) -> None:
        """Update factor estimates and the sky-quality estimate from the previous observe."""
        self.exposure_r = None
        self.exposure_bounds = None
        self.exposure_closed = False
        self.weather_sample = None
        if not result or result.get("action") != "observe":
            self.pending = {}
            return
        entry = self._record_hits(result, now) if self.state_evidence else None
        if entry is False or (isinstance(entry, dict) and not entry['valid']):
            self.pending = {}
            return
        if not self.pending:
            self.pending = {}
            return
        hits = {hit["target_id"]: float(hit["score"]) for hit in result.get("hits", [])}
        any_positive = any(score > 0 for score in hits.values())
        # every hit scored zero: the dome was shut (an unannounced closed slot); exposures next to it are diluted
        self.exposure_closed = bool(hits) and not any_positive
        declared = self.multipliers[self.pending_program]
        # saturated hits of this exposure show the program band exactly: refit the weather-only band level with
        # them first, then judge match/mismatch of the unsaturated hits from it (the quality-based guess pro used
        # includes the instrument efficiency, so during a fault it called matched hits mismatched)
        fresh = 0
        for target_id, prediction in self.pending.items():
            score = hits.get(target_id)
            if score is not None and score > 0.0:
                seen = score / self.weight[self.index_of[target_id]]
                if abs(seen - declared) < 2e-4 or abs(seen - self.mismatch) < 2e-4:
                    fresh += 1
        band_ref = self.calibrated_band_scale(hours, extra=self._exposure_band_obs(hits, declared, hours)) if fresh else self.band_level
        exposure_ratios = []
        for target_id, prediction in self.pending.items():
            i = self.index_of[target_id]
            self.vdirty.add(i)
            score = hits.get(target_id)
            if score is None:
                if self.pointing is None and prediction.get("p", 1.0) >= 0.999:
                    self.misses[i] += 1  # a miss: the target did not land on its fibre glass
                continue
            if score <= 0.0:
                if any_positive:
                    self.blocked.append((prediction["az"], prediction["alt"]))
                continue
            # score = weight * factor * multiplier; the multiplier is `declared` if the program matched.
            # A saturated hit (factor = 1) shows the multiplier exactly, so it tells whether the sky's
            # program band matched the declared program. Instrument efficiency does not enter the band.
            multiplier_seen = score / self.weight[i]
            self.cur[i] = max(self.cur[i], multiplier_seen)
            if abs(multiplier_seen - declared) < 2e-4:
                self.band_obs.append((hours, prediction["model"], self.pending_program, True, prediction["dir_clean"]))
            elif abs(multiplier_seen - self.mismatch) < 2e-4:
                self.band_obs.append((hours, prediction["model"], self.pending_program, False, prediction["dir_clean"]))
            factor_if_match = score / (self.weight[i] * declared) if declared > 0 else 0.0
            factor_if_miss = score / (self.weight[i] * self.mismatch) if self.mismatch > 0 else factor_if_match
            ratio_match = factor_if_match * self.f0t0 / (self.flux[i] * self.pending_duration * prediction["model"])
            if abs(multiplier_seen - declared) < 2e-4:
                matched = True
            elif abs(multiplier_seen - self.mismatch) < 2e-4:
                matched = False
            elif band_ref and BAND_CLASSIFY:
                matched = self._band(prediction["model"] * band_ref) == self.pending_program
            else:
                matched = self._band(ratio_match * prediction["band_model"]) == self.pending_program
            factor = factor_if_match if matched else factor_if_miss
            self.factor[i] = max(self.factor[i], min(1.0, factor))
            if isinstance(entry, dict):
                entry['factor_estimates'][target_id] = min(1.0, factor)
            self.season_progress_dirty = True
            if self.needs_required(i):
                pred = prediction.get("pred", 0.0)
                if pred > 0 and factor < 0.97:
                    self.req_calib[i] = min(1.0, max(0.3, factor / pred)) ** REQ_CALIB_POWER
                self.attempts[i] += 1  # not enough yet: lower its priority a little for next time
            if factor < 0.97:
                ratio = factor * self.f0t0 / (self.flux[i] * self.pending_duration * prediction["model"])
                self.samples.append((hours, ratio))
                self.all_ratios.append(ratio)
                self.night_ratios.append(ratio)
                if prediction["dir_clean"]:
                    self.e_ratios.append((hours, ratio))
                    exposure_ratios.append(ratio)
        # the fault signal of this exposure: instrument efficiency x weather, from its unsaturated clean hits
        ordered = sorted(exposure_ratios)
        self.exposure_r = ordered[len(ordered) // 2] if ordered else None
        self.exposure_meta = (self.pending_night, self.pending_notices, self.pending_duration)
        # weather-free bounds on the instrument efficiency from the program-band outcome (bandfit.py)
        rows = self._hit_rows(hits, declared)
        self.exposure_bounds = bandfit.exposure_bounds(self.pending_program, rows) if rows else None
        if DUMP_HITS:
            self._dump_exposure(rows, hours)
        if DIAG:
            self.diag['assigned'] += len(self.pending)
            self.diag['hits'] += len(hits)
        if self.weather is not None and any(score > 0 and self.pending[tid]['dir_clean']
                for tid, score in hits.items() if tid in self.pending):
            lo, hi = quality_interval(self.pending_program, result.get('hits', []), self.pending,
                    {t: self.weight[self.index_of[t]] for t in self.pending}, self.multipliers,
                    self.mismatch, self.bands)
            self.weather_sample = (self.pending_night, self.pending_notices, lo, hi)
        if self.pointing is None:
            self._offset_evidence(hits)
        elif self.pending_cmd is not None:
            t0 = time.process_time()
            end_lst = local_sidereal_deg(now, self.lon)
            point_rows = []
            for tid, p in self.pending.items():
                i = self.index_of[tid]
                end_alt = radec_to_altaz(self.ra[i], self.dec[i], end_lst, self.lat)[0]
                if tid in hits or min(p['alt'], end_alt) >= self.min_alt + ALT_MARGIN_DEG:
                    point_rows.append((p['alt'], p['az'], p['fiber'], tid in hits))
            self.pointing.observe(self.pending_cmd, point_rows)
            self.offset = self.pointing.mean
            self.diag['point_cpu'] += time.process_time() - t0
        self.pending = {}
        self.pending_start = None
        self.update_scale(hours)

    def _hit_rows(self, hits: dict, declared: float) -> list:
        """[sky model, efficiency x weather if the program matched, saturated, multiplier seen, direction clean]
        per positive hit of the pending exposure (the input of bandfit.exposure_bounds)."""
        if declared <= 0:
            return []
        rows = []
        for target_id, prediction in self.pending.items():
            score = hits.get(target_id)
            if score is None or score <= 0.0:
                continue
            i = self.index_of[target_id]
            seen = score / self.weight[i]
            ratio = score / (self.weight[i] * declared) * self.f0t0 / (self.flux[i] * self.pending_duration * prediction["model"])
            sat = abs(seen - declared) < 2e-4 or abs(seen - self.mismatch) < 2e-4
            rows.append([prediction["model"], ratio, int(sat), seen if sat else 0.0, int(prediction["dir_clean"])])
        return rows

    def _dump_exposure(self, rows: list, hours: float) -> None:
        """Development only (V5_DUMP_HITS=<file>): one JSON line per exposure with its hit rows (_hit_rows)."""
        rows = [[round(m, 5), round(ratio, 5), sat, round(seen, 5), clean] for m, ratio, sat, seen, clean in rows]
        line = {"h": round(hours, 4), "n": self.pending_night, "T": self.pending_duration, "p": self.pending_program,
                "notices": sorted(f"{k} {d}" for k, d in self.pending_notices), "band": round(self.band_level or 0.0, 4),
                "hits": rows}
        with open(DUMP_HITS, "a", encoding="utf-8") as out:
            out.write(json.dumps(line, separators=(",", ":")) + "\n")

    def _exposure_band_obs(self, hits: dict, declared: float, hours: float) -> list:
        out = []
        for target_id, prediction in self.pending.items():
            score = hits.get(target_id)
            if score is None or score <= 0.0:
                continue
            seen = score / self.weight[self.index_of[target_id]]
            if abs(seen - declared) < 2e-4:
                out.append((hours, prediction["model"], self.pending_program, True, prediction["dir_clean"]))
            elif abs(seen - self.mismatch) < 2e-4:
                out.append((hours, prediction["model"], self.pending_program, False, prediction["dir_clean"]))
        return out

    # --- pointing offset (Hard-mode cards) ----------------------------------------------------------------

    def _offset_evidence(self, hits: dict) -> None:
        """Hard-mode cards add a hidden fixed offset to every pointing (participant guide: actual = command +
        (d_alt, d_az)). Each assigned target's hit or miss is evidence; keep a score for each candidate offset
        on a grid and adopt the best one once it clearly explains the misses better than no offset."""
        if not self.pending or self.pending_cmd is None:
            return
        rows = [(p["alt"], p["az"], p["fiber"], target_id in hits) for target_id, p in self.pending.items() if "fiber" in p]
        if not rows:
            return
        missed = sum(1 for row in rows if not row[3])
        self.offset_misses += missed
        self.offset_evidence.append((self.pending_cmd, rows))
        if EDGE_BOX:
            self._box_update(self.pending_cmd, rows)
        if self.offset_misses < OFFSET_MIN_MISSES:
            return
        if self.offset_scores is None:
            self._rescore_offsets(list(self.offset_evidence))
        else:
            self._score_offsets(self.pending_cmd, rows)
        self.offset_updates += 1
        if self.offset_updates % OFFSET_REFINE_EVERY == 1 or OFFSET_REFINE_EVERY <= 1:
            self._refine_offset()

    def _box_cut(self, box: list, cmd, rows) -> bool:
        """Intersect the offset box with what one observe's outcomes allow. False if they contradict it.

        Linearised about the box centre r: a target at (n, e) from its fibre centre, seen from the field centre
        cmd + r, lands at (n - (o_alt - r_alt), e - (o_az - r_az) cos alt) for the true offset o; it hits iff
        both stay within half the glass. A hit bounds o on both axes; a miss bounds the axis that must have
        failed, when the other one was inside for every offset in the box."""
        hg = self.grid.glass / 2.0
        r_alt, r_az = (box[0] + box[1]) / 2.0, (box[2] + box[3]) / 2.0
        c_alt, c_az = cmd[0] + r_alt, (cmd[1] + r_az) % 360.0
        cos_c = max(0.05, math.cos(math.radians(c_alt)))
        for t_alt, t_az, fiber, hit in rows:
            offsets = tangent_offsets(t_alt, t_az, c_alt, c_az)
            if offsets is None:
                continue
            f_north, f_east = self.grid.fiber_center(fiber)
            x_n, x_e = offsets[0] - f_north, offsets[1] - f_east
            # bounds of o - r on each axis that keep the target on its glass (east converted to az degrees)
            n_lo, n_hi = x_n - hg - EDGE_TOL, x_n + hg + EDGE_TOL
            e_lo, e_hi = (x_e - hg - EDGE_TOL) / cos_c, (x_e + hg + EDGE_TOL) / cos_c
            a0, a1, z0, z1 = box[0] - r_alt, box[1] - r_alt, box[2] - r_az, box[3] - r_az
            if hit:
                a0, a1, z0, z1 = max(a0, n_lo), min(a1, n_hi), max(z0, e_lo), min(z1, e_hi)
            else:
                n_ok = n_lo + 2 * EDGE_TOL <= a0 and a1 <= n_hi - 2 * EDGE_TOL
                e_ok = e_lo + 2 * EDGE_TOL / cos_c <= z0 and z1 <= e_hi - 2 * EDGE_TOL / cos_c
                if n_ok and e_ok:
                    return False          # it should have landed for every offset in the box
                if n_ok:                  # east failed: o - r lies below e_lo or above e_hi
                    below, above = (z0, min(z1, e_lo + 2 * EDGE_TOL / cos_c)), (max(z0, e_hi - 2 * EDGE_TOL / cos_c), z1)
                    if below[0] > below[1]:
                        z0, z1 = above
                    elif above[0] > above[1]:
                        z0, z1 = below
                elif e_ok:
                    below, above = (a0, min(a1, n_lo + 2 * EDGE_TOL)), (max(a0, n_hi - 2 * EDGE_TOL), a1)
                    if below[0] > below[1]:
                        a0, a1 = above
                    elif above[0] > above[1]:
                        a0, a1 = below
            if a0 > a1 or z0 > z1:
                return False
            box[:] = [a0 + r_alt, a1 + r_alt, z0 + r_az, z1 + r_az]
        return True

    def _box_update(self, cmd, rows) -> None:
        """Narrow the offset box with the last observe; on a contradiction widen it around the learned offset and
        replay the recent evidence. Once narrow, command with the box centre."""
        box = list(self.box)
        if self._box_cut(box, cmd, rows):
            self.box = box
        else:
            self._box_reset(widen=True)
            self.log(f"offset box: outcomes contradict it, widened to +-{self.box_half:.3f} deg")
        box = self.box
        half_alt, half_az = (box[1] - box[0]) / 2.0, (box[3] - box[2]) / 2.0
        if half_alt < EDGE_ASSUME / 2.0 and half_az < EDGE_ASSUME:
            centre = (round((box[0] + box[1]) / 2.0, 4), round((box[2] + box[3]) / 2.0, 4))
            if abs(centre[0] - self.offset[0]) + abs(centre[1] - self.offset[1]) > 0.001:
                self.offset = centre

    def _box_reset(self, widen: bool) -> None:
        """A box around the learned offset (wider each time when widen), narrowed by the recent evidence."""
        while True:
            if widen:
                self.box_half = min(EDGE_MAX, 2.0 * self.box_half)
            box = [self.offset[0] - self.box_half, self.offset[0] + self.box_half,
                   self.offset[1] - 2.0 * self.box_half, self.offset[1] + 2.0 * self.box_half]
            if all(self._box_cut(box, c, r) for c, r in list(self.offset_evidence)[-100:]) or self.box_half >= EDGE_MAX:
                break
            widen = True
        self.box = box

    def _consistent(self, cmd, rows, d_alt, d_az) -> int:
        c_alt, c_az = cmd[0] + d_alt, (cmd[1] + d_az) % 360.0
        ok = 0
        for t_alt, t_az, fiber, hit in rows:
            offsets = tangent_offsets(t_alt, t_az, c_alt, c_az)
            fib = self.grid.classify(*offsets)[0] if offsets is not None else None
            ok += (fib == fiber) == hit
        return ok

    def _make_offset_grid(self) -> list:
        n, step = self.offset_steps, self.offset_step
        return [(step * i, step * j) for i in range(-n, n + 1) for j in range(-n, n + 1)]

    def _rescore_offsets(self, evidence) -> None:
        self.offset_scores = [0] * len(self.offset_grid)
        for cmd, past in evidence:
            self._score_offsets(cmd, past)

    def _score_offsets(self, cmd, rows) -> None:
        for k, (d_alt, d_az) in enumerate(self.offset_grid):
            self.offset_scores[k] += self._consistent(cmd, rows, d_alt, d_az)

    def _refine_offset(self) -> None:
        k = max(range(len(self.offset_grid)), key=lambda n: self.offset_scores[n])
        base_alt, base_az = self.offset_grid[k]
        n = self.offset_steps
        edge = max(abs(base_alt), abs(base_az)) >= (n - 0.5) * self.offset_step
        if edge and (n + 1) * self.offset_step < self.grid.fov / 2.0:
            # the best candidate sits on the edge of the grid: the offset may be larger, widen the search
            self.offset_steps = int(n * 1.5) + 1
            self.offset_grid = self._make_offset_grid()
            self._rescore_offsets(list(self.offset_evidence)[-100:])
            self.log(f"pointing offset: search widened to +-{self.offset_steps * self.offset_step:.2f} deg")
            k = max(range(len(self.offset_grid)), key=lambda m: self.offset_scores[m])
            base_alt, base_az = self.offset_grid[k]
        evidence = list(self.offset_evidence)[-OFFSET_FINE_EVIDENCE:]
        zero = sum(self._consistent(cmd, rows, 0.0, 0.0) for cmd, rows in evidence)
        scored = []
        fine = self.offset_step / 5.0
        for i in range(-6, 7):
            for j in range(-6, 7):
                d_alt, d_az = base_alt + fine * i, base_az + fine * j
                scored.append((sum(self._consistent(cmd, rows, d_alt, d_az) for cmd, rows in evidence), d_alt, d_az))
        top = max(score for score, _, _ in scored)
        if top - zero < OFFSET_MARGIN:
            return
        # several offsets often explain the evidence equally well: take the centre of that set
        tied = [(d_alt, d_az) for score, d_alt, d_az in scored if score == top]
        centre = (round(sum(a for a, _ in tied) / len(tied), 3), round(sum(z for _, z in tied) / len(tied), 3))
        if abs(centre[0] - self.offset[0]) + abs(centre[1] - self.offset[1]) < 0.005:
            return
        if EDGE_BOX and self.box[1] - self.box[0] < EDGE_ASSUME and self.box[3] - self.box[2] < 2.0 * EDGE_ASSUME:
            return   # the offset box is already narrower than this search: it sets the offset
        total = sum(len(rows) for _, rows in evidence)
        self.log(f"pointing offset: alt {centre[0]:+.3f} az {centre[1]:+.3f} deg explains {top}/{total} "
                 f"fibre outcomes (no offset: {zero}; {len(tied)} equally good grid points)")
        if self.offset == (0.0, 0.0):
            self.misses = [0] * len(self.ids)   # the misses were the offset, not the targets
            self.vcache = None
        self.offset = centre
        if EDGE_BOX:
            self._box_reset(widen=False)

    def calibrated_band_scale(self, hours: float, extra=()) -> float:
        """Sky level for the program band, fitted to recent saturated hits (they show the multiplier exactly).
        Falls back to the quality-based estimate; an unreported instrument fault lowers quality but not the band."""
        guess = self.scale / 0.95
        recent = [item for item in self.band_obs if item[0] >= hours - BAND_MEMORY_HOURS] + list(extra)
        if len(recent) < 4 and BAND_FALLBACK:
            # few saturated hits lately (poor quality, or an instrument fault): the band does not follow the
            # instrument, so keep fitting the latest saturated hits instead of the quality level
            recent = [item for item in self.band_obs if item[0] >= hours - BAND_FALLBACK_HOURS][-8:]
        if len(recent) < 4:
            return guess
        # among equally consistent levels prefer the one closest to the last fitted level (the sky band moves
        # with the weather, not with the instrument), else to the quality-based guess
        centre = self.band_level if (BAND_CONT and self.band_level) else guess
        best = None
        if BAND_HALF_LIFE > 0:
            weights = [0.5 ** ((hours - h) / BAND_HALF_LIFE) for h, _, _, _, _ in recent]
        else:
            weights = [1.0] * len(recent)
        for step in range(-25, 31):
            w = centre * (1.06 ** step)
            ok = sum(wt for wt, (_, model, program, matched, _) in zip(weights, recent) if (self._band(model * w) == program) == matched)
            key = (round(ok, 6), -abs(step))
            if best is None or key > best[0]:
                best = (key, w)
        self.band_level = best[1]
        return best[1]

    def clean_e(self, hours: float):
        """E = clean-sky quality level / clean-sky band level over the last BAND_MEMORY_HOURS (1 = consistent)."""
        ratios = sorted(r for h, r in self.e_ratios if h >= hours - BAND_MEMORY_HOURS)
        obs = [item for item in self.band_obs if item[0] >= hours - BAND_MEMORY_HOURS and item[4]]
        if len(ratios) < 4 or len(obs) < 4:
            return None
        guess = ratios[len(ratios) // 2] / 0.95
        best = None
        for step in range(-20, 31):
            w = guess * (1.06 ** step)
            ok = sum(1 for _, model, program, matched, _ in obs if (self._band(model * w) == program) == matched)
            key = (ok, -abs(step))
            if best is None or key > best[0]:
                best = (key, w)
        return min(1.0, guess / best[1])

    def update_scale(self, hours: float) -> None:
        """Sky quality now = median of recent samples; fall back to the long-run median when stale."""
        if len(self.all_ratios) >= 8:
            ordered = sorted(self.all_ratios)
            self.prior_scale = ordered[len(ordered) // 2]
        recent = sorted(ratio for when, ratio in self.samples if when >= hours - SKY_MEMORY_HOURS)
        self.scale = max(0.05, recent[len(recent) // 2]) if len(recent) >= 4 else self.prior_scale

    def _close_night(self, night_index: int) -> None:
        """A new night: keep the last night's median quality ratio; a typical night = the WX_Q quantile of them."""
        if night_index == self.ratio_night:
            return
        self.ratio_night = night_index
        if len(self.night_ratios) >= 5:
            ordered = sorted(self.night_ratios)
            self.night_medians.append(ordered[len(ordered) // 2])
        self.night_ratios = []
        if len(self.night_medians) >= WX_MIN_NIGHTS:
            ordered = sorted(self.night_medians)
            self.good_scale = ordered[min(len(ordered) - 1, int(WX_Q * len(ordered)))]

    def _band(self, q_band: float) -> str:
        if q_band >= float(self.bands["DARK"]):
            return "DARK"
        if q_band >= float(self.bands["BRIGHT"]):
            return "BRIGHT"
        return "BACKUP"

    # --- anomaly check ---------------------------------------------------------------------------

    def forget_quality_history(self) -> None:
        """After a correct report the instrument is repaired: start the quality estimates afresh."""
        self.e_hours = []
        self.e_ratios.clear()
        self.samples.clear()
        self.all_ratios.clear()
        self.prior_scale = 1.0

    # --- planning --------------------------------------------------------------------------------

    def current_night(self, now: datetime):
        for k, (start, end) in enumerate(self.nights):
            if start <= now < end:
                return k, start, end
        return None

    def next_night_start(self, now: datetime):
        for start, _ in self.nights:
            if start > now:
                return start
        return None

    def _direction_factor(self, alt: float, az: float) -> float:
        factor = 1.0
        known = DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain
        if known and alt < self.dutylog.horizon(az):
            return 0.0
        for direction in (() if known else self.terrain):
            if direction in DIRECTION_AZ and alt < 50.0 and _az_distance(az, DIRECTION_AZ[direction]) <= 60.0:
                return 0.0
        for kind, direction in self.notices:
            if LP_WEATHER and kind == 'cold_snap':
                continue
            if direction not in DIRECTION_AZ:
                continue
            near = _az_distance(az, DIRECTION_AZ[direction]) <= 67.5
            if kind in BLOCKING_KINDS and near and alt < 62.0:
                return 0.0
            if near and alt < 75.0:
                factor = min(factor, 0.35)
        for direction in self.extra_avoid:
            if direction in DIRECTION_AZ and _az_distance(az, DIRECTION_AZ[direction]) <= 67.5 and alt < 70.0:
                factor = min(factor, 0.35)
        for blocked_az, blocked_alt in (() if known else self.blocked[-40:]):
            if _az_distance(az, blocked_az) <= 12.0 and alt <= blocked_alt + 3.0:
                factor = min(factor, 0.2)
        return factor

    def _fault_clean(self, alt: float, az: float) -> bool:
        """No directional notice near this direction at any altitude. A sector event reaches up to ~80 deg
        altitude and scales the quality but not the program band, so a field under it fakes a low efficiency
        bound (card b: SE overcast at 76 deg altitude read as efficiency <= 0.54, a paid false report)."""
        for kind, direction in self.notices:
            if direction in DIRECTION_AZ and kind not in NEUTRAL_KINDS and alt < 85.0 \
                    and _az_distance(az, DIRECTION_AZ[direction]) <= 75.0:
                return False
        return True

    def value(self, i: int) -> float:
        f = self.factor[i]
        damp = 0.6 ** self.misses[i]
        request = self.request_bonus.get(i, 0.0)
        if self.required[i]:
            if self.required_satisfied(i) and f >= REQUIRED_SAFE_FACTOR:
                return (self.weight[i] * max(0.0, 1.0 - f * f) + request) * damp
            return (self.weight[i] * (1.0 - f * f) + REQUIRED_BONUS * (1.0 if self.needs_required(i) else 0.35) + request) * damp
        return ((0.0 if f >= DONE_FACTOR else self.weight[i] * (1.0 - f * f)) + request) * damp

    def _season_plan(self, now: datetime, night_index: int) -> None:
        """Which targets will the season complete? Fill the remaining useful fibre-time with targets in
        order of value density (w * flux); the rest are fillers whose partial exposures are worth taking."""
        self.plan_night = night_index
        cap = sum(max(0.0, (end - max(start, now)).total_seconds()) for start, end in self.nights if end > now)
        cap *= self.grid.n * PLAN_UTIL
        self.planned = [False] * len(self.ids)
        n = 0
        for i in self.density_order:
            if cap <= 0:
                break
            if self.hmax[i] <= 0.0 or self.factor[i] >= DONE_FACTOR:
                continue
            cap -= min(self.max_exposure, self.f0t0 / (max(self.flux[i], 1e-3) * PLAN_Q))
            self.planned[i] = True
            n += 1
        self.log(f"season plan: {n} targets to complete")

    def _seconds_to_rise(self, lst: float, min_up_deg: float, seconds_left: float):
        """Seconds until the first target that still has value is up for min_up (60 s steps, one slot ahead);
        None when nothing rises within the slot."""
        vc, pa, pb, pc, lim = self.vcache, self.alt_a, self.alt_b, self.alt_c, self.sin_alt_limit
        horizon = min(self.slot_seconds, seconds_left - self.min_exposure)
        steps = []
        t = 60
        while t <= horizon:
            r1 = math.radians(lst + t * SIDEREAL_DEG_PER_SECOND)
            r2 = r1 + math.radians(min_up_deg)
            steps.append((t, math.cos(r1), math.sin(r1), math.cos(r2), math.sin(r2)))
            t += 60
        best = None
        for i in self.active:
            if vc[i] <= 0.0:
                continue
            a, b, c = pa[i], pb[i], pc[i]
            for t, c1, s1, c2, s2 in steps:
                if best is not None and t >= best:
                    break
                if a + b * c1 + c * s1 >= lim and a + b * c2 + c * s2 >= lim:
                    best = t
                    break
        if WALL and best is None:
            # ponytail: cap the long scan at 200 valuable targets; widen only if T4 shows missed value.
            targets = heapq.nlargest(200,(i for i in self.active if vc[i]>0.),key=lambda i:(vc[i],-i))
            for t in range(int(horizon)+300,int(seconds_left-self.min_exposure)+1,300):
                r1=math.radians(lst+t*SIDEREAL_DEG_PER_SECOND)
                r2=r1+math.radians(min_up_deg)
                c1,s1,c2,s2=math.cos(r1),math.sin(r1),math.cos(r2),math.sin(r2)
                if any(pa[i]+pb[i]*c1+pc[i]*s1>=lim and pa[i]+pb[i]*c2+pc[i]*s2>=lim for i in targets):
                    best=t
                    break
        return best

    def monitor(self, now: datetime, night_end: datetime, night_index: int, hours: float):
        """An observe action that only watches the instrument efficiency, or None: when no target has value
        left (a time-rich card late in the season), exposures stop and so would the fault evidence, while a
        fault goes on until reported. Any target up serves: the unsaturated hits give r, all hits the bands."""
        if self.budget_expired():
            return None
        seconds_left = (min(night_end, self.survey_end) - now).total_seconds()
        if DL_FLAT and self.dutylog is not None:
            seconds_left = self.dutylog.clip_exposure(now, seconds_left)
        T = int(min(MONITOR_T, seconds_left, self.max_exposure))
        if T < self.min_exposure:
            return None
        lst = local_sidereal_deg(now, self.lon)
        moon = Moon(now + timedelta(seconds=T / 2), lst, self.lat, self.lunar_model)
        c1, s1 = math.cos(math.radians(lst)), math.sin(math.radians(lst))
        lim = math.sin(math.radians(min(80.0, self.min_alt + 10.0)))
        pa, pb, pc = self.alt_a, self.alt_b, self.alt_c
        up = {}
        for i in range(len(self.ids)):
            if pa[i] + pb[i] * c1 + pc[i] * s1 < lim:
                continue
            alt, az = radec_to_altaz(self.ra[i], self.dec[i], lst, self.lat)
            if self._direction_factor(alt, az) < 1.0:
                continue
            if DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain:
                if any(a < self.dutylog.horizon(z) for a, z in
                       (radec_to_altaz(self.ra[i], self.dec[i], lst + dt * SIDEREAL_DEG_PER_SECOND, self.lat) for dt in (T * .5, T))):
                    continue
            model = moon.lunar_factor(self.ra[i], self.dec[i]) / (self.q0 * normalized_airmass(max(alt, 1.0)) ** self.airmass_exponent)
            reach = self.flux[i] * T * model * self.scale / self.f0t0
            up[i] = (alt, az, model, 1.0 if reach < 0.9 else 0.25)   # an unsaturated hit gives r as well
        if not up:
            return None
        grid = self.grid
        half_fov, g_mid, g_side, g_pitch = grid.fov / 2.0, grid.side / 2.0, grid.side, grid.pitch
        g_center = (grid.side - 1) / 2.0
        box_wide = max(self.box[1] - self.box[0], (self.box[3] - self.box[2]) * 0.5)
        keep = grid.glass / 2.0 - box_wide - EDGE_MARGIN_DEG
        deg = 180.0 / math.pi
        ranked = sorted(up, key=lambda i: (up[i][3], up[i][0]), reverse=True)
        step = max(1, len(ranked) // MONITOR_ANCHORS)
        best = None
        for anchor in ranked[::step][:MONITOR_ANCHORS]:
            if self.budget_expired():
                break
            fiber = self.central4[0]
            d_north, d_east = grid.fiber_center(fiber)
            c_alt, c_az = shift_altaz(up[anchor][0], up[anchor][1], -d_north, -d_east)
            if not self.min_alt <= c_alt <= 89.0:
                continue
            c_alt, c_az = round(c_alt, 4), round(c_az, 4) % 360.0
            calt, caz = math.radians(c_alt), math.radians(c_az)
            sa, ca, sz, cz = math.sin(calt), math.cos(calt), math.sin(caz), math.cos(caz)
            cells: dict = {}
            for j in self.neighbours(self.ra[anchor], self.dec[anchor], self.neighbour_radius):
                if j not in up or self.misses[j] > 1:
                    continue
                ta, tz = math.radians(up[j][0]), math.radians(up[j][1])
                t0, t1, t2 = math.cos(ta) * math.cos(tz), math.cos(ta) * math.sin(tz), math.sin(ta)
                depth = t0 * ca * cz + t1 * ca * sz + t2 * sa
                if depth <= 0.0:
                    continue
                dn = deg * ((-t0 * sa * cz - t1 * sa * sz + t2 * ca) / depth)
                de = deg * ((-t0 * sz + t1 * cz) / depth)
                if abs(dn) > half_fov or abs(de) > half_fov:
                    continue
                row = min(max(int(math.floor(dn / g_pitch + g_mid)), 0), g_side - 1)
                col = min(max(int(math.floor(de / g_pitch + g_mid)), 0), g_side - 1)
                if max(abs(dn - (row - g_center) * g_pitch), abs(de - (col - g_center) * g_pitch)) > keep:
                    continue
                cell = row * g_side + col
                if up[j][3] > cells.get(cell, (0.0, -1))[0]:
                    cells[cell] = (up[j][3], j)
            total = sum(v for v, _ in cells.values())
            if total > 0 and (best is None or total > best[0]):
                best = (total, c_alt, c_az, {fib: j for fib, (_, j) in cells.items()})
        if best is None:
            return None
        _, c_alt, c_az, pick = best
        band_scale = self.calibrated_band_scale(hours) * BAND_OPT
        votes = {"DARK": 0, "BRIGHT": 0, "BACKUP": 0}
        for j in pick.values():
            votes[self._band(up[j][2] * band_scale)] += 1
        program = max(votes, key=lambda p: (votes[p], self.multipliers[p]))
        clean = not self.all_sky_notice()
        self.pending = {}
        for fib, j in pick.items():
            alt, az, model, _ = up[j]
            self.pending[self.ids[j]] = {"model": model, "band_model": model / 0.95, "alt": alt, "az": az,
                                        "pred": self.flux[j] * T * model * self.scale / self.f0t0,
                                        "clean": clean, "dir_clean": self._fault_clean(alt, az), "p": 1.0, "fiber": fib}
        self.pending_program = program
        self.pending_duration = T
        self.pending_start = now
        self.pending_night = night_index
        self.pending_notices = set(self.notices)
        cmd_alt = round(min(90.0, max(0.0, c_alt - self.offset[0])), 4)
        cmd_az = round((c_az - self.offset[1]) % 360.0, 4)
        if cmd_az >= 360.0:
            cmd_az = 0.0
        self.pending_cmd = (cmd_alt, cmd_az)
        return {"action": "observe", "pointing": {"alt_deg": cmd_alt, "az_deg": cmd_az},
                "assignments": {str(fib): self.ids[j] for fib, j in sorted(pick.items())},
                "duration_seconds": T, "program": program}

    def plan(self, now: datetime, night_end: datetime, night_index: int, hours: float):
        """Return an observe action dict, or None when nothing useful is up."""
        started_cpu = time.process_time()
        state_cpu = getattr(self, 'cpu_components', {}).get('state_update', 0.0)
        self.cpu_components = {'candidate_generation': 0.0, 'visibility': 0.0, 'fiber_assignment': 0.0,
                               'exposure_search': 0.0, 'lookahead': 0.0, 'state_update': state_cpu, 'season': 0.0}
        self.decision_record = {'alternatives': [], 'constraints': {'feasible': None, 'reason': 'NO_OBSERVE_SELECTED'}}
        if self.budget_expired():
            return None
        self.next_up = None
        self.last_plan_gain = 0.
        if DIAG and self.diag_night != night_index:
            self.flush_diagnostics()
            self.diag_night = night_index
        if PARTIAL_DISCOUNT < 1.0 and night_index != self.plan_night:
            self._season_plan(now, night_index)
        self.update_scale(hours)
        self._close_night(night_index)
        refresh_slot = (night_index, int(local_sidereal_deg(now, self.lon) // 15))
        refresh = bool(SEASON_REFRESH and self.season_progress_dirty and refresh_slot != self.season_refresh_slot)
        if self.season is not None and (night_index != self.season_night or self.long_dirty or refresh):
            t0 = time.process_time()
            due = self.long_dirty or self.season.price is None or night_index - self.season.night >= season.OPT_REPRICE if SEASON_MODE == 'option' else True
            if due and SEASON_MODE == 'option' and (self.weather is not None or DESI_HA):
                self.season.configure_slots(self.weather.predict(now) if self.weather is not None else None, now)
            complete = self.season.update(self.factor, night_index, force=self.long_dirty or refresh,
                                          best_scores=[w*c for w,c in zip(self.weight, self.cur)],
                                          deadline=self.budget_expired)
            self.cpu_components['season'] += time.process_time() - t0
            self.diag['season_cpu'] += time.process_time() - t0
            self.diag['reprices'] += int(due or refresh)
            self.long_dirty = not complete
            if complete:
                self.season_progress_dirty = False
                self.season_refresh_slot = refresh_slot
            self.season_slot = None
            self.design_slot = None
            if SEASON_MODE != "option":
                mult, region = self.season.mult, self.season.region_of
                self.smult = [mult[region[i]] ** SEASON_GAMMA for i in range(len(self.ids))]
            if self.season_night < 0 or night_index % 15 == 0:
                self.log(f"season: night {night_index} demand/supply {self.season.ratio:.2f} prices {self.season.summary()}")
            self.season_night = night_index
        self.night_index = night_index
        lst = local_sidereal_deg(now, self.lon)
        if SEASON_MODE == "option" and self.season is not None and (night_index, int(lst // 15.0)) != self.season_slot:
            # the multiplier compares this LST hour with the best later block: recompute it every hour
            self.season_slot = (night_index, int(lst // 15.0))
            mult, region = self.season.mult_now(lst), self.season.region_of
            self.smult = [mult[region[i]] ** SEASON_GAMMA for i in range(len(self.ids))]
        science_priority = self.smult
        if DESI_HA and SEASON_MODE == 'option' and self.season is not None:
            key = (night_index,int(lst//15))
            if key != self.design_slot:
                self.design_slot = key
                self.design_priority = []
                proxy_lst = key[1]*15+7.5
                for i in range(len(self.ids)):
                    design = self.season.design_ha[self.season.region_of[i]]
                    delta = wrap180(wrap180(proxy_lst-self.ra[i])-design) if design is not None else 0.
                    self.design_priority.append(design_weight(delta)
                                                if self.last_night[i] > night_index else 1.)
            science_priority = [self.smult[i] * self.design_priority[i] for i in range(len(self.smult))]
        focus = self.group_plan.update(self.requests, now) if self.group_plan is not None else set()
        horizon = min(night_end, self.survey_end)
        seconds_left = (horizon - now).total_seconds()
        if DL_FLAT and self.dutylog is not None:
            seconds_left = self.dutylog.clip_exposure(now, seconds_left)
        if seconds_left <= 0:
            return None
        lst_later = lst + 1800.0 * SIDEREAL_DEG_PER_SECOND
        moon = Moon(now + timedelta(seconds=600), lst, self.lat, self.lunar_model)
        scale = self.scale * PLAN_FACTOR_SAFETY
        band_scale = self.calibrated_band_scale(hours) * BAND_OPT
        e_now = self.clean_e(hours)
        if e_now is not None and not (WEATHER_GATE and self.all_sky_weather()):
            hour = int(hours)
            if not self.e_hours or self.e_hours[-1][0] != hour:
                self.e_hours.append((hour, night_index, []))
            self.e_hours[-1][2].append(e_now)
        visibility_started = time.process_time()
        min_up = min(self.min_exposure if TEMPORAL else MIN_VISIBLE_SECONDS, seconds_left)
        level = self.fast_level
        base = {}
        visible = {}
        still_active = []
        min_up_deg = min_up * SIDEREAL_DEG_PER_SECOND
        sl, cl = self.sin_lat, self.cos_lat
        sin_min = math.sin(math.radians(self.min_alt))
        deep = self.deep and level == 0
        width = min(5.0, max(1.0, float(getattr(self, "search_width_multiplier", 1.0))))
        pool_size = min(len(self.ids), int(DEEP_POOL * width)) if deep else (POOL, POOL // 2, POOL // 4, POOL // 8, POOL // 8)[min(level, 4)]
        proxy = []
        science_proxy = []
        bins: dict = {}
        bin_best: dict = {}
        sd, cd = self.sin_dec, self.cos_dec
        if self.vcache is None:
            self.vcache = [self.value(i) for i in range(len(self.ids))]
        else:
            for i in self.vdirty:
                self.vcache[i] = self.value(i)
        self.vdirty = set()
        vc = self.vcache
        hmax, ra = self.hmax, self.ra
        # sin(alt) = A + B cos(LST) + C sin(LST): no trigonometry per target
        pa, pb, pc = self.alt_a, self.alt_b, self.alt_c
        c1, s1 = math.cos(math.radians(lst)), math.sin(math.radians(lst))
        c2, s2 = math.cos(math.radians(lst + min_up_deg)), math.sin(math.radians(lst + min_up_deg))
        sin_lim = self.sin_alt_limit
        terrain_positions = {}
        terrain_ceiling = (math.sin(math.radians(max(self.min_alt, *(v[0] for v in self.dutylog.terrain.values()))))
                           if DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain else None)
        for position, i in enumerate(self.active):
            if position % 256 == 0 and self.budget_expired():
                still_active.extend(self.active[position:])
                break
            a = pa[i]
            sin_alt = a + pb[i] * c1 + pc[i] * s1
            if sin_alt < sin_lim or a + pb[i] * c2 + pc[i] * s2 < sin_lim:
                still_active.append(i)   # not up now (or setting soon): keep it, check its value when it rises
                continue
            v = vc[i]
            if v <= 0.0:
                continue
            still_active.append(i)
            # Reject mountain-blocked targets BEFORE the bounded priority pool.
            # Above the highest terrain no extra geometry is needed; reuse lower positions in exact().
            if terrain_ceiling is not None and sin_alt < terrain_ceiling:
                position = radec_to_altaz(self.ra[i], self.dec[i], lst, self.lat)
                if position[0] < self.dutylog.horizon(position[1]):
                    continue
                terrain_positions[i] = position
            visible[i] = None
            # proxy priority: planning value x a rough airmass factor x urgency (no Moon, no direction)
            nights_left = (1 + self.remaining_opportunities(i, night_index, min_up) if TEMPORAL else self.last_night[i] - night_index + 1)
            if REWARD_SPLIT:
                request_proxy = self.request_bonus.get(i,0.)
                protected = request_proxy
                if self.required[i] and self.factor[i] < REQUIRED_SAFE_FACTOR:
                    protected += REQUIRED_BONUS*(1. if self.factor[i] < .5 else .35)
                protected *= .6**self.misses[i]
                v = max(0.,v-protected)*science_priority[i]+protected
                if i in focus: v += .25*request_proxy*.6**self.misses[i]
            proxy.append((v * (sin_alt ** 0.6) * (1.0 + URGENCY / (nights_left if nights_left > 1 else 1))
                          * (1. if REWARD_SPLIT else self.smult[i]), i))
            science_proxy.append((self.weight[i] * max(0.0, max(self.multipliers.values()) - self.cur[i]) * sin_alt ** 0.6, i))
            if N_DENSE:
                # plain science still to gain here, binned on the sky at roughly one field size
                key = (int((self.ra[i] * cd[i]) // DENSE_BIN_DEG), int((self.dec[i] + 90.0) // DENSE_BIN_DEG))
                dense_val = self.weight[i] * max(0.0, 1.0 - self.cur[i] / 1.2) * (sin_alt ** 0.6) * science_priority[i]
                bins[key] = bins.get(key, 0.0) + dense_val
                if dense_val > bin_best.get(key, (0.0, -1))[0]:
                    bin_best[key] = (dense_val, i)
        self.active = still_active
        self.cpu_components["visibility"] = time.process_time() - visibility_started
        if not visible:
            if WAIT_TO_RISE:
                self.next_up = self._seconds_to_rise(lst, min_up_deg, seconds_left)
            return None

        def exact(i):
            item = base.get(i)
            if item is None and i not in base:
                ha = (lst - self.ra[i] + 180.0) % 360.0 - 180.0
                position = terrain_positions.get(i)
                alt, az = position if position is not None else radec_to_altaz(self.ra[i], self.dec[i], lst, self.lat)
                dirf = self._direction_factor(alt, az)
                if alt < self.min_alt or dirf <= 0.0:
                    base[i] = None
                    return None
                h = self.hmax[i]
                up = (h - ha) / SIDEREAL_DEG_PER_SECOND if h < 180.0 else 1e9
                lunar = moon.lunar_factor(self.ra[i], self.dec[i])
                nights_left = max(1, self.last_night[i] - night_index + 1)
                damp = 0.6 ** self.misses[i] * 0.8 ** self.attempts[i]
                item = base[i] = (alt, az, lunar, up, (1.0 + URGENCY / nights_left) * damp * dirf * (1. if REWARD_SPLIT else self.smult[i]))
            return item

        pool = [i for _, i in (heapq.nlargest(pool_size, proxy) if len(proxy) > pool_size else proxy)]
        for i in pool:
            if self.budget_expired():
                break
            exact(i)
        pool = [i for i in pool if base.get(i) is not None]
        if not pool:
            return None
        info = {}

        def full(i):
            item = info.get(i)
            if item is None:
                alt, az, lunar, up, mult = base[i]
                alt2, _ = radec_to_altaz(self.ra[i], self.dec[i], lst_later, self.lat)
                m0 = lunar / (self.q0 * normalized_airmass(max(alt, 1.0)) ** self.airmass_exponent)
                m1 = lunar / (self.q0 * normalized_airmass(max(alt2, 1.0)) ** self.airmass_exponent)
                item = info[i] = (alt, az, m0, m1, up, mult)
            return item

        top_mult = max(self.multipliers.values())

        def science_price(i, T):
            if not DESI_HA or SEASON_MODE != 'option' or self.season is None or self.last_night[i] <= night_index:
                return science_priority[i]
            design = self.season.design_ha[self.season.region_of[i]]
            if design is None:
                return self.smult[i]
            delta = wrap180(wrap180(lst+T*.5*SIDEREAL_DEG_PER_SECOND-self.ra[i])-design)
            return self.smult[i] * design_weight(delta)

        def shaped(v):
            """Convex value of score/weight v: finishing a target beats half-doing it twice, because only
            its best exposure counts (a partial exposure is wasted if the target is redone later)."""
            return top_mult * (v / top_mult) ** KAPPA if KAPPA != 1.0 else v

        def timing(i, model):
            """Science now vs at the target's best moment (transit, Moon down): time spent at a poor airmass
            buys less than the same time later, while nights are left to wait for it."""
            left = self.last_night[i] - night_index
            if left <= 0:
                return 1.0
            return min(1.0, model / self.ideal_model[i]) ** (TIMING_BETA * min(1.0, left / TIMING_NIGHTS))

        def reach_timing(i, T, reach):
            """Share of the reach this exposure would get at the target's best moment (same T): 1 for a
            target that saturates either way, the sky-model ratio for a faint one."""
            left = self.last_night[i] - night_index
            if left <= 0:
                return 1.0
            best = min(1.0, self.flux[i] * T * self.ideal_model[i] * scale / self.f0t0)
            return min(1.0, reach / best) ** (REACH_BETA * min(1.0, left / TIMING_NIGHTS)) if best > 0.0 else 1.0

        # tonight's sky vs a typical night's: under a poor sky a faint target's exposure is mostly superseded
        # later, under a good one it gets what a typical night cannot give (symmetric, so the mix stays balanced)
        wx = self.good_scale / self.scale if WX_BETA and self.good_scale > 0.0 else 1.0

        def weather_timing(i, reach, T, model):
            """(reach now / reach under the typical night's sky, same T and sky model) ** WX_BETA."""
            left = self.last_night[i] - night_index
            if left <= 0:
                return 1.0
            typical = min(1.0, self.flux[i] * T * model * scale * wx / self.f0t0)
            return (reach / typical) ** (WX_BETA * min(1.0, left / TIMING_NIGHTS)) if typical > 0.0 else 1.0

        gain_cache = {}
        science_rate_cache = {}
        def predicted_factor(i, T):
            _, _, m0, m1, _, _ = full(i)
            actual = min(T, seconds_left)
            model = m0 + (m1-m0) * min(1.0, actual/3600.0)
            return min(1.0, max(0.0, self.flux[i]*actual*model*self.scale/self.f0t0))

        def gain(i, T, program=None):
            key = (i, T, program)
            if GAIN_CACHE and key in gain_cache:
                return gain_cache[key]
            result = uncached_gain(i, min(T, seconds_left), program)
            if GAIN_CACHE:
                gain_cache[key] = result
            return result

        def uncached_gain(i, T, program):
            alt, az, m0, m1, up, mult = full(i)
            if up < T:
                return 0.0
            if DL_HORIZON and self.dutylog is not None and self.dutylog.has_terrain:
                if any(a < self.dutylog.horizon(z) for a, z in
                       (radec_to_altaz(self.ra[i], self.dec[i], lst + dt * SIDEREAL_DEG_PER_SECOND, self.lat) for dt in (T * .5, T))):
                    return 0.0
            model = m0 + (m1 - m0) * min(1.0, T / 3600.0)
            reach = min(1.0, self.flux[i] * T * model * scale / self.f0t0)
            band = self._band(model * band_scale)
            m = self.multipliers[band] if program is None or band == program else self.mismatch
            if SCIENCE_TIME_PRICE:
                science_rate_cache[i,T,program] = self.weight[i]*max(0.0,reach*m-self.cur[i])
            g = self.weight[i] * max(0.0, shaped(reach * m) - shaped(self.cur[i]))
            if TIMING_BETA and g > 0.0:
                g *= timing(i, model)
            if REACH_BETA and g > 0.0:
                g *= reach_timing(i, T, reach)
            if wx != 1.0 and g > 0.0:
                g *= weather_timing(i, reach, T, model)
            if reach < PARTIAL_DONE and self.planned[i] and self.last_night[i] - night_index >= PARTIAL_NIGHTS:
                g *= PARTIAL_DISCOUNT   # it will be completed later: this partial exposure would be wasted
            bonus = request_gain = 0.
            if self.needs_required(i):
                raw = self.flux[i] * T * model * self.scale / self.f0t0 / max(1e-12, self.required_threshold) * self.req_calib.get(i, 1.0)
                bonus = REQUIRED_BONUS * min(1.0, max(0.0, (raw - REQ_P_LO) / (REQ_P_HI - REQ_P_LO)))
                target_best = self.best_future_model(i, night_index) if REQ_CALENDAR else self.ideal_model[i]
                if REQ_TIMING and model < REQ_TIMING * target_best and self.last_night[i] - night_index >= REQ_TIMING_NIGHTS:
                    bonus *= REQ_TIMING_DISCOUNT   # a better moment for this target will come
                if self.bad_forecast and self.last_night[i] - night_index >= REQ_TIMING_NIGHTS:
                    bonus *= FORECAST_DISCOUNT     # tonight is forecast bad over the whole sky
                if not REWARD_SPLIT: g += bonus
            if TEMPORAL:
                request_gain = REQUEST_MULT * self.request_gain(i, now, T, predicted_factor(i,T), True)
            elif i in self.request_bonus:
                threshold = self.request_threshold.get(i, 0.5)
                raw = self.flux[i] * T * model * self.scale / self.f0t0 / max(1e-6, threshold)
                request_gain = self.request_bonus[i] * min(1.0, max(0.0, (raw-REQ_P_LO)/(REQ_P_HI-REQ_P_LO)))
            if REWARD_SPLIT and i in focus:
                request_gain *= GROUP_BOOST
            if not REWARD_SPLIT:
                g += request_gain
            return goal_gain(g, bonus, request_gain, science_price(i,T), mult) if REWARD_SPLIT else g * mult

        def quick(i, T):
            """gain() with the start-of-exposure sky model only (no second alt/az): for ranking."""
            alt, az, lunar, up, mult = base[i]
            T = min(T, up, seconds_left)
            if T < min(self.min_exposure, seconds_left):
                return 0.0, T
            model = lunar / (self.q0 * normalized_airmass(max(alt, 1.0)) ** self.airmass_exponent)
            reach = min(1.0, self.flux[i] * T * model * scale / self.f0t0)
            g = self.weight[i] * max(0.0, shaped(reach * self.multipliers[self._band(model * band_scale)]) - shaped(self.cur[i]))
            if TIMING_BETA and g > 0.0:
                g *= timing(i, model)
            if REACH_BETA and g > 0.0:
                g *= reach_timing(i, T, reach)
            if wx != 1.0 and g > 0.0:
                g *= weather_timing(i, reach, T, model)
            if reach < PARTIAL_DONE and self.planned[i] and self.last_night[i] - night_index >= PARTIAL_NIGHTS:
                g *= PARTIAL_DISCOUNT
            bonus = request_gain = 0.
            if self.needs_required(i):
                raw = self.flux[i] * T * model * self.scale / self.f0t0 / max(1e-12, self.required_threshold)
                bonus = REQUIRED_BONUS * min(1.0, max(0.0, (raw - REQ_P_LO) / (REQ_P_HI - REQ_P_LO)))
                if not REWARD_SPLIT: g += bonus
            if TEMPORAL:
                request_gain = REQUEST_MULT * self.request_gain(i, now, T,
                    min(1.0, self.flux[i]*T*model*self.scale/self.f0t0), True)
            elif i in self.request_bonus:
                raw = self.flux[i]*T*model*self.scale/self.f0t0/max(1e-6,self.request_threshold.get(i,0.5))
                request_gain = self.request_bonus[i]*min(1.0,max(0.0,(raw-REQ_P_LO)/(REQ_P_HI-REQ_P_LO)))
            if REWARD_SPLIT and i in focus:
                request_gain *= GROUP_BOOST
            if not REWARD_SPLIT:
                g += request_gain
            return (goal_gain(g, bonus, request_gain, science_price(i,T), mult) if REWARD_SPLIT else g * mult), T

        durations = self.duration_candidates(seconds_left, level)
        if not durations:
            return None
        t_long = durations[-1]
        t_mid = durations[len(durations) // 2]
        lam = self.lambda_frac * self.rate_ema
        ranked = []
        for i in pool:
            g1, T1 = quick(i, t_long)
            g2, T2 = quick(i, t_mid)
            best_net = max(g1 - lam * T1 / self.grid.n, g2 - lam * T2 / self.grid.n)
            if best_net > 0:
                ranked.append((best_net, i))
        if not ranked:
            self.rate_ema *= 0.9
            lam = 0.0
            ranked = [(quick(i, t_long)[0], i) for i in pool]
            ranked = [item for item in ranked if item[0] > 0]
        if not ranked:
            return None
        ranked.sort(reverse=True)
        n_anchors = int(DEEP_ANCHORS * width) if deep else (N_ANCHORS, 3, 1, 1)[min(level, 3)]
        anchors = [i for _, i in ranked[:n_anchors]]
        if SPECIAL_ANCHORS:
            protected = [i for _,i in proxy if self.needs_required(i) or i in self.request_bonus]
            for i in sorted(protected, key=lambda i: (-vc[i], i))[:SPECIAL_ANCHORS]:
                if i not in anchors and exact(i) is not None:
                    anchors.insert(0, i)
        n_value_anchors = len(anchors)
        if SCIENCE_ANCHORS and level <= 1:
            # A separate science stream prevents required-state/proxy truncation
            # from hiding high marginal-score fields elsewhere in the sky.
            science_seeds = []
            for _, i in heapq.nlargest(max(pool_size, 6 * int(SCIENCE_ANCHORS * width)), science_proxy):
                if self.budget_expired():
                    break
                if exact(i) is None:
                    continue
                _, _, m0, m1, up, _ = full(i)
                best_science = 0.0
                for T in (t_mid, t_long):
                    actual = min(T, seconds_left)
                    if up < actual:
                        continue
                    model = m0 + (m1 - m0) * min(1.0, actual / 3600.0)
                    reach = min(1.0, self.flux[i] * actual * model * scale / self.f0t0)
                    marginal = self.weight[i] * max(0.0, reach * self.multipliers[self._band(model * band_scale)] - self.cur[i])
                    best_science = max(best_science, marginal)
                if best_science > 0:
                    science_seeds.append((best_science, i))
            for _, i in heapq.nlargest(int(SCIENCE_ANCHORS * width) if level == 0 else min(8, SCIENCE_ANCHORS), science_seeds):
                if i not in anchors:
                    anchors.append(i)
        if N_DENSE and level <= 1 and bins:
            # also try the densest patches of remaining science: fields with no single outstanding target
            for _, key in heapq.nlargest((int(DEEP_DENSE * width) if deep else N_DENSE) if level == 0 else 2, ((v, k) for k, v in bins.items())):
                j = bin_best[key][1]
                if j not in anchors and exact(j) is not None:
                    anchors.append(j)
        fibers = (self.anchor_fibers, self.anchor_fibers, self.central4, self.central4[:1])[min(level, 3)]
        best = None
        leaders = []
        seen_centers = set()
        best_rate_here = 0.0
        best_rate = [0.0]
        vcache3: dict = {}

        def unit(j):
            v = vcache3.get(j)
            if v is None:
                alt, az = math.radians(base[j][0]), math.radians(base[j][1])
                ca = math.cos(alt)
                v = vcache3[j] = (ca * math.cos(az), ca * math.sin(az), math.sin(alt))
            return v

        grid = self.grid
        half_fov = grid.fov / 2.0
        g_mid = grid.side / 2.0
        g_side = grid.side
        g_pitch = grid.pitch
        g_half_glass = grid.glass / 2.0
        g_center = (grid.side - 1) / 2.0
        edge = EDGE_MARGIN_DEG
        misses = self.misses
        deg = 180.0 / math.pi
        hgf = g_half_glass - EDGE_FLOOR
        box_n = (self.box[0] - self.offset[0], self.box[1] - self.offset[0])   # true offset - commanded correction
        box_z = (self.box[2] - self.offset[1], self.box[3] - self.offset[1])
        box_wide = max(box_n[1] - box_n[0], (box_z[1] - box_z[0]) * 0.5)

        def overlap(x, lo, hi):
            """Share of offsets in [lo, hi] (uniform) for which a target x from its fibre centre stays on glass."""
            if hi - lo < 1e-7:
                return 1.0 if x - hgf <= lo and hi <= x + hgf else 0.0
            return max(0.0, min(hi, x + hgf) - max(lo, x - hgf)) / (hi - lo)

        def neighborhood(c_alt, c_az, legacy=()):
            if not GEOMETRY:
                return list(legacy)
            r,d = altaz_to_radec(c_alt,c_az,lst,self.lat)
            return [j for j in self.neighbours(r,d,self.grid.query_radius_deg) if j in visible and exact(j) is not None]

        def event_durations(near):
            events = [self.min_exposure, self.max_exposure, seconds_left]
            for r in sorted(getattr(self, "request_records", []), key=lambda r: r["deadline"])[:EVENT_MAX]:
                events.append((r["deadline"] - now).total_seconds())
            # Leading targets supply model-derived roots, including non-monotonic quadratics.
            for j in sorted(near, key=lambda i: (-vc[i], i))[:EVENT_MAX]:
                if self.budget_expired():
                    break
                _, _, m0, m1, up, _ = full(j)
                events.append(up)
                rate = self.flux[j] * scale / self.f0t0
                thresholds = [1.0, self.required_threshold, float(self.score_config_uniformity_threshold)]
                thresholds += [self.cur[j] / m for m in set(self.multipliers.values()) | {self.mismatch} if m > 0]
                thresholds += [float(r["completion_factor_threshold"]) for r in getattr(self, "requests_by_target", {}).get(j, [])[:EVENT_MAX]]
                a, b = rate * (m1 - m0) / 3600.0, rate * m0
                for threshold in thresholds:
                    if abs(a) < 1e-15:
                        if b > 0:
                            events.append(threshold / b)
                    else:
                        disc = b * b + 4 * a * threshold
                        if disc >= 0:
                            for t in ((-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a)):
                                if 0 < t <= 3600:
                                    events.append(t)
                    if rate * m1 > 0 and threshold / (rate * m1) > 3600:
                        events.append(threshold / (rate * m1))
                if m1 != m0 and band_scale > 0:
                    events.extend(3600 * (float(band) / band_scale - m0) / (m1 - m0)
                                  for band in self.bands.values())
            # Preserve reason/target priority above; do not let dense fields expand the grid without limit.
            bounded = []
            for event in events:
                if math.isfinite(event) and self.min_exposure <= event <= min(seconds_left, self.max_exposure):
                    if all(abs(event - prior) >= 1.0 for prior in bounded):
                        bounded.append(event)
                if len(bounded) >= EVENT_LIMIT:
                    break
            return self.duration_candidates(seconds_left, level, bounded)

        def evaluate(c_alt, c_az, near, durs, programs=(None,)):
            if self.budget_expired():
                return None
            geometry_start = time.process_time()
            """Best (net, T, pick, total, chance) for one pointing, or None."""
            calt, caz = math.radians(c_alt), math.radians(c_az)
            sa, ca, sz, cz = math.sin(calt), math.cos(calt), math.sin(caz), math.cos(caz)
            c0, c1, c2 = ca * cz, ca * sz, sa
            n0, n1, n2 = -sa * cz, -sa * sz, ca
            e0, e1 = -sz, cz
            if EDGE_BOX:
                be0, be1 = box_z[0] * ca, box_z[1] * ca
                n_lo, n_hi = box_n[1] - hgf, box_n[0] + hgf    # a target inside these lands for every offset
                e_lo, e_hi = be1 - hgf, be0 + hgf
            cells: dict = {}
            for j in near:
                t0, t1, t2 = unit(j)
                depth = t0 * c0 + t1 * c1 + t2 * c2
                if depth <= 0.0:
                    continue
                dn = deg * ((t0 * n0 + t1 * n1 + t2 * n2) / depth)
                de = deg * ((t0 * e0 + t1 * e1 + t2 * 0.0) / depth)
                if abs(dn) > half_fov or abs(de) > half_fov:
                    continue
                if DIAG:
                    self.diag['evaluated'] += 1
                row = min(max(int(math.floor(dn / g_pitch + g_mid)), 0), g_side - 1)
                col = min(max(int(math.floor(de / g_pitch + g_mid)), 0), g_side - 1)
                if self.pointing is not None:
                    fiber = row * g_side + col
                    p = self.pointing.p_inside(dn, de, fiber, c_alt)
                    if p < .05:
                        if DIAG: self.diag['edge_rejected'] += 1
                        continue
                    cells.setdefault(fiber, []).append((j, p))
                    continue
                if EDGE_BOX:
                    xn, xe = dn - (row - g_center) * g_pitch, de - (col - g_center) * g_pitch
                    if misses[j]:
                        if g_half_glass - max(abs(xn), abs(xe)) < box_wide + edge * (0.5 + 1.5 * misses[j]):
                            continue
                        p = 1.0
                    elif n_lo <= xn <= n_hi and e_lo <= xe <= e_hi:
                        p = 1.0
                    else:
                        p = overlap(xn, box_n[0], box_n[1]) * overlap(xe, be0, be1)
                        if p < EDGE_P_MIN:
                            if DIAG: self.diag['edge_rejected'] += 1
                            continue
                    cells.setdefault(row * g_side + col, []).append((j, p))
                    continue
                margin = g_half_glass - max(abs(dn - (row - g_center) * g_pitch), abs(de - (col - g_center) * g_pitch))
                if margin < 0.0 or margin < edge * (0.5 + 1.5 * misses[j]):
                    continue
                cells.setdefault(row * g_side + col, []).append((j, 1.0))
            self.cpu_components['fiber_assignment'] += time.process_time()-geometry_start
            if not cells:
                return None
            duration_start = time.process_time()
            if TEMPORAL:
                minimum = min(self.min_exposure, seconds_left)
                first = min(min(durs), seconds_left)
                short_events = []
                for js in cells.values():
                    for j, _ in js:
                        up = base[j][3]
                        if minimum <= up < first:
                            short_events.extend((self.min_exposure, up))
                        for request in self.requests_by_target.get(j, []):
                            left = (request['deadline']-now).total_seconds()
                            if minimum <= left < first:
                                short_events.extend((self.min_exposure,left))
                if short_events:
                    durs = sorted(set(durs) | set(self.duration_candidates(seconds_left,level,short_events)))
            found = None
            for T in durs:
                if self.budget_expired():
                    break
                actual = min(T,seconds_left)
                for program in programs:
                    pick = {}
                    chance = {}
                    total = 0.0
                    for fib, js in cells.items():
                        g,j,prob = max((gain(j,T,program)*prob,j,prob) for j,prob in js)
                        if g > 0:
                            pick[fib],chance[fib] = j,prob
                            total += g
                    if not pick:
                        continue
                    if TEMPORAL and self.request_records:
                        factors = {j:predicted_factor(j,T) for j in pick.values()}
                        proxy_request = sum(self.request_gain(j,now,actual,factors[j],True)*full(j)[5]*chance[fib]
                                            for fib,j in pick.items())
                        bounded = self.aggregate_request_gain(pick.values(),now,actual,factors,True)
                        total += REQUEST_MULT*(bounded-proxy_request)
                    priced_gain = (sum(science_rate_cache.get((j,actual,program),0.0)*chance[fib] for fib,j in pick.items())
                                   if SCIENCE_TIME_PRICE else total)
                    if priced_gain/actual > best_rate[0]:
                        best_rate[0] = priced_gain/actual
                    net = total-lam*actual-(self.wall_action_cost if WALL else 0.0)
                    if found is None or net > found[0]:
                        found = (net,T,pick,total,chance,program)
            self.cpu_components['exposure_search'] += time.process_time()-duration_start
            return found

        best_near = None
        coarse_started = time.process_time()
        available = max(0.0, getattr(self,"cpu_deadline",float("inf"))-coarse_started)
        coarse_deadline = coarse_started + 0.75*available
        for rank, anchor in enumerate(anchors):
            if self.budget_expired() or (best is not None and time.process_time() >= coarse_deadline):
                break
            a_alt, a_az = base[anchor][0], base[anchor][1]
            legacy = [] if GEOMETRY else [j for j in self.neighbours(self.ra[anchor],self.dec[anchor],self.neighbour_radius) if j in visible and exact(j) is not None]
            # density anchors mark a patch, not a target to centre: a few central placements, then refine
            for fiber in (fibers if rank < n_value_anchors else self.central4):
                if self.budget_expired() or (best is not None and time.process_time() >= coarse_deadline):
                    break
                d_north, d_east = self.grid.fiber_center(fiber)
                c_alt, c_az = shift_altaz(a_alt, a_az, -d_north, -d_east)
                if not (0.0 if GEOMETRY else self.min_alt) <= c_alt <= (90.0 if GEOMETRY else 89.0):
                    continue
                c_alt, c_az = round(c_alt, 4), round(c_az, 4) % 360.0
                if (c_alt,c_az) in seen_centers:
                    continue
                seen_centers.add((c_alt,c_az))
                near = neighborhood(c_alt,c_az,legacy)
                found = evaluate(c_alt, c_az, near, durations)
                if found is not None:
                    candidate = (found[0],c_alt,c_az,found[1],found[2],found[3],found[4],found[5])
                    leaders.append((candidate,near))
                    leaders.sort(key=lambda item: -item[0][0])
                    del leaders[max(1,EXACT_TOPK):]
                if found is not None and (best is None or found[0] > best[0]):
                    best = (found[0], c_alt, c_az, found[1], found[2], found[3], found[4], found[5])
                    best_near = near
        # Coarse gains use an optimistic per-target program. Preserve a legal
        # fixed-assignment fallback evaluated under ONE declared program before
        # comparing exact leaders; no geometric search is needed for this checkpoint.
        if best is not None and PROGRAM_AWARE:
            coarse = best
            actual = min(coarse[3],seconds_left)
            options = []
            for program in self.multipliers:
                total = sum(gain(j,coarse[3],program)*coarse[6].get(fib,1.0) for fib,j in coarse[4].items())
                if TEMPORAL and self.request_records:
                    factors = {j:predicted_factor(j,coarse[3]) for j in coarse[4].values()}
                    proxy = sum(self.request_gain(j,now,actual,factors[j],True)*full(j)[5]*coarse[6].get(fib,1.0)
                                for fib,j in coarse[4].items())
                    total += REQUEST_MULT*(self.aggregate_request_gain(coarse[4].values(),now,actual,factors,True)-proxy)
                net = total-lam*actual-(self.wall_action_cost if WALL else 0.0)
                options.append((net,total,program))
            net,total,program = max(options,key=lambda item:(item[0],item[2]))
            best = (net,coarse[1],coarse[2],coarse[3],coarse[4],total,coarse[6],program)
        if best is not None and (PROGRAM_AWARE or EVENT_DURATIONS):
            for candidate, near in leaders:
                if self.budget_expired():
                    break
                times = event_durations(near) if EVENT_DURATIONS else durations
                programs = tuple(self.multipliers) if PROGRAM_AWARE else (None,)
                found = evaluate(candidate[1],candidate[2],near,times,programs)
                if found is not None and found[0] > best[0]:
                    best = (found[0],candidate[1],candidate[2],found[1],found[2],found[3],found[4],found[5])
                    best_near = near
        if best is not None and REFINE_STEPS and level == 0:
            # local search: nudge the winning pointing to catch targets near the cell edges
            for _ in range(REFINE_ROUNDS):
                if self.budget_expired():
                    break
                improved = False
                b_alt, b_az = best[1], best[2]
                for d_north, d_east in REFINE_STEPS:
                    if self.budget_expired():
                        break
                    c_alt, c_az = shift_altaz(b_alt, b_az, d_north, d_east)
                    if not (0.0 if GEOMETRY else self.min_alt) <= c_alt <= (90.0 if GEOMETRY else 89.0):
                        continue
                    c_alt, c_az = round(c_alt, 4), round(c_az, 4) % 360.0
                    near = neighborhood(c_alt,c_az,best_near)
                    times = event_durations(near) if EVENT_DURATIONS else ((best[3],) if REFINE_FIXED_T else durations)
                    found = evaluate(c_alt,c_az,near,times,tuple(self.multipliers) if PROGRAM_AWARE else (None,))
                    if found is not None and found[0] > best[0] + 1e-9:
                        best = (found[0], c_alt, c_az, found[1], found[2], found[3], found[4], found[5])
                        improved = True
                if not improved:
                    break
        best_rate_here = best_rate[0]
        self.rate_ema = (1 - LAMBDA_EMA) * self.rate_ema + LAMBDA_EMA * best_rate_here if self.rate_ema > 0 else best_rate_here
        if best is None or best[5] <= 0:
            if int(hours) != getattr(self, "_dbgnone", None):
                self._dbgnone = int(hours)
                self.log(f"plan none: info={len(info)} ranked={len(ranked)} scale={self.scale:.3f} lam={lam:.4f} best={best and best[:1]}")
            return None
        _, c_alt, c_az, T, pick, _, chance, evaluated_program = best
        actual_T = min(T,seconds_left)
        self.last_plan_gain = best[5]
        # program: maximise expected score over the assigned targets
        votes = {"DARK": 0.0, "BRIGHT": 0.0, "BACKUP": 0.0}
        for fib, j in pick.items():
            alt, az, m0, m1, up, _ = info[j]
            model = m0 + (m1 - m0) * min(1.0, actual_T / 3600.0)
            reach = min(1.0, self.flux[j] * actual_T * model * scale / self.f0t0)
            votes[self._band(model * band_scale)] += self.weight[j] * reach + (0.05 * REQUIRED_BONUS if self.required[j] else 0.0)
        total_votes = sum(votes.values())
        program = max(votes, key=lambda p: (votes[p] * self.multipliers[p] + (total_votes - votes[p]) * self.mismatch, p))
        if evaluated_program is not None:
            program = evaluated_program
        clean = not self.all_sky_notice()
        self.pending = {}
        for fib, j in pick.items():
            alt, az, m0, m1, up, _ = info[j]
            model = m0 + (m1 - m0) * min(1.0, actual_T / 3600.0)
            dir_clean = self._direction_factor(alt, az) >= 1.0 and self._fault_clean(alt, az)
            self.pending[self.ids[j]] = {"model": model, "band_model": model / 0.95, "alt": alt, "az": az,
                                        "pred": self.flux[j] * actual_T * model * self.scale / self.f0t0,
                                        "clean": clean and dir_clean, "dir_clean": dir_clean,
                                        "p": chance.get(fib, 1.0)}
        self.pending_program = program
        self.pending_duration = actual_T
        self.pending_start = now
        self.pending_night = night_index
        self.pending_notices = set(self.notices)
        for fib, j in pick.items():
            self.pending[self.ids[j]]["fiber"] = fib
        # the mount lands at command + offset: command the desired centre minus the learned offset
        cmd_alt = round(min(90.0, max(0.0, c_alt - self.offset[0])), 4)
        cmd_az = round((c_az - self.offset[1]) % 360.0, 4)
        if self.pointing is not None:
            cmd_alt, cmd_az = self.pointing.command(c_alt, c_az)
        if cmd_az >= 360.0:
            cmd_az = 0.0
        self.pending_cmd = (cmd_alt, cmd_az)
        actual_alt, actual_az = cmd_alt+self.offset[0], (cmd_az+self.offset[1])%360.0
        checked = {}
        for fib,j in pick.items():
            offsets = tangent_offsets(base[j][0],base[j][1],actual_alt,actual_az)
            reached, margin = self.grid.classify(*offsets) if offsets is not None else (None,-1.0)
            if reached == fib and full(j)[4] >= actual_T and 0 <= actual_alt <= 90:
                checked[fib] = j
        pick = checked
        self.pending = {self.ids[j]: self.pending[self.ids[j]] for j in pick.values()}
        if not pick:
            return None
        science = 0.0
        factors = {}
        for j in pick.values():
            factors[j] = predicted_factor(j,T)
            model = self.pending[self.ids[j]]['model']
            reach = min(1.0,self.flux[j]*actual_T*model*scale/self.f0t0)
            mult = self.multipliers[program] if self._band(model*band_scale) == program else self.mismatch
            science += self.weight[j]*max(0.0,reach*mult-self.cur[j])
        self.decision_record = {
            'predicted': {'science_gain': science, 'request_reward': self.aggregate_request_gain(pick.values(),now,actual_T,factors),
                          'quality': {self.ids[j]:self.pending[self.ids[j]]['model']*self.scale for j in pick.values()},
                          'required_penalty_relief': {'lower':0.0,'upper':self.required_penalty*sum(self.needs_required(j) and factors[j]>=self.required_threshold for j in pick.values())},
                          'uniformity_delta':None,'report_delta':0.0,'uncertainty':'public model; actual weather, band and pointing offset hidden'},
            'heuristic': {'utility':best[5],'net':best[0],'time_price':lam},
            'constraints': {'feasible':True,'actual_duration_seconds':actual_T,'horizon':horizon.isoformat(),
                            'visibility_slack_seconds':min(full(j)[4]-actual_T for j in pick.values()),
                            'requests':[{'request_id':r.get('request_id'),'start':r['start'].isoformat(),'deadline':r['deadline'].isoformat(),
                                         'finish_slack_seconds':(r['deadline']-now).total_seconds()-actual_T,
                                         'eligible':r['start']<=now and now+timedelta(seconds=actual_T)<=r['deadline']} for r in self.request_records]},
            'assignment': {'n_fibers':self.grid.n,'n_assigned':len(pick),'unused_fibers':[f for f in range(self.grid.n) if f not in pick],
                           'required':[self.ids[j] for j in pick.values() if self.required[j]],'timed':[self.ids[j] for j in pick.values() if j in self.request_bonus]},
            'alternatives': [{'pointing':{'alt_deg':c[1],'az_deg':c[2]},'duration_seconds':c[3],'program':c[7],
                              'utility':c[5],'net':c[0],'rejection_reason':'LOWER_SEARCH_UTILITY'} for c,_ in leaders if c[1:4]!=best[1:4]][:5],
            'search': {'centers':len(seen_centers),'width_multiplier':width,'interrupted':self.budget_expired(),'gain_cache_entries':len(gain_cache)}}
        self.cpu_components['candidate_generation'] = max(0.0,time.process_time()-started_cpu-sum(v for k,v in self.cpu_components.items() if k!='state_update'))
        return {"action": "observe", "pointing": {"alt_deg": cmd_alt, "az_deg": cmd_az},
                "assignments": {str(fib): self.ids[j] for fib, j in sorted(pick.items())},
                "duration_seconds": int(T), "program": program}

    def flush_diagnostics(self):
        if not DIAG or self.diag_night is None:
            return
        data = {'night': self.diag_night, **self.diag, 'level': self.fast_level,
                'deep': self.deep, 'box_half_alt': (self.box[1]-self.box[0])/2,
                'box_half_az': (self.box[3]-self.box[2])/2,
                'pointing': self.pointing.summary() if self.pointing else None,
                'weather': self.weather.summary() if self.weather else None,
                'season': self.season.summary() if self.season and self.season.price else None,
                'v61': {'desi_ha': DESI_HA, 'reward_split': REWARD_SPLIT,
                        'groups': self.group_plan.diagnostics if self.group_plan else None}}
        self.log('v6diag ' + json.dumps(data, separators=(',', ':')))
        self.diag = dict.fromkeys(self.diag, 0)
