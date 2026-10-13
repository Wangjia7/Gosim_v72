"""Common observe/diagnose/event/obligation control for both geometry kernels."""
import math
import os
import time
import copy
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
        self.joint_trials=0;self.joint_accepted=0;self.joint_errors=0
        self.diagnostic_targets=sorted(range(len(planner.ids)),key=lambda i:(-planner.flux[i],i))[:128]

    def feedback(self,result,now,notices,messages):
        if not self.enabled:return
        if result and result.get('action')=='report':
            self.health.report_result(result,now.timestamp());self.events.report_result(result)
        self.health.observe(result,now,notices);self.health.resync(messages)

    def refresh(self,requests,now,cpu_budget):
        if self.enabled and self.joint:
            self.obligations.refresh(requests,now,max(.002,min(.12,cpu_budget*.35)))
            self.obligations.search_deadline=time.process_time()+max(.001,cpu_budget-self.obligations.cpu)

    def allocate(self,agent,payload,now,requests):
        """Redistribute a turn's own CPU, retaining the rest-of-card reserve."""
        if not self.enabled:return
        cpu,wall,fair=agent._clock(payload)
        if not fair:return
        left=max(1.,agent._decisions_left(now))
        unit=max(.001,.85*max(0.,cpu-15.)/left)
        from skymath import parse_utc
        imminent=any(r.get('completion_reward',0)>0 and r.get('remaining_count',r['minimum_completed'])>0 and
                     0<(parse_utc(r['deadline_utc'])-now).total_seconds()<=4*3600 for r in requests)
        multiplier=1.5 if imminent or self.obligations.urgent_required else 1.
        cap=max(.003,min(.015*cpu,unit*multiplier))
        self.p.cpu_turn_budget=min(self.p.cpu_turn_budget or cap,cap) if multiplier==1 else cap

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
        if self.health.state=='unavailable_candidate' and self.health.zero_run>=2:
            retry=min(boundary,self.health.last_probe+900)
            if retry>stamp:
                return {'action':'wait','until_utc':format_utc(now+timedelta(seconds=retry-stamp)),
                        'reason':'repeated zero exposures; bounded recovery probe'},safe_end
        return None,safe_end

    def diagnostic(self,now,end):
        p=self.p;night=p.current_night(now)
        if night is None:return None
        T=int(min(max(300,p.min_exposure),p.max_exposure,(end-now).total_seconds()))
        if T<p.min_exposure:return None
        if os.environ.get('FUSION_SCIENCE_PROBE','1')=='1':
            # A diagnostic is a short independent exposure, not necessarily a
            # single already-saturated bright star. Reuse the legal science
            # search without letting this forced short visit change time price.
            o=self.obligations;active=o.active;rate=p.rate_ema
            names=('pending','pending_program','pending_duration','pending_cmd','pending_night','pending_notices')
            state={n:copy.deepcopy(getattr(p,n,None)) for n in names}
            o.active=False
            try:
                hours=(now-p.nights[0][0]).total_seconds()/3600
                action=p.plan(now,now+timedelta(seconds=T),night[0],hours)
            except Exception as exc:
                p.log('science diagnostic fallback: '+type(exc).__name__)
                action=None
            finally:
                o.active=active;p.rate_ema=rate
            if (action and action.get('action')=='observe' and p.pending and
                any(v.get('dir_clean') and v.get('model',0)>0 for v in p.pending.values())):
                return {**action,'reason':'short science health diagnostic'}
            for n,v in state.items():setattr(p,n,v)
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
                'obligations':self.obligations.summary(),'diagnostics':self.diagnostics,
                'joint_trials':self.joint_trials,'joint_accepted':self.joint_accepted,'joint_errors':self.joint_errors}

    def forecast(self,action,requests,now):
        p=self.p;science=0.;required=set();request_counts={}
        predicted={t:min(1.,max(0.,v.get('pred',0.))) for t,v in p.pending.items()}
        raw=getattr(p,'factor_lower',p.factor)
        for target,factor in predicted.items():
            i=p.index_of[target]
            # Conservative program-independent science prediction.
            score=p.weight[i]*factor*min(p.multipliers[action['program']],p.mismatch)
            science+=max(0.,score-p.cur[i]*p.weight[i])
            if p.required[i] and raw[i]<p.required_threshold and factor>=min(1.,1.1*p.required_threshold):
                required.add(i)
        for r in requests:
            if r.get('remaining_count',r['minimum_completed'])<=0 or r.get('completion_reward',0)<=0:continue
            stamp=now.timestamp()
            from skymath import parse_utc
            if stamp<parse_utc(r['issued_at_utc']).timestamp() or stamp+action['duration_seconds']>parse_utc(r['deadline_utc']).timestamp():
                request_counts[r['request_id']]=0;continue
            done=set(r.get('completed_target_ids',[]))
            request_counts[r['request_id']]=sum(predicted.get(t,0.)>=min(1.,1.1*r['completion_factor_threshold']) for t in r['target_ids'] if t not in done)
        return science,required,request_counts

    def plan(self,now,end,night,hours,requests):
        """Retain a legal incumbent before using spare CPU for group search.

        Acceptance is a forecast Pareto guard, never a score or completion fact.
        It protects unrelated obligations while the group objective is tested.
        """
        p=self.p;o=self.obligations
        if not self.enabled or not self.joint or not o.active:return p.plan(now,end,night,hours)
        names=('pending','pending_program','pending_duration','pending_cmd','pending_night','pending_notices','rate_ema')
        def snapshot():return {n:copy.deepcopy(getattr(p,n)) for n in names}
        def restore(state):
            for n,v in state.items():setattr(p,n,v)
        budget=p.cpu_turn_budget;started=time.process_time();initial_rate=p.rate_ema
        o.active=False
        try:incumbent=p.plan(now,end,night,hours)
        finally:o.active=True
        original=snapshot()
        spare=(budget or .05)-(time.process_time()-started)
        if incumbent is not None and spare<.003:return incumbent
        baseline=self.forecast(incumbent,requests,now) if incumbent else (0.,set(),{})
        p.rate_ema=initial_rate
        p.cpu_turn_budget=max(.003,spare)
        o.search_deadline=time.process_time()+p.cpu_turn_budget
        # A second numeric search is not an independent observation of E.
        e_len=len(p.e_hours);last=list(p.e_hours[-1][2]) if e_len else None
        try:candidate=p.plan(now,end,night,hours)
        except Exception:
            self.joint_errors+=1
            if incumbent is None:raise
            restore(original);return incumbent
        finally:
            p.cpu_turn_budget=budget
            del p.e_hours[e_len:]
            if e_len:p.e_hours[-1][2][:]=last
        self.joint_trials+=1
        if candidate is None:restore(original);return incumbent
        proposal=self.forecast(candidate,requests,now)
        no_loss=(proposal[0]+1e-8>=baseline[0] and baseline[1]<=proposal[1] and
                 all(proposal[2].get(r,0)>=n for r,n in baseline[2].items()))
        improvement=(proposal[0]>baseline[0]+1e-8 or proposal[1]>baseline[1] or
                     any(n>baseline[2].get(r,0) for r,n in proposal[2].items()))
        if incumbent is None or (no_loss and improvement):
            self.joint_accepted+=1;return candidate
        restore(original);return incumbent

    def clip_wait(self,action,now):
        if not self.enabled or action.get('action')!='wait':return action
        from skymath import parse_utc
        stop=parse_utc(action['until_utc']).timestamp() if action.get('until_utc') else now.timestamp()+action.get('duration_seconds',900)
        boundary=self.events.next_boundary(now.timestamp(),stop)
        if boundary<stop:
            action={**action,'until_utc':format_utc(now+timedelta(seconds=boundary-now.timestamp()))}
            action.pop('duration_seconds',None)
        return action
