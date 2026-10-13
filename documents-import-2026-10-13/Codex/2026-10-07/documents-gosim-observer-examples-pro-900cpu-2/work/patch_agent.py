from pathlib import Path
p=Path('outputs/python-pro-v2/agent.py');s=p.read_text()
s=s.replace('from advisor import Advisor','from advisor import Advisor\nfrom review import StepReviewer')
s=s.replace('        self.advisor = RulesOnly() if rules_only else Advisor(self.client, log=log)','        self.advisor = RulesOnly() if rules_only else Advisor(self.client, log=log)\n        self.reviewer = StepReviewer(self.client, log=log)\n        self.turn_sequence = 0\n        self.previous_action = None')
s=s.replace('        level = self.planner.fast_level\n        action = self._respond(payload)', '''        cpu_left, wall_left, fair = self._clock(payload)
        now = parse_utc(payload["now_utc"])
        remaining = self._decisions_left(now)
        allowance = max(0.005, PACE_SAFETY * max(0.0, cpu_left - 2.0) / remaining)
        self.planner.cpu_deadline = cpu_started + allowance if fair and FIXED_LEVEL < 0 else float("inf")
        self.planner.wall_deadline = started + max(0.005, PACE_SAFETY * max(0.0, wall_left - 2.0) / remaining) if FIXED_LEVEL < 0 else float("inf")
        self.turn_sequence += 1
        self.reviewer.poll(self.turn_sequence)
        action = self._respond(payload)
        level = self.planner.fast_level
        self.reviewer.record(self.turn_sequence, payload, self.previous_action, action,
                             self.planner.last_plan if action.get("action") == "observe" else {},
                             wall_left, cpu_left)
        self.previous_action = action''')
s=s.replace('        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))','        planner.on_result(payload.get("last_result"), now, hours)\n        planner.on_messages(payload.get("new_messages", []), payload.get("latest_bulletin"))')
s=s.replace('        planner.on_result(payload.get("last_result"), now, hours)\n        self._pace','        self._pace')
s=s.replace('self.wall_ema[self.planner.fast_level]','self.wall_ema[min(self.planner.fast_level, 3)]')
s=s.replace('        while level < 3 and (self.cost_ema[level] > cpu_budget or self.wall_ema[level] > wall_budget):','        while level < 3 and (self.cost_ema[level] > cpu_budget or self.wall_ema[level] > wall_budget):')
p.write_text(s)
p=Path('outputs/python-pro-v2/planner.py');s=p.read_text()
s=s.replace('if self.offset_scores is None:\n            self._rescore_offsets(list(self.offset_evidence))','if self.offset_scores is None or self.offset_updates % 40 == 0:\n            self._rescore_offsets(list(self.offset_evidence)[-OFFSET_FINE_EVIDENCE:])')
# Budget-safe offset rebuild must not publish incomplete scores.
s=s.replace('        self.offset_scores = [0] * len(self.offset_grid)\n        for cmd, past in evidence:\n            self._score_offsets(cmd, past)', '''        old = self.offset_scores
        scores = [0] * len(self.offset_grid)
        for k, (d_alt, d_az) in enumerate(self.offset_grid):
            if self.budget_expired():
                self.offset_scores = old if old is not None and len(old) == len(self.offset_grid) else None
                return
            scores[k] = sum(self._consistent(cmd, rows, d_alt, d_az) for cmd, rows in evidence)
        self.offset_scores = scores''')
s=s.replace('        self.offset_updates += 1\n        if self.offset_updates', '        if self.offset_scores is None or self.budget_expired():\n            return\n        self.offset_updates += 1\n        if self.offset_updates')
s=s.replace('        for k, (d_alt, d_az) in enumerate(self.offset_grid):\n            self.offset_scores[k] += self._consistent(cmd, rows, d_alt, d_az)', '''        additions = []
        for k, (d_alt, d_az) in enumerate(self.offset_grid):
            if self.budget_expired():
                self.offset_scores = None
                return
            additions.append(self._consistent(cmd, rows, d_alt, d_az))
        self.offset_scores = [a+b for a, b in zip(self.offset_scores, additions)]''')
s=s.replace('            self.log(f"pointing offset: search widened', '            if self.offset_scores is None:\n                return\n            self.log(f"pointing offset: search widened')
s=s.replace('            for j in range(-6, 7):\n                d_alt', '            for j in range(-6, 7):\n                if self.budget_expired():\n                    return\n                d_alt')
s=s.replace('        if abs(centre[0] - self.offset[0])', '''        if sum(self._consistent(cmd, rows, *centre) for cmd, rows in evidence) < top:
            centre = min(tied, key=lambda p: (p[0]-self.offset[0])**2 + (p[1]-self.offset[1])**2)
        if abs(centre[0] - self.offset[0])''')
s=s.replace('if not self.min_alt <= c_alt <= 89.0:', 'if not self.min_alt <= c_alt <= 89.0 or not 0.0 <= c_alt - self.offset[0] <= 90.0:')
p.write_text(s)
p=Path('outputs/python-pro-v2/AGENTS.md');s=p.read_text().replace('- Never call the model per decision. The night stages run in the background; `agent._model_wait_budget`\n  decides how long a night start may wait for them.', '- Per the v2 user requirement, every decision emits a review hook. Model review is asynchronous, bounded,\n  and advisory only; no model response may modify official target state or bypass planner constraints.\n  `agent._model_wait_budget` controls waits for the existing night stages.');p.write_text(s)
