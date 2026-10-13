"""Append-only diagnostics; never writes official protocol stdout."""
from __future__ import annotations
import hashlib
import json
import math
import os
import sys
import time
from urllib.parse import urlsplit, urlunsplit

VERSION = '0.2.0'
_SECRET_NAMES = ('key', 'secret', 'token', 'password', 'authorization', 'credential')

def sanitize(value):
    """Remove credential-bearing fields/URLs and known environment secret values."""
    if isinstance(value, dict):
        return {str(k): ('[REDACTED]' if any(s in str(k).lower() for s in _SECRET_NAMES) else sanitize(v)) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,str):
        for name, secret in os.environ.items():
            if secret and len(secret)>=4 and any(s in name.lower() for s in _SECRET_NAMES): value=value.replace(secret,'[REDACTED]')
        if value.startswith(('http://','https://')):
            try:
                parts=urlsplit(value)
                value=urlunsplit((parts.scheme,parts.hostname or '',parts.path,'',''))
            except ValueError: return '[INVALID URL]'
        return value
    if value is None or isinstance(value,(bool,int)): return value
    return str(value)

class DecisionLogger:
    def __init__(self, config=None, path=None, stderr=None):
        self.path = path if path is not None else os.environ.get('PRO_LOG_PATH','decision-log.jsonl')
        self.stderr = stderr if stderr is not None else sys.stderr
        self.last_cpu_seconds=0.0
        self.last_wall_seconds=0.0
        self.sequence=0
        self.config_hash=hashlib.sha256(json.dumps(sanitize(config or {}),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def emit(self, record):
        cpu_started=time.process_time();wall_started=time.monotonic()
        self.sequence+=1
        packet={'schema_version':'pro-decision-log-v1','version':VERSION,'config_hash':self.config_hash,'event_id':self.sequence,**sanitize(record)}
        line=json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'
        try:
            with open(self.path,'a',encoding='utf-8') as stream: stream.write(line);stream.flush()
            self.last_cpu_seconds=time.process_time()-cpu_started
            self.last_wall_seconds=time.monotonic()-wall_started
            return True
        except (OSError,ValueError):
            try: self.stderr.write(line);self.stderr.flush()
            except (OSError,ValueError): pass
            self.last_cpu_seconds=time.process_time()-cpu_started
            self.last_wall_seconds=time.monotonic()-wall_started
            return False
