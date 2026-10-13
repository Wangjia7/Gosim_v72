#!/usr/bin/env python3
"""Test-only local runner adapter. On macOS, validate CPU units against process_time.

Usage: python tools/run_local_metered.py /path/to/runner/run_local.py <runner arguments>
Scoring, cards and the runner on disk are untouched. This adapter is not the participant agent.
"""
import ctypes
import ctypes.util
import os
from pathlib import Path
import runpy
import sys
import time


def main():
    runner = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(runner.parent))
    from challenge import fair_clock
    if sys.platform == 'darwin':
        lib = ctypes.CDLL(ctypes.util.find_library('proc') or '/usr/lib/libproc.dylib')
        class Info(ctypes.Structure):
            _fields_ = [('uuid',ctypes.c_uint8*16),('user',ctypes.c_uint64),('system',ctypes.c_uint64),('rest',ctypes.c_uint64*30)]
        def meter(pid):
            info = Info()
            if lib.proc_pid_rusage(int(pid),2,ctypes.byref(info)) != 0:
                return None
            return (info.user+info.system)/1e9
        original = fair_clock._darwin_cpu()
        start = time.process_time(); raw0 = meter(os.getpid()); old0 = original(os.getpid())
        while time.process_time()-start < .2:
            pass
        actual = time.process_time()-start
        raw = meter(os.getpid())-raw0; old = original(os.getpid())-old0
        print(f'meter check: process_time={actual:.6f}s raw_ns={raw:.6f}s upstream={old:.6f}s',file=sys.stderr)
        if abs(raw/actual-1) > .05:
            raise SystemExit('Independent CPU meter failed unit check; refusing benchmark')
        fair_clock._darwin_cpu = lambda: meter
    sys.argv = [str(runner)] + sys.argv[2:]
    runpy.run_path(str(runner),run_name='__main__')


if __name__ == '__main__':
    main()
