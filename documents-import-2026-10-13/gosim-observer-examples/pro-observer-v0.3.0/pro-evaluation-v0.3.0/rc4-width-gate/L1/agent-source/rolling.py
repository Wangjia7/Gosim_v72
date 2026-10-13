"""Public geometry and bounded, advisory request-group planning. No solver dependency."""
import math
import os
import time
from datetime import timedelta
from skymath import SIDEREAL_DEG_PER_SECOND, local_sidereal_deg, parse_utc, wrap180

DESI_HA_WIDTH = float(os.environ.get('V6_DESI_HA_WIDTH_DEG', '30'))
DESI_HA_FLOOR = float(os.environ.get('V6_DESI_HA_FLOOR', '.75'))
GROUP_BOOST = float(os.environ.get('V6_GROUP_BOOST', '1.25'))
GROUP_HORIZON = float(os.environ.get('V6_GROUP_HORIZON_DAYS', '7'))
GROUP_CPU_FAST = float(os.environ.get('V6_GROUP_CPU_FAST', '.02'))
GROUP_CPU_FULL = float(os.environ.get('V6_GROUP_CPU_FULL', '.05'))
FIXED_LEVEL = int(os.environ.get('V5_FIXED_LEVEL', os.environ.get('PRO_FIXED_LEVEL', '-1')))
DL_REQ = os.environ.get('V6_DL_REQ', '0') == '1'
if (not all(math.isfinite(v) for v in (DESI_HA_WIDTH, DESI_HA_FLOOR, GROUP_BOOST,
                                     GROUP_HORIZON, GROUP_CPU_FAST, GROUP_CPU_FULL))
        or DESI_HA_WIDTH <= 0 or not 0 <= DESI_HA_FLOOR <= 1 or GROUP_BOOST < 1
        or GROUP_HORIZON <= 0 or not 0 < GROUP_CPU_FAST <= GROUP_CPU_FULL):
    raise ValueError('invalid v6.1 HA or request-group tuning parameters')


def design_weight(delta):
    return max(DESI_HA_FLOOR, math.exp(-.5*(delta/DESI_HA_WIDTH)**2))


def start_windows(ra, hmax, start, end, lon, duration):
    """All start intervals for a full exposure above the altitude cut, including RA wrap."""
    span = (end-start).total_seconds()
    if duration <= 0 or span < duration or hmax <= 0:
        return []
    if hmax >= 180:
        return [(start, end-timedelta(seconds=duration))]
    ha = wrap180(local_sidereal_deg(start, lon)-ra)
    stop = ha + span*SIDEREAL_DEG_PER_SECOND
    out = []
    for cycle in range(math.ceil((ha-hmax)/360), math.floor((stop+hmax)/360)+1):
        a = max(0., (360*cycle-hmax-ha)/SIDEREAL_DEG_PER_SECOND)
        b = min(span, (360*cycle+hmax-ha)/SIDEREAL_DEG_PER_SECOND)-duration
        if b >= a:
            out.append((start+timedelta(seconds=a), start+timedelta(seconds=b)))
    return out


def goal_gain(science, required, request, science_priority, common):
    """Long-term preference prices science; task obligations keep their own reward."""
    return (science*science_priority+required+request)*common


