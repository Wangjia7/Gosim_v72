from pathlib import Path
p=Path('outputs/python-pro-v2/planner.py');s=p.read_text()
s=s.replace('        self.offset_scores = None','        self.offset_scores = None\n        self._offset_scan = None',1)
s=s.replace('        need = 20 * 60 * SIDEREAL_DEG_PER_SECOND','        need = self.min_exposure * SIDEREAL_DEG_PER_SECOND')
s=s.replace('"""First and last night on which each target has at least 20 minutes above the limit."""','"""First and last night with enough time for one legal exposure above the limit."""')
s=s.replace('        if not self.budget_expired():\n            self._offset_evidence(hits)', '''        if not self.budget_expired():
            deadline = self.cpu_deadline
            remaining = deadline - time.process_time()
            self.cpu_deadline = time.process_time() + remaining * 0.2
            try:
                self._offset_evidence(hits)
            finally:
                self.cpu_deadline = deadline''')
a=s.index('        if self.offset_scores is None or self.offset_updates');b=s.index('    def _consistent',a)
s=s[:a]+'''        self.offset_updates += 1
        if self.offset_scores is None or self._offset_scan is not None or self.offset_updates % OFFSET_REFINE_EVERY == 1:
            if self._rescore_offsets(list(self.offset_evidence)[-OFFSET_FINE_EVIDENCE:]):
                # The completed coarse scan is already usable; optional fine work may run out of budget.
                evidence = self._offset_scored_evidence
                k = max(range(len(self.offset_grid)), key=lambda n: self.offset_scores[n])
                candidate = self.offset_grid[k]
                zero = sum(self._consistent(cmd, rows, 0, 0) for cmd, rows in evidence)
                if self.offset_scores[k] - zero >= OFFSET_MARGIN:
                    if self.offset == (0.0, 0.0):
                        self.misses = [0] * len(self.ids)
                        self.vcache = None
                    self.offset = candidate
                if not self.budget_expired():
                    self._refine_offset()

'''+s[b:]
a=s.index('        old = self.offset_scores',s.index('    def _rescore_offsets'));b=s.index('    def _refine_offset',a)
s=s[:a]+'''        # Freeze evidence for one generation and resume the exact candidate cursor next turn.
        # Never publish a partly scored grid or restart it just because the slice ended.
        if self._offset_scan is None or self._offset_scan[0] != len(self.offset_grid):
            self._offset_scan = [len(self.offset_grid), list(evidence), [0]*len(self.offset_grid), 0]
        scan = self._offset_scan
        while scan[3] < len(self.offset_grid):
            if self.budget_expired():
                return False
            k = scan[3]
            d_alt, d_az = self.offset_grid[k]
            scan[2][k] = sum(self._consistent(cmd, rows, d_alt, d_az) for cmd, rows in scan[1])
            scan[3] += 1
        self.offset_scores = scan[2]
        self._offset_scored_evidence = scan[1]
        self._offset_scan = None
        return True

'''+s[b:]
s=s.replace('            self._rescore_offsets(list(self.offset_evidence)[-100:])\n            if self.offset_scores is None:', '            if not self._rescore_offsets(list(self.offset_evidence)[-100:]):')
# Coarse all-target deadline coverage prevents request-only targets vanishing before refinement.
s=s.replace('        t_long = durations[-1]', '''        for terms in self.request_terms.values():
            for start, deadline, _, _ in terms:
                boundary = int((deadline - now).total_seconds())
                if start <= now and lower <= boundary <= limit:
                    durations.append(boundary)
        durations = sorted(set(durations))
        t_long = durations[-1]''')
s=s.replace('            best_net = max(g1 - lam * T1 / self.grid.n, g2 - lam * T2 / self.grid.n)', '''            best_net = max(g1 - lam * T1 / self.grid.n, g2 - lam * T2 / self.grid.n)
            for start, deadline, _, _ in self.request_terms.get(i, ()):
                if start <= now:
                    endpoint = min(t_long, (deadline - now).total_seconds())
                    if endpoint >= lower:
                        g3, T3 = quick(i, endpoint)
                        best_net = max(best_net, g3 - lam*T3/self.grid.n)''')
s=s.replace('        fibers = (range(self.grid.n), range(self.grid.n), central, central[:1])[min(level, 3)]','        all_fibers = tuple(central) + tuple(f for f in range(self.grid.n) if f not in central)\n        fibers = (all_fibers, all_fibers, central, central[:1])[min(level, 3)]')
s=s.replace('            for T in durations:\n                total', '''            # A usable representative exposure comes first if the turn budget is already exhausted.
            for T in sorted(durations, key=lambda t: (abs(t - min(limit, 900)), t)):
                total''')
p.write_text(s)
# Independent self CPU telemetry complements the runner's external meter.
p=Path('outputs/python-pro-v2/agent.py');s=p.read_text();s=s.replace('        self.turn_sequence = 0','        self.turn_cpu = 0.0\n        self.turn_sequence = 0');s=s.replace('        cpu = time.process_time() - cpu_started','        cpu = time.process_time() - cpu_started\n        self.turn_cpu += cpu');s=s.replace("f\"observes={agent.observes if agent else 0} reports={agent.reports if agent else 0}\")","f\"observes={agent.observes if agent else 0} reports={agent.reports if agent else 0} \"\n                f\"self_turn_cpu_seconds={agent.turn_cpu if agent else 0:.6f}\")");p.write_text(s)
