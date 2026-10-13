import ctypes,ctypes.util,os,resource,sys,time,json
sys.path.insert(0,'/Users/jqwang/Documents/gosim-observer-examples/runner')
from challenge.fair_clock import _darwin_cpu
class Timebase(ctypes.Structure):
    _fields_=[('numer',ctypes.c_uint32),('denom',ctypes.c_uint32)]
tb=Timebase();libc=ctypes.CDLL(ctypes.util.find_library('c') or 'libc.dylib');libc.mach_timebase_info(ctypes.byref(tb))
read=_darwin_cpu(); pid=os.getpid()
def sample():
    r=resource.getrusage(resource.RUSAGE_SELF)
    return {'process_time':time.process_time(),'getrusage':r.ru_utime+r.ru_stime,'runner_darwin_cpu':read(pid),'monotonic':time.monotonic()}
rows=[]
for wanted in [0.3,0.6,1.0]:
    a=sample(); stop=time.process_time()+wanted; value=1
    while time.process_time()<stop:
        for _ in range(1000): value=(value*1664525+1013904223)&0xffffffff
    b=sample(); delta={k:b[k]-a[k] for k in a}; delta['runner_over_process_ratio']=delta['runner_darwin_cpu']/delta['process_time'];rows.append(delta)
print(json.dumps({'platform':sys.platform,'machine':os.uname().machine,'timebase_numer':tb.numer,'timebase_denom':tb.denom,'timebase_ratio':tb.numer/tb.denom,'trials':rows},indent=2))
