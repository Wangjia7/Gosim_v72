"""Joint 61x61 offset posterior; O(rows * 61 + grid) exact spherical updates.

Queries use the joint cumulative mass with a conservative 0.002-degree safety
floor. No atmospheric score is used as a hit label.
"""
from __future__ import annotations
import bisect
import math
from collections import deque

class PointingModel:
    def __init__(self, grid, epsilon=.002):
        self.grid = grid
        self.centres = [grid.fiber_center(f) for f in range(grid.n)]
        self.n = 61
        self.axes = [(.005 * (i - 30)) for i in range(self.n)]
        self.z_axes = list(self.axes)
        self.step = .005
        self.refined = False
        self.history = deque(maxlen=100)
        self.since_reset = 0
        self.epsilon = epsilon
        self.mean = (0.0, 0.0)
        self.samples = self.exposures = self.resets = 0
        self.cusum = 0.0
        self.cooldown = 0
        self._prior()
        self._rebuild()

    def _prior(self):
        self.mass = [.98*math.exp(-.5*(a*a+z*z)/.02**2)/(2*math.pi*.02**2)+.02/.3**2
                     for a in self.axes for z in self.z_axes]
        total=sum(self.mass)
        self.mass=[v/total for v in self.mass]

    def _refine(self):
        history=list(self.history)
        a,z=self.mean
        a,z=max(-.12,min(.12,a)),max(-.12,min(.12,z))
        self.axes=[a+.001*(i-30) for i in range(self.n)]
        self.z_axes=[z+.001*(i-30) for i in range(self.n)]
        self.step=.001;self.refined=True
        self._prior();self._rebuild()
        for cmd,rows in history:self.observe(cmd,rows,_replay=True)

    def _widen(self):
        axes=[.005*(i-30) for i in range(self.n)]
        mass=[0.0]*len(self.mass)
        for i,a in enumerate(self.axes):
            ai=min(60,max(0,int(round(a/.005))+30))
            for j,z in enumerate(self.z_axes):
                zi=min(60,max(0,int(round(z/.005))+30))
                mass[ai*self.n+zi]+=self.mass[i*self.n+j]
        self.axes=axes;self.z_axes=list(axes);self.step=.005;self.refined=False
        self.mass=[.5*v+.5/len(mass) for v in mass]
        self.history.clear();self.since_reset=0
        self._rebuild()

    def _rebuild(self):
        n = self.n
        prefix = [[0.0] * (n+1) for _ in range(n+1)]
        ma, mz = [0.0] * n, [0.0] * n
        for i in range(n):
            run = 0.0
            for j in range(n):
                v = self.mass[i*n+j]
                run += v
                prefix[i+1][j+1] = prefix[i][j+1] + run
                ma[i] += v; mz[j] += v
        self.prefix = prefix
        self.mean = (sum(a*v for a,v in zip(self.axes, ma)), sum(a*v for a,v in zip(self.z_axes, mz)))
        def interval(marginal, axes):
            total = 0.0; lo = hi = self.axes[-1]
            for a, v in zip(axes, marginal):
                old = total; total += v
                if old < .025 <= total: lo = a
                if old < .975 <= total: hi = a; break
            return [lo-self.step/2, hi+self.step/2]
        self.intervals = (interval(ma,self.axes), interval(mz,self.z_axes))

    def command(self, alt, az):
        return round(min(90.0, max(0.0, alt-self.mean[0])), 4), round((az-self.mean[1]) % 360.0, 4) % 360.0

    def _bounds(self, dn, de, fiber, center_alt, correction, padding=0.0):
        fn, fe = self.centres[fiber]
        half = self.grid.glass / 2 + padding
        ca = max(1e-5, math.cos(math.radians(center_alt)))
        a, z = correction
        cmd_alt = min(90.0, max(0.0, center_alt-a))
        a = center_alt-cmd_alt
        return (max(a + dn-fn-half, -cmd_alt), min(a + dn-fn+half, 90.0-cmd_alt),
                z + (de-fe-half)/ca, z + (de-fe+half)/ca)

    def _indices(self, bounds):
        a,b,c,d = bounds
        x,y = self.axes,self.z_axes
        return bisect.bisect_left(x,a), bisect.bisect_right(x,b), bisect.bisect_left(y,c), bisect.bisect_right(y,d)

    def p_inside(self, dn, de, fiber, center_alt):
        a,b,c,d = self._indices(self._bounds(dn,de,fiber,center_alt,self.mean,-.002))
        p = self.prefix
        return min(1.0, max(0.0,p[b][d]-p[a][d]-p[b][c]+p[a][c]))

    @staticmethod
    def _rect(diff, rect, value):
        a,b,c,d = rect
        if a >= b or c >= d:
            return
        diff[a][c] += value; diff[b][c] -= value
        diff[a][d] -= value; diff[b][d] += value

    def _hit_rectangles(self, cmd, alt, az, fiber):
        """Exact spherical hit set: at most two altitude intervals per azimuth column.

        north=tan(u-centre_alt), east=E/(R*cos(u-centre_alt)). Invert these
        inequalities instead of evaluating a full grid of tangent coordinates.
        """
        fn,fe=self.centres[fiber]
        half=self.grid.glass/2
        gn0,gn1=math.atan(math.radians(fn-half)),math.atan(math.radians(fn+half))
        e0,e1=math.radians(fe-half),math.radians(fe+half)
        ta=math.radians(alt);st,ct=math.sin(ta),math.cos(ta)
        for j,z in enumerate(self.z_axes):
            delta=math.radians(az-cmd[1]-z)
            b=ct*math.cos(delta);east=ct*math.sin(delta)
            radius=math.hypot(st,b)
            if radius<=0:continue
            u=math.atan2(st,b)
            lo,hi=max(0.,u-gn1),min(math.pi/2,u-gn0)
            if lo>hi:continue
            low,high=(e0,e1) if east>=0 else (-e1,-e0)
            east=abs(east)
            intervals=[(lo,hi)]
            if east<1e-16:
                if not low<=0<=high:continue
            else:
                if high<=0:continue
                bound=east/(high*radius)
                if bound>1+1e-12:continue
                theta=math.acos(min(1.,bound))
                lo,hi=max(lo,u-theta),min(hi,u+theta)
                if lo>hi:continue
                intervals=[(lo,hi)]
                if low>0:
                    bound=east/(low*radius)
                    if bound<1:
                        theta=math.acos(max(0.,bound))
                        intervals=[(lo,min(hi,u-theta)),(max(lo,u+theta),hi)]
            for lo,hi in intervals:
                if lo>hi:continue
                a=bisect.bisect_left(self.axes,math.degrees(lo)-cmd[0]-1e-10)
                b=bisect.bisect_right(self.axes,math.degrees(hi)-cmd[0]+1e-10)
                if a<b:yield a,b,j,j+1

    def observe(self, cmd, rows, _replay=False):
        if not rows or not 0 <= cmd[0] <= 90:
            return
        n = self.n
        delta = [[0.0]*(n+1) for _ in range(n+1)]
        count = [[0.0]*(n+1) for _ in range(n+1)]
        hit_count = 0
        eps = self.epsilon
        if not _replay:self.history.append((cmd,list(rows)))
        for alt, az, fiber, hit in rows:
            change=math.log((1-eps)/eps) * (1 if hit else -1)
            for rect in self._hit_rectangles(cmd,alt,az,fiber):
                self._rect(delta,rect,change)
                self._rect(count,rect,1.)
            hit_count += bool(hit)
        mean = square = 0.0
        ll = []
        for i in range(n):
            for j in range(n):
                for matrix in (delta,count):
                    if i: matrix[i][j] += matrix[i-1][j]
                    if j: matrix[i][j] += matrix[i][j-1]
                    if i and j: matrix[i][j] -= matrix[i-1][j-1]
                k = count[i][j]
                m = self.mass[i*n+j]
                mean += m*k; square += m*k*k
                ll.append(math.log(max(m,1e-300)) + delta[i][j])
        variance = max(0.0,square-mean*mean) + eps*len(rows) + .25
        # ponytail: count CUSUM can miss count-preserving swaps; per-target predictive residuals if observed.
        if not _replay:
            self.cusum = max(0.0,self.cusum+(mean-hit_count)/math.sqrt(variance)-.5)
            if self.cooldown:
                self.cooldown -= 1
                self.cusum = 0.0              # recovery residuals must not retrigger when cooldown expires
            elif self.cusum > 5:
                self.cusum = 0.0; self.cooldown = 30; self.resets += 1
                self._widen()
                return
        top = max(ll)
        self.mass = [math.exp(x-top) for x in ll]
        total = sum(self.mass)
        self.mass = [v/total for v in self.mass]
        if not _replay:
            self.exposures += 1; self.samples += len(rows); self.since_reset += 1
        self._rebuild()
        if not _replay and not self.refined and self.since_reset>=20 and max(hi-lo for lo,hi in self.intervals)<=.015:
            self._refine()

    def summary(self):
        return {'mean': list(self.mean), 'ci95': self.intervals, 'samples': self.samples,
                'exposures': self.exposures, 'resets': self.resets, 'cusum': self.cusum,
                'grid_step':self.step}
