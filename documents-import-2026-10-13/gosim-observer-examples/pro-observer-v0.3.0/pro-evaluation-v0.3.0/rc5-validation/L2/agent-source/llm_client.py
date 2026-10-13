"""OpenAI-compatible chat client for the pro agent (standard library only).

Configuration (environment, or a local .env next to agent.py that is never packed):
    OPENAI_API_KEY    required (KIMI_API_KEY is accepted as an alternate name)
    OPENAI_BASE_URL   default https://api.kimi.com/coding/v1 (Kimi Coding Plan; outside mainland China
                      use https://api.kimi.ai/coding/v1). On the platform this is injected automatically.
    OPENAI_MODEL      default k3

Calls never block the decision loop: `submit()` starts the request on a background thread and returns a
handle; the agent picks the answer up with `result()` on a later decision. The wall clock keeps running
while the model thinks, but the planner keeps working, so a slow reasoning model costs almost nothing.
k3 only accepts the default temperature, so none is sent.
"""
from __future__ import annotations

import json
import hashlib

import os

API_ASYNC = os.environ.get("V7_API_ASYNC", "0") == "1"
import re
import threading
import queue
from decision_log import sanitize
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from switches import TIERED, NIGHT_WAIT, VALUES

DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_MODEL = "k3"
MAX_BODY_BYTES = 512 * 1024

def _reject_nonfinite(value):
    raise ValueError("nonfinite JSON")
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


def api_key() -> str:
    return (os.environ.get('OPENAI_API_KEY', '').strip() or os.environ.get('KIMI_API_KEY', '').strip()
            or os.environ.get('DEEPSEEK_API_KEY', '').strip())


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
        self.input_hash = hashlib.sha256(json.dumps(sanitize([system, user]), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.timeout = timeout
        self.wait_limit = getattr(client, "night_wait_limit", NIGHT_WAIT)
        self.answer = None
        self.error = None
        self.seconds = 0.0
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(client, system, user, timeout), daemon=True)
        self._thread.start()

    def _run(self, client, system, user, timeout) -> None:
        started = time.monotonic()
        try:
            for attempt in range(client.max_retries):
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    self.error = "TimeoutError"
                    break
                try:
                    if not client._request_slots.acquire(blocking=False):
                        self.error = "in_flight_limit"
                        break
                    mailbox = queue.Queue(maxsize=1)
                    def fetch(remaining=remaining, mailbox=mailbox):
                        try:
                            answer = client._request(system, user, remaining, self.tag) if TIERED else client._request(system, user, remaining)
                            mailbox.put((True,answer))
                        except Exception as exc:
                            mailbox.put((False,exc))
                        finally:
                            client._request_slots.release()
                    # A slow socket cannot extend the complete call deadline. Its
                    # bounded request slot remains occupied until the I/O ends.
                    threading.Thread(target=fetch,daemon=True).start()
                    try:
                        ok,answer = mailbox.get(timeout=max(0.0, timeout-(time.monotonic()-started)))
                    except queue.Empty:
                        self.error = "TimeoutError"
                        break
                    if not ok:
                        raise answer
                    self.answer = answer
                    self.error = None
                    break
                except Exception as exc:
                    self.error = "TimeoutError" if isinstance(exc, TimeoutError) else type(exc).__name__
                    remaining = timeout-(time.monotonic()-started)
                    if remaining <= 0:
                        break
                    time.sleep(min(1.0+attempt,remaining))
        finally:
            self.seconds = time.monotonic() - started
            self._done.set()

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, seconds: float) -> bool:
        return self._done.wait(max(0.0, seconds))