class RequestPlan:
    # ponytail: enumerate <=8 groups, greedy target insertion; CP-SAT only if measured misses justify it.
    def __init__(self, planner):
        self.p = planner
        self.cache_key = None
        self.focus = set()
        self.diagnostics = {'replans':0, 'nodes':0, 'selected':[], 'advisory':True}

    def update(self, requests, now):
        p = self.p
        if DL_REQ:
            requests = [r for r in requests if float(r.get('completion_reward', 0)) > 0
                        and parse_utc(r['deadline_utc']) > now]
        signature = tuple((r.get('request_id'), r['deadline_utc'], r['minimum_completed'],
                           r.get('remaining_count'), r['completion_factor_threshold'], r['completion_reward'],
                           tuple(r['target_ids']), tuple(r.get('completed_target_ids',[]))) for r in requests)
        key = (int(now.timestamp()//3600), signature, tuple(sorted(p.notices)),
               p.weather.revision if p.weather is not None else 0)
        if key == self.cache_key:
            return self.focus
        self.cache_key = key
        started = time.process_time()
        cpu_limit = GROUP_CPU_FAST if getattr(p,'fast_level',0) >= 2 else GROUP_CPU_FULL
        horizon = min(p.survey_end, now+timedelta(days=GROUP_HORIZON))
        windows = {}
        groups = []
        examined = 0
        for r in requests:
            remaining = int(r.get('remaining_count', r['minimum_completed']))
            deadline = min(parse_utc(r['deadline_utc']), horizon)
            if remaining <= 0 or deadline <= now:
                continue
            jobs = []
            completed = set(r.get('completed_target_ids',[]))
            for tid in dict.fromkeys(r['target_ids']):
                if (examined >= (200 if FIXED_LEVEL >= 2 else 500)) if FIXED_LEVEL >= 0 else (time.process_time()-started >= cpu_limit):
                    break
                examined += 1
                i = p.index_of.get(tid)
                if i is None or tid in completed or p.hmax[i] <= 0:
                    continue
                # Advisory cost uses public transit geometry and learned sky scale.
                # It is not a proof of completion in future weather or of fibre feasibility.
                model = p.ideal_model[i]*max(.05,p.prior_scale)
                need = math.ceil(float(r['completion_factor_threshold'])*p.f0t0/(max(1e-9,p.flux[i]*model)))
                duration = max(p.min_exposure,need)
                if duration > p.max_exposure:
                    continue
                wkey = (i,duration,deadline)
                if wkey not in windows:
                    windows[wkey] = [window for start,end in p.nights if end>now and start<deadline
                        for window in start_windows(p.ra[i],p.hmax[i],max(now,start),min(deadline,end),p.lon,duration)]
                if windows[wkey]:
                    jobs.append((i,duration,windows[wkey]))
            if len(jobs) >= remaining:
                groups.append((deadline, str(r.get('request_id','')), float(r['completion_reward']), remaining, jobs))
        # Keep deadline-near groups first; truncation changes advice, never removes baseline rewards.
        groups.sort(key=lambda g:(g[0],-g[2],g[1]))
        truncated = max(0,len(groups)-8)
        groups = groups[:8]
        best = (0.,0.,(),set())
        nodes = 0
        for mask in range(1,1<<len(groups)):
            if FIXED_LEVEL < 0 and time.process_time()-started >= cpu_limit:
                break
            nodes += 1
            cursor = now
            chosen = set()
            reward = 0.
            ids = []
            valid = True
            for k,(_,rid,value,remaining,jobs) in enumerate(groups):
                if not mask & (1<<k):
                    continue
                used = set()
                for _ in range(remaining):
                    if FIXED_LEVEL < 0 and time.process_time()-started >= cpu_limit:
                        valid = False
                        break
                    options = []
                    for i,duration,ws in jobs:
                        if i in used:
                            continue
                        for a,b in ws:
                            t = max(cursor,a)
                            if t <= b:
                                options.append((t+timedelta(seconds=duration),i))
                                break
                    if not options:
                        valid = False
                        break
                    cursor,i = min(options)
                    used.add(i)
                if not valid:
                    break
                chosen.update(used)
                ids.append(rid)
                reward += value
            if valid:
                candidate = (reward,-(cursor-now).total_seconds(),tuple(ids),chosen)
                if candidate[:3] > best[:3]:
                    best = candidate
        self.focus = best[3]
        cpu = time.process_time()-started
        self.diagnostics = {'replans':self.diagnostics['replans']+1,'nodes':nodes,
                            'selected':list(best[2]),'focus_targets':len(self.focus),
                            'truncated_groups':truncated,'advisory':True,'cpu_seconds':cpu,
                            'budget_limited':cpu>=cpu_limit,'cpu_limit':cpu_limit,
                            'horizon_days':GROUP_HORIZON,'focus_boost':GROUP_BOOST}
        return self.focus
