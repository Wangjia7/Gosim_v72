from pathlib import Path
p=Path('outputs/python-pro-v2/planner.py'); s=p.read_text()
s=s.replace('import os\n','import os\nimport time\n')
s=s.replace('DENSE_FIBERS = (5, 6, 9, 10)','DURATION_LEADERS = _env("DURATION_LEADERS", 3)\nBREAKPOINT_TARGETS = _env("BREAKPOINT_TARGETS", 24)')
s=s.replace('        self.q0 = float(score["q0"])','        self.required_threshold = float(score["required"]["observed_factor_threshold"])\n        self.factor_history = {}  # observe_index -> [(target index, estimated factor)]\n        self.cpu_deadline = float("inf")\n        self.wall_deadline = float("inf")\n        self.last_plan = {}\n        self.q0 = float(score["q0"])')
s=s.replace('        self.request_threshold: dict[int, float] = {}','        self.request_threshold: dict[int, float] = {}\n        self.request_terms = {}')
s=s.replace('        self.request_threshold = {}\n        for request', '        self.request_threshold = {}\n        self.request_terms = {}\n        for request')
s=s.replace('                # Overlapping requests:', '                self.request_terms.setdefault(i, []).append((\n                    parse_utc(request["issued_at_utc"]), parse_utc(request["deadline_utc"]), threshold, unit))\n                # Overlapping requests:')
a=s.index('        """Part of the recent data was lost:'); b=s.index('    def site_closed',a)
s=s[:a]+'''        """Scores and required completion are distinct: replay only surviving local factors."""
        best = {row["target_id"]: float(row["best_score"]) for row in message.get("best_scores", [])}
        window = message.get("invalidated_window", {})
        first, end = window.get("action_index_start"), window.get("action_index_end_exclusive")
        if first is None or end is None:
            self.factor_history.clear()  # unknown validity: do not claim required completion
        else:
            for index in list(self.factor_history):
                if first <= index < end:
                    del self.factor_history[index]
        self.factor = [0.0] * len(self.ids)
        for rows in self.factor_history.values():
            for i, factor in rows:
                self.factor[i] = max(self.factor[i], factor)
        self.cur = [best.get(target_id, 0.0) / self.weight[i] for i, target_id in enumerate(self.ids)]
        self.active = [i for i in range(len(self.ids)) if self.hmax[i] > 0.0]
        self.attempts = [0] * len(self.ids)
        self.req_calib.clear()
        self.vcache = None
        self.pending = {}
        self.log(f"state_resync: {len(best)} official scores; surviving local factor history replayed")

    def budget_expired(self):
        return time.process_time() >= self.cpu_deadline or time.monotonic() >= self.wall_deadline

    def request_gain(self, i, now, duration, factor):
        """Each overlapping request retains its own threshold and whole-exposure window."""
        end = now + timedelta(seconds=duration)
        return sum(unit * min(1.0, max(0.0, (factor / max(1e-6, threshold) - REQ_P_LO)
                                                     / (REQ_P_HI - REQ_P_LO)))
                   for start, deadline, threshold, unit in self.request_terms.get(i, ())
                   if start <= now and end <= deadline)

''' +s[b:]
s=s.replace('        declared = self.multipliers[self.pending_program]','        observed_factors = []\n        declared = self.multipliers[self.pending_program]')
s=s.replace('            self.factor[i] = max(self.factor[i], min(1.0, factor))','            observed_factors.append((i, min(1.0, factor)))\n            self.factor[i] = max(self.factor[i], min(1.0, factor))')
s=s.replace('        self._offset_evidence(hits)','        if "observe_index" in result:\n            self.factor_history[int(result["observe_index"])] = observed_factors\n        if not self.budget_expired():\n            self._offset_evidence(hits)')
s=s.replace('self.factor[i] < 0.5','self.factor[i] < self.required_threshold').replace('f < 0.5','f < self.required_threshold')
s=s.replace(' / self.f0t0 / 0.5',' / self.f0t0 / self.required_threshold')
# Conservative spherical cap: works at poles and wrapping RA as well.
a=s.index('        cos_dec = max(0.05,'); b=s.index('        for key in range',a)
s=s[:a]+'''        polar = abs(dec) + radius >= 90.0
        width = 180.0 if polar else math.degrees(math.asin(min(1.0, math.sin(math.radians(radius))
                                                                     / math.cos(math.radians(dec)))))
'''+s[b:]
s=s.replace('            spans = [(ra - width, ra + width)]','            if width >= 180.0:\n                found.extend(i for _, i in band)\n                continue\n            spans = [(ra - width, ra + width)]')
s=s.replace('        min_up = min(MIN_VISIBLE_SECONDS, seconds_left)','        min_up = min(self.min_exposure, seconds_left)')
s=s.replace('        lst_later = lst + 1800.0 * SIDEREAL_DEG_PER_SECOND\n        moon = Moon(now + timedelta(seconds=600), lst, self.lat, self.lunar_model)', '''        quality_horizon = float(self.max_exposure)
        lst_later = lst + quality_horizon * 0.5 * SIDEREAL_DEG_PER_SECOND
        moon = Moon(now, lst, self.lat, self.lunar_model)
        moon_mid = Moon(now + timedelta(seconds=quality_horizon / 2), lst_later, self.lat, self.lunar_model)
        lst_end = lst + quality_horizon * SIDEREAL_DEG_PER_SECOND
        moon_end = Moon(now + timedelta(seconds=quality_horizon), lst_end, self.lat, self.lunar_model)''')