class LLMClient:
    def __init__(self, log=lambda text: None, call_timeout: float = 90.0, max_calls: int = 1500,
                 max_retries: int = 3, max_in_flight: int = 4):
        self.log = log
        self.base_url = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
        self.key = api_key()
        self.model = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
        if not (os.environ.get('OPENAI_API_KEY', '').strip() or os.environ.get('KIMI_API_KEY', '').strip()) and self.key:
            self.base_url = os.environ.get('DEEPSEEK_BASE_URL', '').strip().rstrip('/')
            self.model = os.environ.get('DEEPSEEK_MODEL', '').strip()
            if not self.base_url or not self.model:
                self.key = ''
                self.log('llm: incomplete DEEPSEEK_* configuration; rules decide')
        self.call_timeout = max(.01, min(float(call_timeout), 20.0 if API_ASYNC else 90.0))
        self.max_calls = min(max_calls, 400) if API_ASYNC else max_calls
        self.max_retries = max(1,min(int(max_retries),3))
        self.max_in_flight = max(1,min(int(max_in_flight),4))
        self._request_slots = threading.BoundedSemaphore(self.max_in_flight)
        try:
            endpoint = urlsplit(self.base_url)
            host = endpoint.hostname
            endpoint.port
            valid = endpoint.scheme in ('http','https') and bool(host) and not any(ord(c)<=32 or ord(c)==127 for c in host)
            valid = valid and endpoint.username is None and endpoint.password is None
            if not valid: raise ValueError('invalid endpoint')
        except ValueError:
            self.key = ''
            self.log('llm: invalid endpoint; rules decide')
        self.calls: list[Call] = []
        self.ok = 0
        self.failed = 0
        self.sim_hours = 0.0
        self.timeout_streak = 0
        self.circuit_until = -float("inf")
        self.allow_submit = True
        self.night_wait_limit = NIGHT_WAIT
        self.night_slow = False

    def set_sim_time(self, hours):
        self.sim_hours = float(hours)
        # Collect abandoned handles too: they still count toward timeout and call limits.
        for call in self.calls:
            if call.done():
                self.collect(call)


    def request_payload(self, system, user, tag=None):
        payload = {"model": self.model,
            "messages": [{"role":"system", "content":system},
                         {"role":"user", "content":json.dumps(sanitize(user), separators=(',', ':'), allow_nan=False)}],
            "max_tokens":2000}
        endpoint = urlsplit(self.base_url)
        if TIERED and endpoint.scheme == 'https' and endpoint.netloc == 'api.deepseek.com' and self.model == 'deepseek-flash':
            requested = VALUES['V7_MODEL_EFFORT']
            effort = ('none' if tag == 'confirm_report' or requested == 'none' or
                      requested == 'auto' and self.night_slow else 'low')
            payload.update(reasoning_effort=effort, thinking={'type':'disabled' if effort == 'none' else 'enabled'})
            if effort == 'none':
                payload['max_tokens'] = 512
        return payload

    def _request(self, system: str, user: dict, timeout: float, tag=None) -> dict:
        payload = self.request_payload(system, user, tag)
        if TIERED:
            self.log('v7 llm request ' + json.dumps({'tag':tag,
                'reasoning_effort':payload.get('reasoning_effort'), 'thinking':payload.get('thinking'),
                'max_tokens':payload['max_tokens']}, separators=(',', ':')))
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        if len(body)>MAX_BODY_BYTES: raise ValueError("oversized request")
        request = urllib.request.Request(self.base_url + "/chat/completions", data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer " + self.key})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES+1)
            if len(raw)>MAX_BODY_BYTES: raise ValueError("oversized response")
            data = json.loads(raw.decode("utf-8"), parse_constant=_reject_nonfinite)
        text = data["choices"][0]["message"]["content"] or ""
        match = _JSON_OBJECT.search(text)
        if not match:
            raise ValueError("no JSON object in the reply")
        parsed = json.loads(match.group(0), parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError("reply is not a JSON object")
        return parsed

    def in_flight(self) -> int:
        return sum(1 for call in self.calls if not call.done())

    def submit(self, tag: str, system: str, user: dict, wallclock_left: float):
        """Start a call in the background; None when the run's limits say no."""
        if not self.key:
            return None
        if API_ASYNC:
            self.set_sim_time(self.sim_hours)
            if not self.allow_submit or self.sim_hours < self.circuit_until:
                return None
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
            if TIERED and call.tag == 'night_plan' and (call.answer is not None or
                    call.error in {'TimeoutError', 'timeout'} or call.seconds >= call.timeout):
                if call.seconds > getattr(call, 'wait_limit', NIGHT_WAIT):
                    # Stay at none for the remainder of this run once low exceeded its useful wait.
                    self.night_slow = True
            if API_ASYNC:
                timed_out = call.answer is None and (call.error in {"TimeoutError", "timeout"} or
                                                    call.seconds >= call.timeout)
                self.timeout_streak = self.timeout_streak + 1 if timed_out else 0
                if self.timeout_streak >= 3:
                    self.circuit_until = self.sim_hours + 6.0
                    self.timeout_streak = 0
                    self.log(f"v7 llm circuit open until simulation hour {self.circuit_until:.3f}")
                self.log("v7 llm response " + json.dumps({"tag": call.tag, "input_sha256": call.input_hash,
                         "answer": sanitize(call.answer), "error": call.error}, separators=(",", ":")))
            if call.answer is not None:
                self.ok += 1
                self.log(f'llm: {call.tag} accepted transport response in {call.seconds:.2f}s')
            else:
                self.failed += 1
                self.log(f"llm: {call.tag} failed ({call.error}); rules decide")   # never log the key
        return call.answer
