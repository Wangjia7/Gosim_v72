"""Bounded group completion lookahead; predictions never certify actual completion."""
import itertools
import math
import time
from datetime import datetime, timezone
from skymath import local_sidereal_deg, radec_to_altaz, normalized_airmass, Moon


class Obligations:
    def __init__(self, planner, events):
        self.p=planner;self.events=events
        self.groups=[];self.selected=set();self.urgent_required=set()
        self.options={};self.stamp=0.;self.cpu=0.;self.truncated=False
        self.reservations=[];self.last_key=None;self.active=False

    def intervals(self,i,start,end):
        pieces=[]
        for lo,hi in self.p.opportunities.intervals(i):
            lo,hi=max(lo,start),min(hi,end)
            if hi<=lo:continue
            work=[(lo,hi)]
            for a,b in self.events.blocked_intervals(lo,hi):
                work=[part for x,y in work for part in [(x,min(y,a)),(max(x,b),y)] if part[1]>part[0]]
            pieces.extend(work)
        return pieces

    def target_options(self,i,threshold,start,end):
        key=(i,threshold,start,end)
        if key in self.options:return self.options[key]
        p=self.p;found=[]
        # At most 6 successive windows; continuation is finite lookahead.
        for lo,hi in self.intervals(i,start,end)[:6]:
            duration=p.min_exposure
            model=0.
            for _ in range(3):
                sample=datetime.fromtimestamp(lo+duration/2,timezone.utc)
                lst=local_sidereal_deg(sample,p.lon)
                alt,az=radec_to_altaz(p.ra[i],p.dec[i],lst,p.lat)
                if alt<p.min_alt:break
                terrain=self.events.terrain_limit(az)
                if terrain is not None and alt<terrain+1:break
                moon=Moon(sample,lst,p.lat,p.lunar_model)
                model=moon.lunar_factor(p.ra[i],p.dec[i])/(p.q0*normalized_airmass(alt)**p.airmass_exponent)
                duration=max(p.min_exposure,math.ceil(threshold*1.15*p.f0t0/max(1e-12,p.flux[i]*model*p.scale)))
            if model>0 and duration<=min(p.max_exposure,hi-lo):
                # End altitude is separately checked; no partial window credit.
                end_lst=local_sidereal_deg(datetime.fromtimestamp(lo+duration,timezone.utc),p.lon)
                if radec_to_altaz(p.ra[i],p.dec[i],end_lst,p.lat)[0]>=p.min_alt:
                    found.append((lo,hi,duration))
        self.options[key]=found
        return found

    def sequence(self,members,threshold,start,end,busy=()):
        # Standalone visits are a conservative reservation. Actual co-observing
        # can release time; these reservations do not become score facts.
        rows=[]
        for i in members:
            options=self.target_options(i,threshold,start,end)
            if not options:return None
            rows.append((min(hi-t for lo,hi,t in options),i,options))
        calendar=list(busy);result=[]
        for _,i,options in sorted(rows):
            slot=None
            for lo,hi,t in options:
                at=lo
                for a,b in sorted(calendar):
                    if at+t<=a:break
                    if at<b and at+t>a:at=b
                if at+t<=hi:
                    slot=(at,at+t,i);break
            if slot is None:return None
            calendar.append(slot[:2]);result.append(slot)
        return result

    def refresh(self,requests,now,budget):
        started=time.process_time();stamp=now.timestamp();p=self.p
        key=(tuple((r['request_id'],r.get('remaining_count',r['minimum_completed']),tuple(r.get('completed_target_ids',())))
                   for r in requests if r.get('completion_reward',0)>0),int(stamp//300),
             self.events.revision,len(p.history),round(p.scale,4))
        if key==self.last_key:return
        self.last_key=key;self.stamp=stamp;self.options={};self.selected=set()
        self.groups=[];self.urgent_required=set();self.reservations=[];self.truncated=False
        deadline=started+max(.001,budget)
        rows=[]
        from skymath import parse_utc
        for r in requests:
            remaining=int(r.get('remaining_count',r['minimum_completed']))
            reward=float(r.get('completion_reward',0))
            if remaining<=0 or reward<=0:continue
            begin=max(stamp,parse_utc(r['issued_at_utc']).timestamp())
            end=parse_utc(r['deadline_utc']).timestamp()
            if end<=begin:continue
            done=set(r.get('completed_target_ids',[]))
            members=[p.index_of[t] for t in r['target_ids'] if t in p.index_of and t not in done]
            rows.append((end,-reward,r,begin,members,remaining))
        busy=[]
        for end,_,r,begin,members,remaining in sorted(rows):
            if time.process_time()>=deadline:self.truncated=True;break
            threshold=float(r['completion_factor_threshold'])
            available=[]
            for i in members:
                if time.process_time()>=deadline:self.truncated=True;break
                options=self.target_options(i,threshold,begin,end)
                if options:
                    cost=min(t for lo,hi,t in options)
                    last=max(hi-t for lo,hi,t in options)
                    available.append((cost,-bool(p.required[i]),last,i))
            if len(available)<remaining:continue
            available.sort()
            pool=[v[-1] for v in available[:max(remaining,min(12,remaining+4))]]
            best=None
            for subset in itertools.islice(itertools.combinations(pool,remaining),128):
                if time.process_time()>=deadline:self.truncated=True;break
                sequence=self.sequence(subset,threshold,begin,end,busy)
                if sequence:
                    k=(sum(b-a for a,b,i in sequence),max(b for a,b,i in sequence),subset)
                    if best is None or k<best[0]:best=(k,subset,sequence)
            if best is None:continue
            _,subset,sequence=best
            group={'id':r['request_id'],'threshold':threshold,'end':end,'start':begin,
                   'remaining':remaining,'reward':float(r['completion_reward']),
                   'members':set(members),'subset':set(subset),'sequence':sequence}
            self.groups.append(group);self.selected.update(subset)
            self.reservations.extend(sequence);busy.extend((a,b) for a,b,i in sequence)
        # Last-window required obligations use conservative raw bounds and full
        # exposures, never (threshold - previous exposure factor).
        raw=getattr(p,'factor_lower',p.factor)
        candidates=[i for i,required in enumerate(p.required) if required and raw[i]<p.required_threshold]
        candidates.sort(key=lambda i:(p.last_night[i],-p.flux[i],i))
        for i in candidates[:32]:
            if time.process_time()>=deadline:self.truncated=True;break
            options=self.target_options(i,p.required_threshold,stamp,p.survey_end.timestamp())
            if len(options)==1:
                self.urgent_required.add(i);self.selected.add(i)
        self.active=bool(self.groups or self.urgent_required)
        self.cpu=time.process_time()-started

    def guide(self,i,duration,raw):
        value=0.
        for g in self.groups:
            if i in g['subset'] and g['start']<=self.stamp and self.stamp+duration<=g['end']:
                confidence=min(1.,max(0.,(raw/g['threshold']-1.)/.15))
                value+=g['reward']/g['remaining']*confidence
        return value

    def field_adjustment(self,pick,duration,raw,chance=None):
        """Replace member guides with a single group continuation value per field.

        Shared quality error is treated conservatively with a minimum confidence,
        not as independent Bernoulli successes. This is a planning proxy only.
        """
        selected=set(pick.values());adjust=0.
        chance=chance or {f:1. for f in pick}
        probability={i:chance[f] for f,i in pick.items()}
        for i in selected:adjust-=self.guide(i,duration,raw(i))*probability[i]
        after=self.stamp+duration
        for g in self.groups:
            if not g['start']<=self.stamp or after>g['end']:continue
            accomplished=[i for i in selected & g['members'] if raw(i)>=g['threshold']]
            if not accomplished:continue
            conf=min(min(1.,max(0.,(raw(i)/g['threshold']-1.)/.15))*probability[i] for i in accomplished)
            still=max(0,g['remaining']-len(accomplished))
            continuation=None
            if still:
                left=list(g['subset']-set(accomplished))
                # A field can complete an alternative member; replace a reserved
                # member accordingly. Occupancy check is at least two-step.
                left.sort(key=lambda i:(min((t for lo,hi,t in self.target_options(i,g['threshold'],after,g['end'])),default=1e30),i))
                if len(left)>=still:
                    continuation=self.sequence(left[:still],g['threshold'],after,g['end'])
            if not still or continuation:
                future=sum(b-a for a,b,i in continuation) if continuation else 0.
                # Account for extra telescope occupation; all-or-nothing reward
                # is counted once, with finite continuation discount.
                adjust+=g['reward']*conf*(duration/max(duration,duration+future))
        return adjust

    def summary(self):
        return {'groups':len(self.groups),'selected':len(self.selected),'last_window_required':len(self.urgent_required),
                'planning_cpu_seconds':self.cpu,'truncated':self.truncated,
                'reservations':self.reservations[:12],
                'assumptions':'current own quality; public geometric windows and known downtime; finite standalone continuation, not guaranteed completion'}