s=s.replace('                m1 = lunar / (self.q0 * normalized_airmass(max(alt2, 1.0)) ** self.airmass_exponent)\n                item = info[i] = (alt, az, m0, m1, up, mult)', '''                m1 = moon_mid.lunar_factor(self.ra[i], self.dec[i]) / (self.q0 * normalized_airmass(max(alt2, 1.0)) ** self.airmass_exponent)
                alt3, _ = radec_to_altaz(self.ra[i], self.dec[i], lst_end, self.lat)
                m2 = moon_end.lunar_factor(self.ra[i], self.dec[i]) / (self.q0 * normalized_airmass(max(alt3, 1.0)) ** self.airmass_exponent)
                # Integral of the quadratic through start/mid/end, divided by duration.
                curve[i] = (m0, (-3*m0 + 4*m1 - m2) / 2, (2*m0 - 4*m1 + 2*m2) / 3)
                item = info[i] = (alt, az, m0, m1, up, mult)''')
s=s.replace('        info = {}','        info = {}\n        curve = {}\n\n        def exposure_model(i, T):\n            full(i)\n            a, b, c = curve[i]\n            x = T / quality_horizon\n            return max(0.0, a + b*x + c*x*x)')
s=s.replace('            model = m0 + (m1 - m0) * min(1.0, T / 3600.0)','            model = exposure_model(i, T)',1)
a=s.index('            if i in self.request_bonus:',s.index('        def gain')); b=s.index('            return g * mult',a)
s=s[:a]+'''            g += self.request_gain(i, now, T, self.flux[i] * T * model * self.scale / self.f0t0)
'''+s[b:]
a=s.index('            if i in self.request_bonus:',s.index('        def quick')); b=s.index('            return g * mult, T',a)
s=s[:a]+'''            g += self.request_gain(i, now, T, self.flux[i] * T * model * self.scale / self.f0t0)
'''+s[b:]
a=s.index('        durations = [T for T in LEVEL_DURATIONS');b=s.index('        t_long = ',a)
s=s[:a]+'''        limit = int(min(seconds_left, self.max_exposure))
        lower = min(limit, max(self.min_exposure, MIN_T))
        durations = sorted({lower, limit} | {T for T in LEVEL_DURATIONS[min(level, 3)] if lower <= T <= limit})
'''+s[b:]
s=s.replace('/ 16.0','/ self.grid.n')
s=s.replace('        fibers = (range(self.grid.n), range(self.grid.n), (5, 6, 9, 10), (5,))[min(level, 3)]', '''        central = self.grid.central_fibers
        fibers = (range(self.grid.n), range(self.grid.n), central, central[:1])[min(level, 3)]''')
