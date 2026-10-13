from pathlib import Path
p=Path('work/gosim-desi-v300/agent/planner.py')
s=p.read_text()
def rep(a,b):
 global s
 assert a in s, a[:120]
 s=s.replace(a,b)
rep('import os\n','import os\nfrom functools import lru_cache\nfrom opportunities import Opportunities, request_gain\n')
rep('ALT_MARGIN_DEG = 0.6', 'ALT_MARGIN_DEG = _env("ALT_MARGIN_DEG", 0.0)')
rep('        self.lunar_model = score["lunar_model"]','''        self.lunar_model = score["lunar_model"]
        self.required_threshold = float(score["required"]["observed_factor_threshold"])
        self.required_value = float(score["required"]["penalty_per_missing"]) * REQUIRED_BONUS / 50.0
        self.request_legs = {}
        self.history = []
        self.invalidated = set()
        self.raw_upper = []''')
rep('        self.factor = [0.0] * len(rows)', '        self.raw_upper = [0.0] * len(rows)\n        self.factor = [0.0] * len(rows)')
rep('        self._build_required_calendar()','        self._build_required_calendar()\n        self.opportunities = Opportunities(self)')
rep('        need = 20 * 60 * SIDEREAL_DEG_PER_SECOND','        need = self.min_exposure * SIDEREAL_DEG_PER_SECOND')
a=s.index('    def on_requests('); b=s.index('    def site_closed(',a)
s=s[:a]+'''    def on_requests(self, requests: list) -> None:
        old = self.request_bonus
        self.request_bonus, self.request_threshold, self.request_legs = {}, {}, {}
        active = set(self.active)
        for r in requests:
            remaining = int(r.get("remaining_count", r["minimum_completed"]))
            if remaining <= 0:
                continue
            completed = set(r.get("completed_target_ids", []))
            leg = {"start": parse_utc(r["issued_at_utc"]).timestamp(),
                   "end": parse_utc(r["deadline_utc"]).timestamp(),
                   "threshold": float(r["completion_factor_threshold"]),
                   "value": REQUEST_MULT * float(r["completion_reward"]) / remaining,
                   "request_id": r["request_id"]}
            members = [self.index_of[t] for t in r["target_ids"]
                       if t not in completed and t in self.index_of]
            if len(members) < remaining:
                continue  # an impossible all-or-nothing group has no reward
            for i in members:
                self.request_legs.setdefault(i, []).append(leg)
                self.request_bonus[i] = self.request_bonus.get(i, 0.0) + leg["value"]
                self.request_threshold[i] = min(self.request_threshold.get(i, 1.0), leg["threshold"])
                if self.hmax[i] > 0 and i not in active:
                    self.active.append(i)
                    active.add(i)
        self.vdirty.update(old)
        self.vdirty.update(self.request_bonus)

    def _resync(self, message: dict) -> None:
        window = message["invalidated_window"]
        self.invalidated.update(range(int(window["action_index_start"]),
                                      int(window["action_index_end_exclusive"])))
        self.factor = [0.0] * len(self.ids)
        self.raw_upper = [0.0] * len(self.ids)
        for action_index, rows in enumerate(self.history):
            if action_index in self.invalidated:
                continue
            for i, score, lower, upper in rows:
                self.factor[i] = max(self.factor[i], lower)
                self.raw_upper[i] = max(self.raw_upper[i], upper)
        best = {r["target_id"]: float(r["best_score"]) for r in message.get("best_scores", [])}
        self.cur = [best.get(t, 0.0) / self.weight[i] for i, t in enumerate(self.ids)]
        self.active = [i for i in range(len(self.ids)) if self.hmax[i] > 0.0]
        self.vcache = None
        self.log(f"state_resync: replayed {len(self.history)} observes; invalid {len(self.invalidated)}")

''' +s[b:]
rep('        hits = {hit["target_id"]', '        exposure_rows = []\n        hits = {hit["target_id"]')
rep('            self.factor[i] = max(self.factor[i], min(1.0, factor))','''            # Only score is public: matched/unsaturated can be ambiguous. Maintain
            # feasible raw bounds instead of certifying completion from a guess.
            feasible = [score / (self.weight[i] * m) for m in {declared, self.mismatch}
                        if score <= self.weight[i] * m + 2e-4]
            lower = min(1.0, min(feasible)) if feasible else min(1.0, factor)
            upper = min(1.0, max(feasible)) if feasible else min(1.0, factor)
            self.factor[i] = max(self.factor[i], lower)
            self.raw_upper[i] = max(self.raw_upper[i], upper)
            exposure_rows.append((i, score, lower, upper))''')
