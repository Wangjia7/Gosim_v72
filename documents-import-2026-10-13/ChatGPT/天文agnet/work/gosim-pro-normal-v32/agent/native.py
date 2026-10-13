import ctypes as C
import math
import os
from pathlib import Path

LIB = None
if os.environ.get('OBSERVER_NATIVE', '1') != '0':
    try:
        LIB = C.CDLL(str(Path(__file__).with_name('libjoint.so')))
        LIB.evaluate_field.argtypes = [C.c_int, C.c_int, C.c_int, C.c_double, C.c_double,
            C.c_double, C.c_int, C.c_double, C.c_double, C.POINTER(C.c_double),
            C.POINTER(C.c_double), C.POINTER(C.c_double), C.POINTER(C.c_int), C.POINTER(C.c_double)]
        LIB.evaluate_field.restype = None
        LIB.classify_field.argtypes = [C.c_int,C.c_int,C.c_double,C.c_double,C.c_double,
            C.c_int,C.c_double,C.c_double,C.POINTER(C.c_double),C.POINTER(C.c_double),C.POINTER(C.c_int)]
        LIB.classify_field.restype = None
    except (OSError, AttributeError):
        LIB = None


class GeometryBatch:
    def __init__(self, grid, near, base, misses, margin):
        self.grid, self.near = grid, near
        vectors=[]
        for j in near:
            a,z=map(math.radians,base[j][:2])
            vectors.extend((math.cos(a)*math.cos(z),math.cos(a)*math.sin(z),math.sin(a)))
        self.xyz=(C.c_double*len(vectors))(*vectors)
        self.margin=(C.c_double*len(near))(*(min(grid.glass*.25,margin*(.5+1.5*misses[j])) for j in near))
        self.fibers=(C.c_int*len(near))()

    def on_glass(self, altitude, azimuth):
        g=self.grid
        LIB.classify_field(len(self.near),g.side,g.glass,g.pitch,g.fov,int(g.gap==0),
            altitude,azimuth,self.xyz,self.margin,self.fibers)
        return tuple(j for k,j in enumerate(self.near) if self.fibers[k]>=0)


class FieldBatch:
    def __init__(self, grid, near, base, misses, choices, gain, margin):
        self.grid, self.near, self.choices = grid, near, choices
        vectors = []
        for j in near:
            a,z=map(math.radians, base[j][:2])
            vectors.extend((math.cos(a)*math.cos(z), math.cos(a)*math.sin(z), math.sin(a)))
        self.xyz=(C.c_double*len(vectors))(*vectors)
        self.margin=(C.c_double*len(near))(*(min(grid.glass*.25,margin*(.5+1.5*misses[j])) for j in near))
        values=[gain(j,t,p) for t,p in choices for j in near]
        self.gains=(C.c_double*len(values))(*values)
        self.picks=(C.c_int*(len(choices)*grid.n))()
        self.totals=(C.c_double*len(choices))()

    def evaluate(self, altitude, azimuth):
        g=self.grid
        LIB.evaluate_field(len(self.near),len(self.choices),g.side,g.glass,g.pitch,g.fov,
                          int(g.gap == 0),altitude,azimuth,self.xyz,self.margin,self.gains,self.picks,self.totals)
        return [(t,p,{f:self.near[self.picks[k*g.n+f]] for f in range(g.n)
                      if self.picks[k*g.n+f]>=0},self.totals[k])
                for k,(t,p) in enumerate(self.choices)]

    def best(self, altitude, azimuth, time_price):
        g=self.grid
        LIB.evaluate_field(len(self.near),len(self.choices),g.side,g.glass,g.pitch,g.fov,
                          int(g.gap == 0),altitude,azimuth,self.xyz,self.margin,self.gains,self.picks,self.totals)
        valid=[k for k in range(len(self.choices)) if self.totals[k]>0]
        if not valid:return None,0.0
        k=max(valid,key=lambda k:self.totals[k]-time_price*self.choices[k][0])
        t,p=self.choices[k]
        pick={f:self.near[self.picks[k*g.n+f]] for f in range(g.n) if self.picks[k*g.n+f]>=0}
        rate=max(self.totals[j]/self.choices[j][0] for j in valid)
        return (self.totals[k]-time_price*t,t,pick,self.totals[k],p),rate
