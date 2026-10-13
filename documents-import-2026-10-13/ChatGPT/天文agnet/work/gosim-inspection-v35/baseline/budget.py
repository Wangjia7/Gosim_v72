"""CPU budget and an independent wall protection deadline.
Platform snapshots are authoritative. The 900-second fallback counts own turns
only, including all in-process worker CPU; waits and between-turn engine time
never reduce that counter.
"""
import math

class AgentClock:
    def __init__(self,init):
        limits=init.get('limits',{})
        self.total=float(limits.get('global_cpu_seconds',limits.get('global_wallclock_seconds',900.)))
        self.factor=float(limits.get('speed_factor') or 1.)
        self.used=0.
    def account(self,cpu):
        self.used+=max(0.,cpu)
    def read(self,payload):
        clock=payload.get('wallclock') or {}
        mode=clock.get('clock_mode','cpu')
        wall=max(0.,float(clock.get('wall_remaining_seconds',math.inf)))
        if mode!='cpu':
            remaining=max(0.,float(clock.get('remaining_seconds',self.total)))
            return remaining,min(wall,remaining),False
        if 'remaining_real_cpu_seconds' in clock:
            cpu=float(clock['remaining_real_cpu_seconds'])
        elif 'remaining_seconds' in clock:
            cpu=float(clock['remaining_seconds'])*float(clock.get('speed_factor') or self.factor)
        else:cpu=self.total*self.factor-self.used
        return max(0.,cpu),wall,True

def near_wall_cap(wall_left,turn_cost=0.):
    return wall_left < max(10.,2.*max(0.,turn_cost))
