"""Requested/result facts and recomputable single-exposure credit.
No hidden state, stacking, inferred actual fibre coordinates, or causal labels.
Serialized facts stay unchanged when a resync retracts their scientific credit.
"""
import json
import math
from collections import deque

class Inspection:
    def __init__(self, planner):
        self.p=planner
        self.facts={}
        self.invalid=set()
        self.recent=deque(maxlen=8)
        self.best={}
        self.raw={}
        self.gain=0.
        self.credits={}
        self.rejections=0
        self.last_gate='UNKNOWN'

    def gate(self,result):
        if not result or result.get('action')!='observe':return result
        # A repeated response must not be attributed to the next pending exposure.
        index=result.get('observe_index')
        if isinstance(index,int) and not isinstance(index,bool) and index in self.facts:
            self.last_gate='DUPLICATE';return None
        hits=result.get('hits')
        if not isinstance(index,int) or isinstance(index,bool) or not isinstance(hits,list):
            self.rejections+=1;self.last_gate='UNKNOWN';return None
        seen=set()
        for hit in hits:
            if not isinstance(hit,dict):
                self.rejections+=1;self.last_gate='FAIL';return None
            target=hit.get('target_id');score=hit.get('score')
            if (not isinstance(target,str) or target not in self.p.pending or target in seen
                or isinstance(score,bool) or not isinstance(score,(int,float))
                or not math.isfinite(score) or score<0):
                self.rejections+=1;self.last_gate='FAIL';return None
            i=self.p.index_of[target]
            cap=self.p.weight[i]*max(self.p.multipliers[self.p.pending_program],self.p.mismatch)
            if score>cap+2e-4:
                self.rejections+=1;self.last_gate='FAIL';return None
            seen.add(target)
        self.last_gate='PASS';return result

    def record(self,result,now,weather):
        weather=[n for n in weather if n[0] in {'rain','storm','overcast','haze','cold_snap','earthquake'}]
        p=self.p;index=result['observe_index'];program=p.pending_program
        declared=p.multipliers[program]
        requested=[];measurements=[];predicted_gain=0.;realized_gain=0.
        hit={h['target_id']:float(h['score']) for h in result['hits']}
        for target,prediction in p.pending.items():
            i=p.index_of[target];before=p.cur[i]*p.weight[i]
            requested.append({'target_id':target,'fiber':prediction.get('fiber'),
                'predicted_factor':prediction.get('pred'),'model':prediction.get('model')})
            raw_prediction=prediction.get('pred')
            predicted=None
            if raw_prediction is not None:
                # Public band model is a prediction, not a realized program-match fact.
                predicted_band=p._band(prediction['band_model']*p.scale)
                multiplier=declared if predicted_band==program else p.mismatch
                predicted=p.weight[i]*min(1.,max(0.,raw_prediction))*multiplier
                predicted_gain+=max(0.,predicted-before)*prediction.get('p',1.)
            score=hit.get(target);reasons=[];bounds=None;certified=None;gain=0.
            if score is None:
                reasons.append('FIBER_MISS_CAUSE_UNKNOWN')
            else:
                gain=max(0.,score-before);realized_gain+=gain
                feasible=[min(1.,max(0.,score-.0000005)/(p.weight[i]*m))
                    for m in {declared,p.mismatch} if m>0 and score<=p.weight[i]*m+2e-4]
                if feasible:
                    upper=[min(1.,(score+.0000005)/(p.weight[i]*m)) for m in {declared,p.mismatch}
                        if m>0 and score<=p.weight[i]*m+2e-4]
                    bounds=[min(feasible),max(upper)]
                old_raw=getattr(p,'factor_lower',p.factor)[i]
                certified=max(old_raw,bounds[0])>=p.required_threshold if bounds and p.required[i] else None
                if gain==0:reasons.append('ZERO_MARGINAL_GAIN')
                if p.required[i] and certified is False:reasons.append('BELOW_COMPLETION_THRESHOLD')
                if abs(score/p.weight[i]-p.mismatch)<2e-4 and abs(declared-p.mismatch)>2e-4:
                    reasons.append('PROGRAM_MISMATCH_CANDIDATE')
                if score==0:reasons.append('ZERO_SCORE_CAUSE_UNKNOWN')
                if any(n[0]=='earthquake' or n[1]=='ALL' for n in weather):
                    reasons.append('WEATHER_OR_QUAKE_CONFOUNDED')
                elif not prediction.get('dir_clean',False):reasons.append('DIRECTIONAL_CONDITION_CONFOUNDED')
            measurements.append({'target_id':target,'fiber':prediction.get('fiber'),
                'target_class':p.target_classes[i] if hasattr(p,'target_classes') else 'unknown',
                'required':bool(p.required[i]),'score':score,'score_before':before,
                'science_gain':gain,'raw_factor_bounds':bounds,'required_certified':certified,'realized_program_match':'UNKNOWN',
                'judgement':'UNKNOWN' if score is None or bounds is None else 'WARN' if reasons else 'PASS',
                'reason_codes':reasons})
        night=p.nights[p.pending_night]
        phase=(now.timestamp()-p.pending_duration-night[0].timestamp())/max(1.,(night[1]-night[0]).total_seconds())
        fact={'night_phase':'early' if phase<1/3 else 'middle' if phase<2/3 else 'late','id':index,'utc':now.isoformat(),'requested':{'pointing':getattr(p,'pending_cmd',None),
            'program':program,'duration_seconds':p.pending_duration,'assignments':requested},
            'realized':{'hits':result['hits'],'actual_fiber_positions':None,'weather_notices':weather},
            'measurements':measurements,'predicted_science_gain':predicted_gain,
            'realized_science_gain':realized_gain,
            'science_gain_efficiency':realized_gain/predicted_gain if predicted_gain>1e-8 else None,
            'hit_efficiency':len(hit)/len(requested) if requested else None,
            'science_gain_per_second':realized_gain/p.pending_duration if p.pending_duration>0 else None,
            'source':'JSONL last_result + own pending prediction; no actual fibre positions/raw factors returned'}
        self.facts[index]=json.dumps(fact,separators=(',',':'),allow_nan=False)
        self.recent.append(index);self.gain+=realized_gain
        self.credits[index]=realized_gain
        for row in measurements:
            if row['score'] is None:continue
            target=row['target_id'];self.best[target]=max(self.best.get(target,0.),row['score'])
            if row['raw_factor_bounds']:self.raw[target]=max(self.raw.get(target,0.),row['raw_factor_bounds'][0])

    def resync(self,messages):
        for message in messages:
            if message.get('record_type')!='state_resync':continue
            window=message.get('invalidated_window',{})
            start=window.get('action_index_start',0);end=window.get('action_index_end_exclusive',0)
            self.invalid.update(i for i in self.facts if start<=i<end)
            self.best={};self.raw={};self.credits={}
            for index,text in self.facts.items():
                if index in self.invalid:continue
                credit=0.
                for row in json.loads(text)['measurements']:
                    if row['score'] is None:continue
                    target=row['target_id']
                    credit+=max(0.,row['score']-self.best.get(target,0.))
                    self.best[target]=max(self.best.get(target,0.),row['score'])
                    if row['raw_factor_bounds']:self.raw[target]=max(self.raw.get(target,0.),row['raw_factor_bounds'][0])
                self.credits[index]=credit
            # Engine snapshot is the current scientific-score authority.
            self.best={row['target_id']:float(row['best_score']) for row in message.get('best_scores',[])}
            self.raw={t:v for t,v in self.raw.items() if self.best.get(t,0)>0}
            self.gain=sum(self.best.values())
            self.recent=deque((i for i in self.facts if i not in self.invalid),maxlen=8)

    def summary(self):
        rows=[json.loads(self.facts[i]) for i in self.recent]
        for row in rows:row['credited_science_gain']=self.credits[row['id']]
        # Recorded before/after measurements describe the original visit. Resync
        # replays credit separately; never rewrite the original measurements.
        populations={}
        for visit in rows:
            duration=visit['requested']['duration_seconds']
            bucket='short' if duration<=600 else 'medium' if duration<=1800 else 'long'
            weather=tuple(sorted({n[0] for n in visit['realized']['weather_notices']}))
            for row in visit['measurements']:
                key=(visit['requested']['program'],row['target_class'],row['required'],row['fiber'],bucket,weather,visit['night_phase'])
                stat=populations.setdefault(key,{'assigned':0,'hits':0,'original_measured_science_gain':0.,'reasons':{}})
                stat['assigned']+=1;stat['hits']+=row['score'] is not None;stat['original_measured_science_gain']+=row['science_gain']
                for reason in row['reason_codes']:stat['reasons'][reason]=stat['reasons'].get(reason,0)+1
        groups=[{'program':k[0],'target_class':k[1],'required':k[2],'fiber':k[3],
            'duration_group':k[4],'weather_notices':k[5],'night_phase':k[6],**v} for k,v in populations.items()]
        return {'recent_populations':groups[:32],'population_count':len(groups),'population_scope':'last 8 valid exposures',
            'schema':'realized-inspection-v1','valid_exposures':len(self.facts)-len(self.invalid),
            'invalidated_exposures':len(self.invalid),'gate':self.last_gate,'rejected_results':self.rejections,
            'credit_rule':'max single-exposure score; independent conservative raw maximum; no stacking',
            'recent_visits':[{**{k:v for k,v in row.items() if k not in ('requested','realized','measurements')},
                'measurements':row['measurements'][:16],'measurement_count':len(row['measurements']),
                'requested':{**row['requested'],'assignments':row['requested']['assignments'][:16]},
                'realized':{**row['realized'],'hits':row['realized']['hits'][:16]},
                'predicted_measurement_is_not_realized':True} for row in rows],
            'best_score_sum':sum(self.best.values()),'replayed_visit_credit_sum':sum(self.credits.values()),
            'credit_scope':'current valid visit credit replay; immutable measured deltas describe original planning state; engine best-score snapshot remains authoritative',
            'missing_data':'UNKNOWN; misses/program candidates do not identify causes; efficiency denominator is model prediction'}
