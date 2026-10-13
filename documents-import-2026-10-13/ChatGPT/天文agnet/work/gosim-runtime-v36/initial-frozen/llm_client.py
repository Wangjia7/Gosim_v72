"""OpenAI-compatible chat client for the pro agent (standard library only).

Configuration (environment, or a local .env next to agent.py that is never packed):
    OPENAI_API_KEY    required (KIMI_API_KEY is accepted as an alternate name)
    OPENAI_BASE_URL   default https://api.kimi.com/coding/v1 (Kimi Coding Plan; outside mainland China
                      use https://api.kimi.ai/coding/v1). On the platform this is injected automatically.
    OPENAI_MODEL      default k3

Requests run on background threads: `submit()` starts the request on a background thread and returns a
handle; the agent picks the answer up with `result()` on a later decision. Advisors may wait within the separate wall protection deadline. Idle network/model waiting consumes no CPU; parsing and local thread computation do consume CPU.
k3 only accepts the default temperature, so none is sent.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_MODEL = "k3"
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


def api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("KIMI_API_KEY", "").strip()


def load_dotenv(path: str) -> None:
    """Fill missing environment variables from a local .env (for local runs only)."""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                name, value = name.strip(), value.strip().strip('"').strip("'")
                if name and value and not os.environ.get(name):
                    os.environ[name] = value
    except OSError:
        pass


class Call:
    """One background chat completion."""

    def __init__(self, client: "LLMClient", tag: str, system: str, user: dict, timeout: float):
        self.tag = tag
        self.answer = None
        self.error = None
        self.seconds = 0.0
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(client, system, user, timeout), daemon=True)
        self._thread.start()

    def _run(self, client, system, user, timeout) -> None:
        started = time.monotonic()
        for attempt in range(client.max_retries):
            try:
                remaining = timeout - (time.monotonic()-started)
                if remaining <= 0: break
                self.answer = client._request(system, user, remaining)
                self.error = None
                break
            except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                self.error = type(exc).__name__
                if time.monotonic() - started > timeout:
                    break
                time.sleep(min(0.5, max(0.0, timeout-(time.monotonic()-started))))
        self.seconds = time.monotonic() - started
        self._done.set()

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, seconds: float) -> bool:
        return self._done.wait(max(0.0, seconds))


class LLMClient:
    def __init__(self, log=lambda text: None, call_timeout: float = 30.0, max_calls: int = 160,
                 max_retries: int = 2, max_in_flight: int = 2):
        self.log = log
        self.base_url = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
        self.key = api_key()
        self.model = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
        self.call_timeout = call_timeout
        self.max_calls = max_calls
        self.max_retries = max_retries
        self.max_in_flight = max_in_flight
        self.calls: list[Call] = []
        self.ok = 0
        self.failed = 0

    def _request(self, system: str, user: dict, timeout: float) -> dict:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(user, separators=(",", ":"))}],
            "max_tokens": 5000,
        }).encode("utf-8")
        request = urllib.request.Request(self.base_url + "/chat/completions", data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer " + self.key})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw=response.read(262145)
            if len(raw)>262144: raise ValueError("response exceeds byte limit")
            data = json.loads(raw.decode("utf-8"))
        text = data["choices"][0]["message"]["content"] or ""
        text = text.strip()
        if text.startswith('```'):
            match = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```', text)
            if not match: raise ValueError('reply is not one JSON fence')
            text = match.group(1)
        def pairs(items):
            result={}
            for k,v in items:
                if k in result: raise ValueError("duplicate JSON key")
                result[k]=v
            return result
        def nonfinite(value):
            raise ValueError("nonfinite JSON value")
        if data['choices'][0].get('finish_reason')=='length': raise ValueError("truncated response")
        parsed = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError("reply is not a JSON object")
        return parsed

    def in_flight(self) -> int:
        return sum(1 for call in self.calls if not call.done())

    def submit(self, tag: str, system: str, user: dict, wallclock_left: float):
        """Start a call in the background; None when the run's limits say no."""
        timeout = min(self.call_timeout, wallclock_left - 30.0)
        if len(self.calls) >= self.max_calls or timeout < 5.0 or self.in_flight() >= self.max_in_flight:
            return None
        call = Call(self, tag, system, user, timeout)
        self.calls.append(call)
        return call

    def collect(self, call):
        """The parsed answer of a finished call (None while running or after a failure). Logs once."""
        if call is None or not call.done():
            return None
        if not getattr(call, "_logged", False):
            call._logged = True
            if call.answer is not None:
                self.ok += 1
            else:
                self.failed += 1
                self.log(f"llm: {call.tag} failed ({call.error}); rules decide")   # never log the key
        return call.answer