s=s.replace('else DENSE_FIBERS','else central')
s=s.replace('        def evaluate(c_alt, c_az, near, durations):','''        gain_cache = {}
        def cached_gain(j, T):
            key = (j, T)
            if key not in gain_cache:
                gain_cache[key] = gain(j, T)
            return gain_cache[key]

        def breakpoints(js):
            from exposure import duration_candidates
            points = set(durations)
            for j in sorted(js, key=lambda j: vc[j], reverse=True)[:BREAKPOINT_TARGETS]:
                full(j)
                upper = min(limit, info[j][4])
                thresholds = [1.0 / PLAN_FACTOR_SAFETY, self.cur[j] / max(self.multipliers.values()) / PLAN_FACTOR_SAFETY]
                if self.required[j] and self.factor[j] < self.required_threshold:
                    thresholds += [self.required_threshold * x / self.req_calib.get(j, 1.0) for x in (REQ_P_LO, 1.0, REQ_P_HI)]
                endpoints = [upper]
                for start, deadline, threshold, _ in self.request_terms.get(j, ()):
                    if start <= now:
                        endpoints.append((deadline - now).total_seconds())
                        thresholds += [threshold*x for x in (REQ_P_LO, 1.0, REQ_P_HI)]
                points.update(duration_candidates(lower, upper, thresholds,
                              lambda T: self.flux[j]*T*exposure_model(j, T)*self.scale/self.f0t0, endpoints))
                # Band transitions also change the declared program's return.
                points.update(duration_candidates(lower, upper, list(map(float, self.bands.values())),
                              lambda T: exposure_model(j, T)*band_scale, []))
                if self.budget_expired():
                    break
            return sorted(T for T in points if lower <= T <= limit)

        def evaluate(c_alt, c_az, near, durations, refine_duration=False):''')
s=s.replace('            found = None\n            for T in durations:', '''            found = None
            if refine_duration:
                durations = breakpoints({j for js in cells.values() for j in js})
            for T in durations:''')
s=s.replace('max((gain(j, T), j) for j in js)','max((cached_gain(j, T), j) for j in js)')
s=s.replace('            return found\n\n        best_near', '                if found is not None and self.budget_expired():\n                    break\n            return found\n\n        best_near')
s=s.replace('        n_value_anchors =','        leaders = []\n        n_value_anchors =')
s=s.replace('NEIGHBOUR_RADIUS_DEG) if j in visible','max(NEIGHBOUR_RADIUS_DEG, self.grid.neighbour_radius + REFINE_ROUNDS * REFINE * 1.5)) if j in visible')
s=s.replace('                if found is not None and (best is None or found[0] > best[0]):','''                if found is not None:
                    leaders.append((found[0], c_alt, c_az, near))
                if found is not None and (best is None or found[0] > best[0]):''')
s=s.replace('                    best_near = near\n        if best', '''                    best_near = near
                if best is not None and self.budget_expired():
                    break
            if best is not None and self.budget_expired():
                break
        # Spend the remaining budget on discontinuities and local duration refinement of leading fields.
        for _, c_alt, c_az, near in sorted(leaders, key=lambda x: -x[0])[:max(1, DURATION_LEADERS // (level + 1))]:
            if self.budget_expired():
                break
            found = evaluate(c_alt, c_az, near, durations, True)
            if found is not None:
                for step in (60, 15, 3, 1):
                    if self.budget_expired():
                        break
                    local = sorted({max(lower, min(limit, found[1] + d*step)) for d in (-2, -1, 0, 1, 2)})
                    trial = evaluate(c_alt, c_az, near, local)
                    if trial and trial[0] > found[0]:
                        found = trial
                if best is None or found[0] > best[0]:
                    best = (found[0], c_alt, c_az, found[1], found[2], found[3])
                    best_near = near
        if best''')
s=s.replace('            for _ in range(REFINE_ROUNDS):\n                improved', '            for _ in range(REFINE_ROUNDS):\n                if self.budget_expired():\n                    break\n                improved')
s=s.replace('            model = m0 + (m1 - m0) * min(1.0, T / 3600.0)','            model = exposure_model(j, T)')
s=s.replace('        clean = not self.all_sky_notice()', '''        self.last_plan = {"predicted_gain": round(best[5], 6), "net_gain": round(best[0], 6),
                          "search_level": level, "candidate_fields": len(leaders), "quality_scale": self.scale,
                          "offset_deg": self.offset, "duration_seconds": T, "budget_exhausted": self.budget_expired()}
        clean = not self.all_sky_notice()''')
p.write_text(s)
p=Path('outputs/python-pro-v2/skymath.py'); s=p.read_text(); s=s.replace('        self.fov = float(instrument["fov_side_deg"])','''        self.fov = float(instrument["fov_side_deg"])
        if self.side <= 0 or self.n != self.side ** 2:
            raise ValueError("instrument must have grid_side squared fibres")
        self.central_fibers = tuple(sorted(range(self.n), key=lambda f: (sum(x*x for x in self.fiber_center(f)), f))[:min(4, self.n)])
        # Anchor may lie at any fibre centre; include the opposite field corner.
        centre_radius = max(math.hypot(*self.fiber_center(f)) for f in range(self.n))
        self.neighbour_radius = math.degrees(math.atan(math.radians(centre_radius))) + math.degrees(math.atan(math.radians(math.sqrt(2)*self.fov/2))) + 0.01''');p.write_text(s)
