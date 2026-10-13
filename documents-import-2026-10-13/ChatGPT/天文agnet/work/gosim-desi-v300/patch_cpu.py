from pathlib import Path
p=Path('work/gosim-desi-v300/agent/planner.py');s=p.read_text()
a=s.index('        @lru_cache(maxsize=None)\n        def gain');b=s.index('        def quick(',a)
s=s[:a]+'''        @lru_cache(maxsize=None)
        def physical_gain(i,T):
            alt,az,m0,m1,up,mult = full(i)
            if up < T: return None
            model=m0+(m1-m0)*min(1.0,T/3600.0)
            reach=min(1.0,self.flux[i]*T*model*scale/self.f0t0)
            discount=1.0
            if reach<PARTIAL_DONE and self.planned[i] and self.last_night[i]-night_index>=PARTIAL_NIGHTS:
                discount=PARTIAL_DISCOUNT
            bonus=0.0
            if self.required[i] and self.factor[i]<self.required_threshold:
                raw=self.flux[i]*T*model*self.scale/self.f0t0/self.required_threshold*self.req_calib.get(i,1.0)
                bonus=self.required_value*min(1.0,max(0.0,(raw-REQ_P_LO)/(REQ_P_HI-REQ_P_LO)))
                target_best=self.best_future_model(i,night_index) if REQ_CALENDAR else self.ideal_model[i]
                if REQ_TIMING and model<REQ_TIMING*target_best and self.last_night[i]-night_index>=REQ_TIMING_NIGHTS:
                    bonus*=REQ_TIMING_DISCOUNT
                if self.bad_forecast and self.last_night[i]-night_index>=REQ_TIMING_NIGHTS:
                    bonus*=FORECAST_DISCOUNT
                needed=self.required_threshold*self.f0t0/max(1e-8,self.flux[i]*model*scale)
                _,windows,_=self.opportunities.remaining(i,now.timestamp(),duration=needed)
                if windows<=1:bonus*=2.0
            if i in self.request_legs:
                raw=self.flux[i]*T*model*scale/self.f0t0
                bonus+=request_gain(self.request_legs[i],now.timestamp(),T,raw,self.opportunities,i)
            return reach,self._band(model*band_scale),discount,bonus,mult

        @lru_cache(maxsize=None)
        def gain(i,T,program):
            physical=physical_gain(i,T)
            if physical is None:return 0.0
            reach,band,discount,bonus,mult=physical
            m=self.multipliers[program] if band==program else self.mismatch
            science=self.weight[i]*max(0.0,shaped(reach*m)-shaped(self.cur[i]))*discount
            return (science+bonus)*mult

''' +s[b:]
s=s.replace('for i in pool[:min(40, len(pool))]:','for i in pool[:min(8, len(pool))]:')
s=s.replace('                trials = batch.evaluate(c_alt, c_az)','''                found,rate = batch.best(c_alt,c_az,lam)
                best_rate[0] = max(best_rate[0],rate)
                return found''')
p.write_text(s)
