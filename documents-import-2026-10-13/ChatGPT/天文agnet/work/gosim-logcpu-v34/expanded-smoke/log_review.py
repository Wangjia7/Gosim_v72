"""Incremental audit of own exposure logs, independent of science completion.
Store compact per-exposure evidence; resync removes invalid entries. Periodic
checkpoints compare recent and earlier independent exposures, and provide a
bounded, source-labelled digest to the anomaly reviewer. Never read engine files.
"""
from collections import deque
from statistics import median

WEATHER={'rain','storm','overcast','haze','cold_snap'}

class ObservationReview:
    def __init__(self,planner):
        self.p=planner
        self.records={}
        self.recent=deque(maxlen=64)
        self.groups={}
        self.valid_count=0
        self.invalidated_count=0
        self.epoch=0
        self.checkpoints=0
        self.last_checkpoint_count=-1
        self.last_night=None
        self.digest={}
    def record(self,result,now,notices=()):
        p=self.p
        if not result or result.get('action')!='observe' or not p.pending:return False
        index=int(result.get('observe_index',len(self.records)))
        if index in self.records:return False
        hits={h['target_id']:float(h['score']) for h in result.get('hits',[])}
        program=p.pending_program
        declared=p.multipliers[program]
        multipliers=(declared,p.mismatch)
        group={};ratios=[]
        classes=getattr(p,'target_classes',None)
        closed=bool(hits) and not any(s>0 for s in hits.values())
        weather=sorted({k for k,d in set(getattr(p,'pending_notices',()))|set(notices)
            if k in WEATHER or k=='earthquake'})
        duration=p.pending_duration
        bucket='short' if duration<=600 else 'medium' if duration<=1800 else 'long'
        for target,prediction in p.pending.items():
            i=p.index_of[target]
            name=classes[i] if classes else 'unknown'
            key=(name,program,bucket)
            count=group.setdefault(key,[0,0,0,0])
            count[0]+=1
            score=hits.get(target)
            if score is None:count[2]+=1;continue
            count[1]+=1
            if score<=0:count[3]+=1;continue
            expected=min(1.,max(0.,float(prediction.get('pred',0.))))
            clean=prediction.get('dir_clean',False)
            seen=score/p.weight[i]
            saturated=abs(seen-declared)<2e-4 or abs(seen-p.mismatch)<2e-4
            if clean and not saturated and expected>1e-6:
                feasible=[min(1.,score/(p.weight[i]*m)) for m in multipliers
                    if m>0 and score<=p.weight[i]*m+2e-4]
                if feasible:
                    public_factor=p.flux[i]*duration*float(prediction.get('model',0.))/p.f0t0
                    if public_factor>1e-8:
                        ratios.append((min(feasible)/public_factor,max(feasible)/public_factor))
        row={'id':index,'utc':now.isoformat(),'night':p.pending_night,'epoch':self.epoch,
            'duration':duration,'program':program,'assigned':len(p.pending),'hits':len(hits),
            'missed':sum(c[2] for c in group.values()),'zero':sum(c[3] for c in group.values()),
            'closed':closed,'weather':weather,'clean_samples':len(ratios),
            'ratio_bounds':(median(r[0] for r in ratios),median(r[1] for r in ratios)) if ratios else None,
            'groups':group}
        self.records[index]=row;self.valid_count+=1;self.recent.append(row)
        self._add_groups(group,1)
        return True
    def _add_groups(self,groups,sign):
        for key,values in groups.items():
            total=self.groups.setdefault(key,[0,0,0,0])
            for k,value in enumerate(values):total[k]+=sign*value
    def invalidate(self,messages):
        changed=False
        for message in messages:
            if message.get('record_type')!='state_resync':continue
            window=message.get('invalidated_window',{})
            start=int(window.get('action_index_start',0));end=int(window.get('action_index_end_exclusive',0))
            for index,row in self.records.items():
                if start<=index<end and not row.get('invalid'):
                    row['invalid']=True;self._add_groups(row['groups'],-1)
                    self.valid_count-=1;self.invalidated_count+=1;changed=True
        if changed:
            self.recent=deque((r for r in self.records.values() if not r.get('invalid') and r['epoch']==self.epoch),maxlen=64)
            self.digest={};self.last_checkpoint_count=-1
        return changed
    def repaired(self):
        self.epoch+=1;self.recent.clear();self.digest={};self.last_checkpoint_count=-1
    def checkpoint(self,now,force=False):
        night=self.p.current_night(now)
        night_id=night[0] if night else None
        due=force or night_id!=self.last_night or self.valid_count-self.last_checkpoint_count>=8
        if not due:return False
        self.last_night=night_id;self.last_checkpoint_count=self.valid_count;self.checkpoints+=1
        rows=list(self.recent);last=rows[-8:];old=rows[-24:-8]
        assigned=sum(r['assigned'] for r in last if not r['closed'])
        missed=sum(r['missed'] for r in last if not r['closed'])
        clean=[r for r in last if r['ratio_bounds'] and not r['weather']]
        prior=[r for r in old if r['ratio_bounds'] and not r['weather']]
        cue='retain'
        if len(last)>=3 and assigned>=32 and missed/assigned>.15:cue='geometry_candidate'
        if any(r['weather'] for r in last):cue='weather_or_earthquake_confounded'
        if len(clean)>=4 and len(prior)>=4 and sum(r['clean_samples'] for r in clean)>=8:
            if median(r['ratio_bounds'][1] for r in clean)<.8*median(r['ratio_bounds'][0] for r in prior):cue='throughput_candidate'
        factor=getattr(self.p,'factor_lower',self.p.factor)
        missing=[i for i in range(len(self.p.ids)) if self.p.required[i] and factor[i]<self.p.required_threshold]
        by_class=[{'target_class':k[0],'program':k[1],'duration_group':k[2],
            'assigned':v[0],'hit':v[1],'missed':v[2],'zero_score':v[3]}
            for k,v in sorted(self.groups.items()) if v[0]>0]
        self.digest={'schema':'own-exposure-review-v1','checkpoint':self.checkpoints,'epoch':self.epoch,
            'valid_exposures':self.valid_count,'invalidated_exposures':self.invalidated_count,
            'cue':cue,'recent_miss_fraction':round(missed/max(1,assigned),4),
            'recent_independent_clean_exposures':len(clean),'previous_independent_clean_exposures':len(prior),
            'required_unconfirmed':len(missing),'required_examples':[self.p.ids[i] for i in missing[:8]],
            'by_class_program_duration':by_class[:60],
            'recent_exposures':[{k:v for k,v in r.items() if k not in ('groups','invalid')} for r in last],
            'ratio_definition':'unsaturated raw-factor bounds / public model factor, before learned throughput scaling',
            'limitations':'raw/program ratios are intervals; cue alone cannot authorize a fault report or certify completion'}
        return True
    def summary(self):
        return self.digest
