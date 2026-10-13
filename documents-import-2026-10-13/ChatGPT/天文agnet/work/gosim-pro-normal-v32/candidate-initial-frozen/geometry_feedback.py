"""Bounded online alt/az hypotheses from assignments and published hit IDs.

Residuals trigger fitting; independent future exposures gate adoption. All-miss
batches cannot establish a correction. Rollback compares hypotheses on the same
new commands. No score, weather, actual fibre or hidden offset enters this fit.
"""
from collections import deque
import os
from skymath import tangent_offsets


class GeometryFeedback:
    def __init__(self, grid, enabled=False):
        self.grid, self.enabled = grid, enabled
        self.bound = min(.20, grid.glass*.35)
        self.step = self.bound/8
        self.cells = [(a*self.step,z*self.step) for a in range(-8,9) for z in range(-8,9)]
        self.rows = deque(maxlen=192)
        self.offset = (0.,0.)
        self.proposal = None
        self.validation = []
        self.version = 0
        self.exposures = 0
        self.total_assigned = self.total_hits = 0
        self.next_fit_exposure = 4
        self.fit_attempts = 0
        self.previous_offset = None
        self.monitor = deque(maxlen=4)
        self.last_pause = None
        self.patient_validation = os.environ.get('GEOMETRY_PATIENT_VALIDATION','1')=='1'

    def hit(self, row, offset):
        alt,az,fiber,center_alt,center_az,_=row
        a=center_alt+offset[0]
        if not 0 <= a <= 90:return False
        xy=tangent_offsets(alt,az,a,(center_az+offset[1])%360)
        return xy is not None and self.grid.classify(*xy)[0] == fiber

    def loss(self, rows, offset):
        return sum((4 if row[-1] else 1) for row in rows if self.hit(row,offset)!=row[-1])

    def pause(self, reason):
        self.offset=(0.,0.);self.version+=1
        self.proposal=None;self.validation=[];self.previous_offset=None;self.monitor.clear()
        self.rows.clear();self.next_fit_exposure=self.exposures+8;self.last_pause=reason

    def record(self, pending, hits):
        rows=[]
        for target,pred in pending.items():
            g=pred.get('geometry')
            if not g or not g['altitude_feasible']:continue
            rows.append((pred['alt'],pred['az'],g['fiber'],g['command_alt'],g['command_az'],target in hits))
        if not rows:return None
        self.exposures+=1;self.total_assigned+=len(rows);self.total_hits+=sum(x[-1] for x in rows)
        self.rows.extend(rows)
        result={'assigned':len(rows),'hit_ids':sum(x[-1] for x in rows),
                'unmatched_assignments':sum(not x[-1] for x in rows),
                'source':'assigned fiber and published hit IDs; no actual fiber or offset supplied'}
        if not self.enabled:return {**result,**self.summary()}
        if self.previous_offset is not None:
            self.monitor.append(rows)
            monitored=[x for batch in self.monitor for x in batch]
            if len(self.monitor)>=3 and len(monitored)>=48 and sum(x[-1] for x in monitored)>=24:
                current=self.loss(monitored,self.offset);prior=self.loss(monitored,self.previous_offset)
                if current-prior>=6 and prior<=max(3,.06*len(monitored)):
                    rejected=self.offset;self.offset=self.previous_offset;self.version+=1
                    self.previous_offset=None;self.monitor.clear();self.proposal=None;self.validation=[]
                    self.rows.clear();self.rows.extend(monitored);self.next_fit_exposure=self.exposures+8
                    result['calibration_rollback']={'rejected_offset':rejected,'restored_offset':self.offset,
                        'monitor_rows':len(monitored),'current_loss':current,'prior_loss':prior}
                    return {**result,**self.summary()}
        if self.proposal is not None:
            self.validation.append(rows)
            validation=[x for batch in self.validation for x in batch]
            ready=len(self.validation)>=2 and len(validation)>=24
            reference=self.loss(validation,self.offset);candidate=self.loss(validation,self.proposal)
            supported=sum(x[-1] for x in validation)>=12
            contradicted=ready and (not supported or candidate>max(2,.05*len(validation)))
            adopted=ready and supported and reference-candidate>=3 and candidate<=max(2,.05*len(validation))
            expired=len(self.validation)>=6 if self.patient_validation else ready
            if adopted or contradicted or expired:
                if adopted:
                    self.previous_offset=self.offset;self.offset=self.proposal;self.version+=1;self.monitor.clear()
                    result['calibration_update']={'offset_alt_deg':self.offset[0],'offset_az_deg':self.offset[1],
                        'validation_rows':len(validation),'validation_exposures':len(self.validation),
                        'old_loss':reference,'new_loss':candidate}
                else:
                    result['calibration_rejected']={'validation_rows':len(validation),
                        'validation_exposures':len(self.validation),'expired':expired,
                        'old_loss':reference,'candidate_loss':candidate,'positive_support':supported}
                self.proposal=None;self.validation=[];self.next_fit_exposure=self.exposures+8
            elif ready:
                result['calibration_deferred']={'validation_rows':len(validation),
                    'validation_exposures':len(self.validation),'old_loss':reference,'candidate_loss':candidate,
                    'reason':'candidate consistent but insufficient discriminating evidence'}
            return {**result,**self.summary()}
        if self.exposures<self.next_fit_exposure or len(self.rows)<48 or sum(x[-1] for x in self.rows)<24:
            return {**result,**self.summary()}
        base=self.loss(self.rows,self.offset)
        if base<6:return {**result,**self.summary()}
        self.fit_attempts+=1;self.next_fit_exposure=self.exposures+8
        scored=[(self.loss(self.rows,c),c) for c in self.cells]
        best=min(x[0] for x in scored)
        credible=[c for loss,c in scored if loss==best]
        if base-best<6 or best>max(3,.06*len(self.rows)):return {**result,**self.summary()}
        if any(max(c[k] for c in credible)-min(c[k] for c in credible)>.08 for k in (0,1)):
            return {**result,**self.summary()}
        fit=tuple(sum(c[k] for c in credible)/len(credible) for k in (0,1))
        if self.loss(self.rows,fit)>best+1:return {**result,**self.summary()}
        self.proposal=fit
        result['proposal']={'offset_alt_deg':fit[0],'offset_az_deg':fit[1], 'training_rows':len(self.rows),
                            'baseline_loss':base,'candidate_loss':best,'status':'awaiting subsequent exposure validation'}
        return {**result,**self.summary()}

    def command(self, desired_alt, desired_az):
        alt=desired_alt-self.offset[0]
        if not 0<=alt<=90:return desired_alt,desired_az,False
        return alt,(desired_az-self.offset[1])%360,True

    def summary(self):
        return {'geometry_version':self.version,'calibration_enabled':self.enabled,
                'offset_alt_deg_estimate':self.offset[0],'offset_az_deg_estimate':self.offset[1],
                'offset_bound_deg':self.bound,'evidence_rows':len(self.rows),'exposures':self.exposures,
                'total_assigned':self.total_assigned,'total_hits':self.total_hits,
                'pending_validation':self.proposal is not None,'fit_attempts':self.fit_attempts,
                'next_fit_exposure':self.next_fit_exposure,'last_pause':self.last_pause,
                'patient_validation':self.patient_validation,
                'estimate_kind':'bounded validated hypothesis, not truth'}