rep('        self._offset_evidence(hits)', '        self.history.append(exposure_rows)\n        self._offset_evidence(hits)')
# threshold gates only, not learned weather/program ratios or shape parameters
rep('self.factor[i] < 0.5', 'self.factor[i] < self.required_threshold')
rep('if f < 0.5 else 0.35', 'if f < self.required_threshold else 0.35')
rep('REQUIRED_BONUS * (1.0 if f', 'self.required_value * (1.0 if f')
rep(' / 0.5 * self.req_calib.get(i, 1.0)', ' / self.required_threshold * self.req_calib.get(i, 1.0)')
rep(' / self.f0t0 / 0.5', ' / self.f0t0 / self.required_threshold')
rep('bonus = REQUIRED_BONUS *', 'bonus = self.required_value *')
rep('g += REQUIRED_BONUS *', 'g += self.required_value *')
rep('        min_up = min(MIN_VISIBLE_SECONDS, seconds_left)', '        min_up = min(self.min_exposure, seconds_left)')
rep('        def gain(i, T):', '        @lru_cache(maxsize=None)\n        def gain(i, T):')
rep('''            if i in self.request_bonus:
                threshold = self.request_threshold.get(i, 0.5)
                raw = self.flux[i] * T * model * self.scale / self.f0t0 / max(1e-6, threshold)
                g += self.request_bonus[i] * min(1.0, max(0.0, (raw - REQ_P_LO) / (REQ_P_HI - REQ_P_LO)))''', '''            if i in self.request_legs:
                raw = self.flux[i] * T * model * scale / self.f0t0
                g += request_gain(self.request_legs[i], now.timestamp(), T, raw, self.opportunities, i)''')
rep('''            if i in self.request_bonus:
                raw = self.flux[i] * T * model * self.scale / self.f0t0 / max(1e-6, self.request_threshold.get(i, 0.5))
                g += self.request_bonus[i] * min(1.0, max(0.0, (raw - REQ_P_LO) / (REQ_P_HI - REQ_P_LO)))''', '''            if i in self.request_legs:
                raw = self.flux[i] * T * model * scale / self.f0t0
                g += request_gain(self.request_legs[i], now.timestamp(), T, raw, self.opportunities, i)''')
rep('T1 / 16.0, g2 - lam * T2 / 16.0', 'T1 / self.grid.n, g2 - lam * T2 / self.grid.n')
rep('''        fibers = (range(self.grid.n), range(self.grid.n), (5, 6, 9, 10), (5,))[min(level, 3)]''','''        middle = sorted(range(self.grid.n), key=lambda f: sum(x*x for x in self.grid.fiber_center(f)))
        dense_fibers = middle[:min(4, self.grid.n)]
        fibers = (range(self.grid.n), range(self.grid.n), dense_fibers, middle[:1])[min(level, 3)]''')
rep('NEIGHBOUR_RADIUS_DEG) if j in visible', 'max(NEIGHBOUR_RADIUS_DEG, self.grid.fov / math.sqrt(2) + self.grid.pitch)) if j in visible')
rep('else DENSE_FIBERS):', 'else dense_fibers):')
rep('''        if not durations:
            durations = [int(seconds_left)]''','''        durations = [T for T in durations if self.min_exposure <= T <= self.max_exposure]
        if not durations:
            durations = [int(min(seconds_left, self.max_exposure))]
        # Include request deadline and single-exposure threshold breakpoints; short
        # last windows must remain legal even under the cheapest search level.
        extra = {self.min_exposure}
        for i in pool[:min(40, len(pool))]:
            if not self.required[i] and i not in self.request_legs:
                continue
            alt, az, lunar, up, _ = base[i]
            model = lunar / (self.q0 * normalized_airmass(alt) ** self.airmass_exponent)
            rate = self.flux[i] * model * scale / self.f0t0
            thresholds = ([self.required_threshold] if self.required[i] else [])
            thresholds += [leg['threshold'] for leg in self.request_legs.get(i, [])]
            for threshold in thresholds:
                if rate > 0:
                    extra.add(math.ceil(threshold * 1.08 / rate))
            extra.add(int(up))
            for leg in self.request_legs.get(i, []):
                extra.add(int(leg['end'] - now.timestamp()))
        durations = sorted(set(durations) | {t for t in extra
                           if self.min_exposure <= t <= min(seconds_left, self.max_exposure)})''')
# End-of-season protection uses actual remaining usable windows rather than night labels.
rep('''                g += bonus
            if i in self.request_legs:''','''                needed = self.required_threshold * self.f0t0 / max(1e-8, self.flux[i] * model * scale)
                _, windows, _ = self.opportunities.remaining(i, now.timestamp(), duration=needed)
                if windows <= 1:
                    bonus *= 2.0
                g += bonus
            if i in self.request_legs:''')
p.write_text(s)
# Process the just-finished exposure before a state correction covering it.
p=Path('work/gosim-desi-v300/agent/agent.py');s=p.read_text()
s=s.replace('        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))', '        planner.on_result(payload.get("last_result"), now, hours)\n        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))')
s=s.replace('        planner.on_result(payload.get("last_result"), now, hours)\n        self._pace', '        self._pace')
p.write_text(s)
