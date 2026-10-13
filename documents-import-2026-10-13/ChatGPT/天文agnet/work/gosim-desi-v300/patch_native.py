from pathlib import Path
p=Path('work/gosim-desi-v300/agent/skymath.py');s=p.read_text()
s=s.replace('        self.fov = float(instrument["fov_side_deg"])','        self.fov = float(instrument["fov_side_deg"])\n        self.gap = float(instrument.get("gap_deg", self.pitch - self.glass))\n        if self.n != self.side * self.side:\n            raise ValueError("n_fibers must equal grid_side squared")')
s=s.replace('        return (fiber, margin) if margin >= 0.0 else (None, margin)','        if self.gap == 0.0:\n            return fiber, max(0.0, margin)\n        return (fiber, margin) if margin >= 0.0 else (None, margin)')
p.write_text(s)
p=Path('work/gosim-desi-v300/agent/planner.py');s=p.read_text()
s=s.replace('import os\n','import os\nimport time\nfrom native import LIB, FieldBatch\nfrom geometry_feedback import GeometryFeedback\n')
s=s.replace('        self.grid = FiberGrid(instrument)','        self.grid = FiberGrid(instrument)\n        self.geometry = GeometryFeedback(self.grid, enabled=os.environ.get("OBSERVER_GEOMETRY", "1") == "1")\n        self.cpu_turn_budget = 1.0')
a=s.index('    def _offset_evidence(');b=s.index('    def calibrated_band_scale(',a)
s=s[:a]+'''    def _offset_evidence(self, hits: dict) -> None:
        # Future exposures validate a trained proposal before it alters commands.
        evidence = {}
        if self.pending_cmd is None:
            return
        for target, pred in self.pending.items():
            evidence[target] = {**pred, "geometry": {"altitude_feasible": True,
                "fiber": pred["fiber"], "command_alt": self.pending_cmd[0], "command_az": self.pending_cmd[1]}}
        summary = self.geometry.record(evidence, hits)
        if summary and any(k in summary for k in ('proposal', 'calibration_update', 'calibration_rollback', 'calibration_rejected')):
            self.log('geometry: ' + str(summary))
        self.offset = self.geometry.offset

''' +s[b:]
s=s.replace('        f = self.factor[i]','        f = self.factor[i]')
s=s.replace('if f >= REQUIRED_SAFE_FACTOR:', 'if f >= min(1.0, self.required_threshold * 1.24):')
s=s.replace('        if PARTIAL_DISCOUNT < 1.0 and night_index != self.plan_night:', '        cpu_started = time.process_time()\n        if PARTIAL_DISCOUNT < 1.0 and night_index != self.plan_night:')
s=s.replace('def gain(i, T):','def gain(i, T, program):')
s=s.replace('            m = self.multipliers[self._band(model * band_scale)]','            m = self.multipliers[program] if self._band(model * band_scale) == program else self.mismatch')
s=s.replace('max(NEIGHBOUR_RADIUS_DEG, self.grid.fov / math.sqrt(2) + self.grid.pitch)', 'max(NEIGHBOUR_RADIUS_DEG, math.sqrt(2) * self.grid.fov + REFINE * REFINE_ROUNDS)')
s=s.replace('self.min_alt <= c_alt <= 89.0', '0.0 <= c_alt <= 90.0')
a=s.index('        def evaluate(c_alt, c_az, near, durations):');b=s.index('        best_near = None',a)
s=s[:a]+'''        batches = {}
        def evaluate(c_alt, c_az, near, durations):
            choices = [(t, p) for t in durations for p in ("DARK", "BRIGHT", "BACKUP")]
            if LIB is not None:
                key = (tuple(near), tuple(durations))
                batch = batches.get(key)
                if batch is None:
                    batch = batches[key] = FieldBatch(self.grid, near, base, self.misses, choices, gain, EDGE_MARGIN_DEG)
                trials = batch.evaluate(c_alt, c_az)
            else:
                cells = {}
                for j in near:
                    offsets = tangent_offsets(base[j][0], base[j][1], c_alt, c_az)
                    if offsets is None:
                        continue
                    fib, margin = self.grid.classify(*offsets)
                    if fib is None or margin < EDGE_MARGIN_DEG * (0.5 + 1.5 * self.misses[j]):
                        continue
                    cells.setdefault(fib, []).append(j)
                trials = []
                for T, program in choices:
                    total, pick = 0.0, {}
                    for fib, js in cells.items():
                        g, j = max((gain(j,T,program),j) for j in js)
                        if g > 0:
                            total += g; pick[fib] = j
                    trials.append((T,program,pick,total))
            found = None
            for T, program, pick, total in trials:
                if not pick:
                    continue
                best_rate[0] = max(best_rate[0],total/T)
                net = total-lam*T
                if found is None or net > found[0]:
                    found = (net,T,pick,total,program)
            return found

''' +s[b:]
s=s.replace('        for rank, anchor in enumerate(anchors):', '        for rank, anchor in enumerate(anchors):\n            if best is not None and time.process_time() - cpu_started >= self.cpu_turn_budget:\n                break')
s=s.replace('            # density anchors mark a patch,', '            near.sort()\n            # density anchors mark a patch,')
s=s.replace('            for fiber in (fibers if rank < n_value_anchors else dense_fibers):', '            for fiber in (fibers if rank < n_value_anchors else dense_fibers):\n                if best is not None and time.process_time() - cpu_started >= self.cpu_turn_budget:\n                    break')
s=s.replace('best = (found[0], c_alt, c_az, found[1], found[2], found[3])','best = (found[0], c_alt, c_az, found[1], found[2], found[3], found[4])')
s=s.replace('            for _ in range(REFINE_ROUNDS):','            for _ in range(REFINE_ROUNDS):\n                if time.process_time() - cpu_started >= self.cpu_turn_budget:\n                    break')
a=s.index('        _, c_alt, c_az, T, pick, _ = best');b=s.index('        clean = not self.all_sky_notice()',a)
s=s[:a]+'        _, c_alt, c_az, T, pick, _, program = best\n'+s[b:]
s=s.replace('        clean = not self.all_sky_notice()', '''        self.last_plan = {"gain": best[5], "cpu_seconds": time.process_time()-cpu_started,
                          "native": LIB is not None, "evaluated_batches": len(batches),
                          "required_at_risk": [self.ids[j] for j in pick if False]}
        clean = not self.all_sky_notice()''')
s=s.replace('"required_at_risk": [self.ids[j] for j in pick if False]', '"assigned": len(pick)')
p.write_text(s)
p=Path('work/gosim-desi-v300/agent/agent.py');s=p.read_text()
s=s.replace('        # estimates of levels not used', '''        # A dense urgent turn may spend more CPU; the remaining-turn reserve stays
        # in charge. Native work is in this process and included in process_time.
        urgent = bool(self.planner.request_legs)
        self.planner.cpu_turn_budget = max(0.003, min(max(0.003, cpu_left * .02),
            (cpu_budget if fair else wall_budget) * (1.4 if urgent else 1.0)))
        # estimates of levels not used''')
p.write_text(s)
p=Path('work/gosim-desi-v300/agent/pack_agent.py');s=p.read_text().replace('{".pyc", ".pyo", ".zip"}', '{".pyc", ".pyo", ".zip", ".so", ".dylib", ".dll", ".o"}');p.write_text(s)
p=Path('work/gosim-desi-v300/agent/observer.project.json'); import json
m=json.loads(p.read_text());m['image']='python:3.12-bookworm';m['build']=[['python3','build_native.py']];p.write_text(json.dumps(m,indent=2)+'\n')
