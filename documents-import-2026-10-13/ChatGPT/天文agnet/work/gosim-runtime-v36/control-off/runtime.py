"""Common observe/diagnose/event/obligation control for both geometry kernels."""
import math
import os
from datetime import timedelta
from conditions import HealthWatch
from events import EventQueue
from obligations import Obligations
from skymath import local_sidereal_deg, radec_to_altaz, normalized_airmass, Moon, shift_altaz, format_utc


class Runtime:
    def __init__(self, planner):
        self.p=planner;self.health=HealthWatch(planner);self.events=EventQueue(planner)
        self.obligations=Obligations(planner,self.events)
        planner.events=self.events;planner.obligations=self.obligations
        planner.runtime_health=self.health
        self.enabled=os.environ.get('FUSION_RUNTIME','1')=='1'
        self.joint=os.environ.get('FUSION_OBLIGATIONS','1')=='1'
        self.report_pending=False;self.diagnostics=0
        self.diagnostic_targets=sorted(range(len(planner.ids)),key=lambda i:(-planner.flux[i],i))[:128]

    def feedback(self,result,now,notices,messages):
        if not self.enabled:return
        if result and result.get('action')=='report':
            self.health.report_result(result,now.timestamp());self.events.report_result(result)
        self.health.observe(result,now,notices);self.health.resync(messages)

    def refresh(self,requests,now,cpu_budget):
        if self.enabled and self.joint:
            self.obligations.refresh(requests,now,max(.002,min(.12,cpu_budget*.2)))

    def before_plan(self,agent,payload,now,night_end):
        if not self.enabled:return None,night_end
        stamp=now.timestamp();end=night_end.timestamp()
        unavailable=self.events.unavailable_until(stamp)
        if unavailable:
            until=self.events.next_boundary(stamp,min(unavailable,end))
            return {'action':'wait','until_utc':format_utc(now+timedelta(seconds=until-stamp)),
                    'reason':'validated operational unavailability; not a fault'},night_end
        event=self.events.due_hardware(stamp)
        detector=getattr(agent,'detector',None)
        free=detector.free_left() if detector else agent.free_left()
        false=detector.paid_false if detector else agent.paid_false
        evidence_probe=self.health.report_due(stamp,free)
        # Event facts authorize one evaluation at/after their start, never before.
        # Misdiagnosed episodes are bounded by the same paid-report allowance.
        if (event or evidence_probe) and false<6 and stamp-self.health.last_report>=60:
            agent.reports+=1
            if detector:
                detector.last_evidence='validated engineering event' if event else 'independent persistent throughput bounds'
            else:agent.last_report_hours=(now-agent.start).total_seconds()/3600
            self.health.last_report=stamp
            if event:self.events.reported(event)
            return {'action':'report','reason':('engineering event '+event['event_id']) if event else 'persistent independent throughput residual'},night_end
        boundary=self.events.next_boundary(stamp,end)
        safe_end=now+timedelta(seconds=boundary-stamp)
        if boundary-stamp<self.p.min_exposure:
            return {'action':'wait','until_utc':format_utc(safe_end),'reason':'next engineering boundary'},safe_end
        if self.health.diagnostic_due(stamp):
            action=self.diagnostic(now,safe_end)
            if action:
                self.health.last_probe=stamp;self.diagnostics+=1
                return action,safe_end
        return None,safe_end

    def diagnostic(self,now,end):
        p=self.p;night=p.current_night(now)
        if night is None:return None
        T=int(min(300,p.max_exposure,(end-now).total_seconds()))
        if T<p.min_exposure:return None
        lst=local_sidereal_deg(now,p.lon)
        later=local_sidereal_deg(now+timedelta(seconds=T),p.lon)
        moon=Moon(now+timedelta(seconds=T/2),local_sidereal_deg(now+timedelta(seconds=T/2),p.lon),p.lat,p.lunar_model)
        for i in self.diagnostic_targets:
            alt,az=radec_to_altaz(p.ra[i],p.dec[i],lst,p.lat)
            if min(alt,radec_to_altaz(p.ra[i],p.dec[i],later,p.lat)[0])<p.min_alt+1:continue
            if p._direction_factor(alt,az)<.99:continue
            model=moon.lunar_factor(p.ra[i],p.dec[i])/(p.q0*normalized_airmass(alt)**p.airmass_exponent)
            fib=min(range(p.grid.n),key=lambda f:sum(x*x for x in p.grid.fiber_center(f)))
            a,z=shift_altaz(alt,az,*(-x for x in p.grid.fiber_center(fib)))
            # Same command correction convention as the numeric planners.
            off=getattr(p,'offset',(0.,0.))
            a-=off[0];z=(z-off[1])%360
            if not 0<=a<=90:continue
            program=p._band(model*(getattr(p,'band_level',None) or max(.4,p.scale)))
            target=p.ids[i]
            p.pending={target:{'model':model,'band_model':model/.95,'alt':alt,'az':az,
                'pred':p.flux[i]*T*model*p.scale/p.f0t0,'dir_clean':True,'clean':True,'fiber':fib,'p':1.}}
            p.pending_program=program;p.pending_duration=T;p.pending_night=night[0]
            p.pending_notices=set(p.notices);p.pending_cmd=(a,z)
            return {'action':'observe','pointing':{'alt_deg':round(a,4),'az_deg':round(z,4)},
                    'duration_seconds':T,'program':program,'assignments':{str(fib):target},
                    'reason':'short independent health diagnostic'}
        return None

    def summary(self):
        return {'health':self.health.summary(),'events':self.events.summary(),
                'obligations':self.obligations.summary(),'diagnostics':self.diagnostics}
