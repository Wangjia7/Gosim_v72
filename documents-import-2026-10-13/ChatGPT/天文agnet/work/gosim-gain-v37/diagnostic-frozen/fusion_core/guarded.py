"""Local replay ledger and exact public request windows around the incoming search.
Only own observation results and authoritative public resync messages are consumed.
"""
import copy
from .planner import Planner as SearchPlanner, REQUEST_MULT, REQ_P_LO, REQ_P_HI
from .skymath import parse_utc
from official_pro.opportunities import Opportunities

class Planner(SearchPlanner):
    def __init__(self, init, log=lambda _:None):
        # Required values exist before the superclass's initialization routines.
        self.required_threshold=float(init['scoring']['required']['observed_factor_threshold'])
        self.required_bonus=80.*float(init['scoring']['required']['penalty_per_missing'])/50.
        self.required_safe=min(1.,self.required_threshold+.12)
        super().__init__(init,log)
        self.initial=copy.deepcopy(init)
        columns=init['targets']['columns']
        self.target_classes=[str(r[columns.index('target_class')]) for r in init['targets']['rows']]
        self.factor_lower=[0.]*len(self.ids)
        self.history=[]
        self.invalidated=set()
        self.seen_results=set()
        self.calibration_epoch=0
        self.operator_priorities=set()
        self.requests=[]
        self.request_legs={}
        self.opportunities=Opportunities(self)

    def value(self,i):
        return super().value(i)*(1.5 if i in self.operator_priorities else 1.)

    def forget_quality_history(self):
        super().forget_quality_history()
        self.calibration_epoch+=1

    def on_result(self,result,now,hours):
        self.exposure_r=None;self.exposure_bounds=None;self.exposure_closed=False;self.exposure_meta=None
        if not result or result.get('action')!='observe':return
        index=int(result.get('observe_index',len(self.history)))
        if index in self.seen_results or not self.pending:return
        record={'index':index,'pending':copy.deepcopy(self.pending),'program':self.pending_program,
            'duration':self.pending_duration,'cmd':self.pending_cmd,'night':self.pending_night,
            'notices':set(self.pending_notices),'result':copy.deepcopy(result),
            'now':now,'hours':hours,'epoch':self.calibration_epoch}
        self.seen_results.add(index)
        super().on_result(result,now,hours)
        # Program ambiguity cannot increase this conservative, independent raw maximum.
        possible=max(self.multipliers[record['program']],self.mismatch)
        for hit in result.get('hits',[]):
            i=self.index_of.get(hit['target_id'])
            if i is None:continue
            lower=min(1.,max(0.,float(hit['score'])-.0000005)/(self.weight[i]*possible))
            self.factor_lower[i]=max(self.factor_lower[i],lower)
        self.history.append(record)

    def _resync(self,message):
        invalid=set(self.invalidated)
        window=message.get('invalidated_window',{})
        invalid.update(range(int(window.get('action_index_start',0)),int(window.get('action_index_end_exclusive',0))))
        history=self.history
        rebuilt=type(self)(self.initial,log=self.log)
        epoch=0
        for row in history:
            if row['index'] in invalid:continue
            if row['epoch']!=epoch:
                SearchPlanner.forget_quality_history(rebuilt)
                epoch=row['epoch']
            rebuilt.pending=copy.deepcopy(row['pending'])
            rebuilt.pending_program=row['program'];rebuilt.pending_duration=row['duration']
            rebuilt.pending_cmd=row['cmd'];rebuilt.pending_night=row['night'];rebuilt.pending_notices=row['notices']
            rebuilt.on_result(row['result'],row['now'],row['hours'])
        if epoch!=self.calibration_epoch:SearchPlanner.forget_quality_history(rebuilt)
        best={r['target_id']:float(r['best_score']) for r in message.get('best_scores',[])}
        for i,target in enumerate(self.ids):
            score=best.get(target,0.)
            rebuilt.cur[i]=score/self.weight[i]
            if score<=0:rebuilt.factor[i]=rebuilt.factor_lower[i]=0.
        # Keep the historical ledger including invalid entries for future loss windows.
        rebuilt.history=history;rebuilt.invalidated=invalid;rebuilt.seen_results=set(self.seen_results)
        rebuilt.calibration_epoch=self.calibration_epoch
        for name in ('events','obligations','runtime_health'):
            if hasattr(self,name):setattr(rebuilt,name,getattr(self,name))
        for name in ('pending','pending_program','pending_duration','pending_cmd','pending_night','pending_notices',
                     'fast_level','deep','search_scale','cpu_turn_budget','bad_forecast','operator_priorities','extra_avoid','terrain','notices'):
            setattr(rebuilt,name,getattr(self,name))
        rebuilt.vcache=None
        rebuilt.exposure_r=None;rebuilt.exposure_bounds=None;rebuilt.exposure_meta=None;rebuilt.exposure_closed=False
        self.__dict__.update(rebuilt.__dict__)
        # Opportunities holds a planner reference; after transplant it must follow this instance.
        self.opportunities=Opportunities(self)
        self.log(f'fusion: replayed {len(history)-len([r for r in history if r["index"] in invalid])} valid exposures')

    def on_requests(self,requests,now=None):
        old=self.request_bonus
        self.request_bonus={};self.request_threshold={};self.requests=[];self.request_legs={}
        stamp=(now or self.nights[0][0]).timestamp()
        for request in requests:
            remaining=int(request.get('remaining_count',request['minimum_completed']))
            if remaining<=0:continue
            start=parse_utc(request.get('issued_at_utc',self.nights[0][0].isoformat())).timestamp()
            end=parse_utc(request['deadline_utc']).timestamp()
            if stamp<start or end-stamp<self.min_exposure:continue
            completed=set(request.get('completed_target_ids',[]))
            indices=[self.index_of[t] for t in request['target_ids'] if t not in completed and t in self.index_of]
            indices=[i for i in indices if self.opportunities.remaining(i,stamp,end,self.min_exposure)[1]>0]
            if len(indices)<remaining:continue
            row={**request,'remaining':remaining,'start':start,'end':end,'indices':indices}
            self.requests.append(row)
            for i in indices:
                self.request_legs.setdefault(i,[]).append(row)
                self.request_bonus[i]=self.request_bonus.get(i,0.)+REQUEST_MULT*float(row['completion_reward'])/remaining
                self.request_threshold[i]=max(self.request_threshold.get(i,0.),float(row['completion_factor_threshold']))
                if self.hmax[i]>0 and i not in self.active:self.active.append(i)
        self.vdirty.update(old);self.vdirty.update(self.request_bonus)

    def request_value(self,i,T,model,stamp):
        joint=getattr(self,'obligations',None)
        managed={g['id'] for g in joint.groups} if joint and joint.active else set()
        result=joint.guide(i,T,self.flux[i]*T*model*self.scale/self.f0t0) if managed else 0.
        for row in self.request_legs.get(i,[]):
            if row['request_id'] in managed:continue
            if not row['start']<=stamp or stamp+T>row['end']:continue
            threshold=max(1e-6,float(row['completion_factor_threshold']))
            raw=self.flux[i]*T*model*self.scale/self.f0t0/threshold
            probability=min(1.,max(0.,(raw-REQ_P_LO)/(REQ_P_HI-REQ_P_LO)))
            result+=REQUEST_MULT*float(row['completion_reward'])/row['remaining']*probability
        return result
