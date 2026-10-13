"""Causal wall/CPU measurements and bounded waits, using public requests only."""
from collections import deque
from datetime import timedelta
import math
import statistics

from skymath import parse_utc
from switches import number, WAIT_H

ALPHA = number('EMA_ALPHA', .05, .001, 1.)
# Median full-turn wall delta of the completed r1 old-D rules run; online data takes over.
TURN_PRIOR = number('TURN_PRIOR', .172, .001, 60.)

class WallBudget:
    def __init__(self):
        self.previous = None
        self.action = 'wait'
        self.samples = deque(maxlen=500)
        self.points = deque(maxlen=500)
        self.ema = {}
        self.outside = None
        self.limit = None
        self.coefficients = (0.,0.)
        self.fit_night = None
        self.requests = {}
        self.bulletin = None
        self.bulletin_content = None
        self.stable_bulletins = 0
        self.bulletin_periods = deque(maxlen=32)
        self.rate_marks = deque(maxlen=256)
        self.request_nights = {}
        self.turns = 0
        self.exposures = 0
        self.pressure = False
        self.escalation = 0
        self.predicted_turn = 0.
        self.lambda_wall = 0.

    def update(self, payload, now, night):
        w = payload.get('wallclock') or {}
        remaining = w.get('wall_remaining_seconds')
        if remaining is not None and math.isfinite(float(remaining)):
            remaining = max(0.,float(remaining))
            if self.limit is None:
                self.limit = remaining + max(0.,float(w.get('wall_elapsed_seconds',0.)))
            cpu, wait = float(w.get('cpu_seconds',0.)), float(w.get('wait_seconds',0.))
            if self.previous is not None:
                prev, pcpu, pwait, x = self.previous
                cost = prev - remaining
                if 0. < cost < max(1.,self.limit):
                    self.samples.append(cost)
                    self.ema[self.action] = self.blend(self.ema.get(self.action),cost)
                    # Delta counters account for the last completed decision; no model double charge.
                    outside = max(0.,cost-max(0.,cpu-pcpu)-max(0.,wait-pwait))
                    self.outside = self.blend(self.outside,outside)
                    self.points.append((x,cost))
            self.exposures = int(payload.get('observe_action_index',self.exposures))
            for r in payload.get('active_requests',[]):
                self._request(r,night)
            for message in payload.get('new_messages',[]):
                if message.get('record_type') == 'observation_request':
                    self._request(message,night)
            # Every issued request becomes active or expired; retain IDs, never private truth.
            x = self.exposures*(1+len(self.requests))
            self.previous = remaining,cpu,wait,x
        b = payload.get('latest_bulletin') or {}
        stamp = b.get('issued_at_utc')
        if stamp:
            current = parse_utc(stamp)
            if self.bulletin is None or current > self.bulletin:
                content=tuple(sorted((n.get('event_kind',''),n.get('direction','')) for n in b.get('notices',[])))
                self.stable_bulletins=self.stable_bulletins+1 if content==self.bulletin_content else 1
                self.bulletin_content=content
                if self.bulletin is not None:
                    delta = (current-self.bulletin).total_seconds()
                    if 0 < delta <= 12*3600:
                        self.bulletin_periods.append(delta)
                self.bulletin = current
        if night != self.fit_night:
            self.fit_night = night
            self.fit()
        self.turns += 1

    @staticmethod
    def blend(previous, value):
        return value if previous is None else (1-ALPHA)*previous+ALPHA*value

    def _request(self,r,night):
        key = r.get('request_id')
        if key is not None and key not in self.requests:
            self.requests[key] = r.get('deadline_utc')
            self.request_nights[night] = self.request_nights.get(night,0)+1

    @property
    def reserve(self):
        if len(self.samples) < 50:
            return 90.
        values = sorted(self.samples)
        return 60.+30*values[min(len(values)-1,math.ceil(.99*len(values))-1)]

    def fit(self):
        if len(self.points) < 20:
            return
        mx = statistics.fmean(p[0] for p in self.points)
        my = statistics.fmean(p[1] for p in self.points)
        xx = sum((x-mx)**2 for x,y in self.points)
        slope = max(0.,sum((x-mx)*(y-my) for x,y in self.points)/xx) if xx else 0.
        self.coefficients = max(0.,my-slope*mx),slope

    def predict(self, decisions_left):
        a,b = self.coefficients
        x_mid = (self.exposures+.5*decisions_left)*(1+len(self.requests))
        measured = self.ema.get('observe', statistics.fmean(self.samples) if self.samples else TURN_PRIOR)
        if len(self.samples) < 50:
            measured = max(TURN_PRIOR, measured)
        self.predicted_turn = max(.001,measured,a+b*x_mid)
        return self.predicted_turn

    def turns_per_decision(self, elapsed, observes):
        if not self.rate_marks or elapsed-self.rate_marks[-1][0] >= 4*3600:
            self.rate_marks.append((elapsed,observes,self.turns))
        while len(self.rate_marks)>1 and self.rate_marks[1][0] <= elapsed-120*3600:
            self.rate_marks.popleft()
        _,old_obs,old_turns = self.rate_marks[0]
        return max(1.,(self.turns-old_turns)/max(1,observes-old_obs)) if observes-old_obs>=10 else max(1.,self.turns/max(1,observes))

    def wait_until(self, now, night_end, slot, requests, next_up=None, flat_end=None, skip_bulletins=False):
        targets = [night_end]
        if next_up is not None and next_up > 0:
            targets.append(now+timedelta(seconds=max(60.,next_up)))
        if flat_end is not None and flat_end>now:
            targets.append(flat_end)
        # Never assume wait_until will be interrupted by an unseen request.
        paid = any(float(r.get('completion_reward',0))>0 and parse_utc(r['deadline_utc'])>now for r in requests)
        rates = list(self.request_nights.values())
        high_rate = len(rates)>=3 and statistics.fmean(rates[-3:])>statistics.median(rates)
        if paid or high_rate or skip_bulletins:
            targets.append(now+timedelta(hours=min(WAIT_H,2.5) if skip_bulletins else WAIT_H))
        period = statistics.median(self.bulletin_periods) if self.bulletin_periods else slot
        nxt = (self.bulletin+timedelta(seconds=period)) if self.bulletin else now+timedelta(seconds=slot)
        if nxt<=now:
            nxt=now+timedelta(seconds=period)
        if not skip_bulletins or paid or self.stable_bulletins<2:
            targets.append(nxt)
        for r in requests:
            for key in ('available_from_utc','start_utc'):
                if r.get(key):
                    t=parse_utc(r[key])
                    if t>now: targets.append(t)
        return max(now+timedelta(seconds=1),min(targets))
