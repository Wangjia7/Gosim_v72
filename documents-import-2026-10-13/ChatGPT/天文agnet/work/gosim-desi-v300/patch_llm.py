from pathlib import Path
p=Path('work/gosim-desi-v300/agent/agent.py');s=p.read_text()
s=s.replace('        self.planner = Planner(init, log=log)', '        self.planner = Planner(init, log=log)\n        self.preference_until = 0')
s=s.replace('        self._pace(payload, now)', '''        self._pace(payload, now)
        if not self.rules_only:
            self.advisor.ingest(payload, planner)
        if now.timestamp() > self.preference_until:
            planner.operator_priorities = set()''')
s=s.replace('        else:\n            self._apply_advice(*self.advisor.poll())', '''        else:
            self._apply_advice(*self.advisor.poll())
            # New operator text or a material cumulative residual can arrive mid-night.
            signature = (tuple(str(x) for x in self.advisor.texts), int(hours)) if not self.rules_only else None
            if signature and signature != getattr(self, '_advice_signature', None):
                self._advice_signature = signature
                self._night_advice(night_start, payload, hours)''')
s=s.replace('        return max(0.0, min(MODEL_WAIT_MAX, 0.5 * spare / nights_left))','        return max(0.0, min(8.0, 192.0-self.model_wait, 0.5 * spare / nights_left))')
s=s.replace('            self.planner.extra_avoid = set(plan["avoid_directions"])','''            self.planner.extra_avoid = set(plan["avoid_directions"])
            ids = set(plan.get("prioritize_target_ids", []))
            for rid in plan.get("prioritize_request_ids", []):
                ids.update(self.advisor.active_requests[rid]['target_ids'])
            self.planner.operator_priorities = {self.planner.index_of[t] for t in ids}
            self.preference_until = plan.get('valid_until',0)''')
s=s.replace('"notices_now": notices,','"notices_now": notices, "geometry": self.planner.geometry.summary(),\n                "exposures_processed": len(self.planner.history), "invalidated_exposures": len(self.planner.invalidated),')
s=s.replace('            planner.operator_priorities = set()', '            planner.operator_priorities = set()\n            planner.extra_avoid = set()')
s=s.replace('            log(f"pro finished:', '''            if agent and agent.client:
                log('llm audit: '+json.dumps({'calls':len(agent.client.calls),'ok':agent.client.ok,
                    'failed':agent.client.failed,'validated':agent.advisor.validated,
                    'operator_calls':agent.advisor.operator_count,'anomaly_calls':agent.advisor.anomaly_count}))
            log(f"pro finished:''')
p.write_text(s)
p=Path('work/gosim-desi-v300/agent/planner.py');s=p.read_text().replace('        self.request_legs = {}','        self.request_legs = {}\n        self.operator_priorities = set()',1)
s=s.replace('item = base[i] = (alt, az, lunar, up, (1.0 + URGENCY / nights_left) * damp * dirf)', 'item = base[i] = (alt, az, lunar, up, (1.0 + URGENCY / nights_left) * damp * dirf * (1.1 if i in self.operator_priorities else 1.0))')
p.write_text(s)
p=Path('work/gosim-desi-v300/agent/advisor.py');s=p.read_text().replace('hashlib.sha256(json.dumps(notices,sort_keys=True).encode())', "hashlib.sha256(json.dumps({k:v for k,v in notices.items() if k!='night'},sort_keys=True).encode())");p.write_text(s)
p=Path('work/gosim-desi-v300/agent/llm_client.py');s=p.read_text()
s=s.replace('call_timeout: float = 90.0, max_calls: int = 1500,\n                 max_retries: int = 3, max_in_flight: int = 4', 'call_timeout: float = 12.0, max_calls: int = 48,\n                 max_retries: int = 2, max_in_flight: int = 2')
s=s.replace('self.answer = client._request(system, user, timeout)', '''remaining = timeout - (time.monotonic()-started)
                if remaining <= 0: break
                self.answer = client._request(system, user, remaining)''')
s=s.replace('time.sleep(1.0 + attempt)', 'time.sleep(min(0.5, max(0.0, timeout-(time.monotonic()-started))))')
s=s.replace('data = json.loads(response.read().decode("utf-8"))', '''raw=response.read(262145)
            if len(raw)>262144: raise ValueError("response exceeds byte limit")
            data = json.loads(raw.decode("utf-8"))''')
s=s.replace('        parsed = json.loads(match.group(0))','''        def pairs(items):
            result={}
            for k,v in items:
                if k in result: raise ValueError("duplicate JSON key")
                result[k]=v
            return result
        def nonfinite(value):
            raise ValueError("nonfinite JSON value")
        if data['choices'][0].get('finish_reason')=='length': raise ValueError("truncated response")
        parsed = json.loads(match.group(0), object_pairs_hook=pairs, parse_constant=nonfinite)''')
p.write_text(s)
