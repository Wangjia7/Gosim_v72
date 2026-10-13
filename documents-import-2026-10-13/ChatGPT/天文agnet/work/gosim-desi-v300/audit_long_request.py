"""Post-run truth audit only. Not imported or shipped by the agent."""
from pathlib import Path
from datetime import timedelta
import json,sys,math
r=Path(__file__).resolve().parent;sys.path.insert(0,str(r/'runner'))
from challenge.v4_runner import load_scenario
from challenge.v4_scorer import WeatherTruth,score_target_exposure
from challenge.v4_fiber_map import radec_to_altaz,min_altitude_during
s=load_scenario(r/'cases-v2/long-held/config/v4_scenario.json')
weather=WeatherTruth(s.slots,[e for e in s.events if e.event_type=='instrument_fault'])
req=s.observation_requests[0];targets={t['target_id']:t for t in s.targets};rows=[]
for tid in req['target_ids']:
 target=targets[tid];now=req['issued_at_utc'];best=0;besttime=None
 while now+timedelta(seconds=60)<=req['deadline_utc']:
  # Try longest legal exposure ending within the request. Shrinking to the
  # setting boundary preserves the maximum nonnegative integrated signal.
  duration=min(3600,int((req['deadline_utc']-now).total_seconds()))
  if min_altitude_during(target['ra_deg'],target['dec_deg'],now,now+timedelta(seconds=60),s.config)<30:
   now+=timedelta(seconds=60);continue
  lo,hi=60,duration
  while lo<hi:
   mid=(lo+hi+1)//2
   if min_altitude_during(target['ra_deg'],target['dec_deg'],now,now+timedelta(seconds=mid),s.config)>=30:lo=mid
   else:hi=mid-1
  duration=lo;end=now+timedelta(seconds=duration)
  out=score_target_exposure(target,list(weather.segments(now,end)),s.events,weather,duration,1.0,
    s.score_config,now,lambda t:radec_to_altaz(target['ra_deg'],target['dec_deg'],t,s.site['latitude_deg'],s.site['longitude_deg']),s.site)
  if out.factor>best:best=out.factor;besttime=now.isoformat()
  now+=timedelta(seconds=60)
 rows.append({'target_id':tid,'max_factor_sampled':best,'start_utc':besttime,'feature_flux':target['feature_flux']})
result={'request_id':req['request_id'],'threshold':req['completion_factor_threshold'],'minimum_completed':req['minimum_completed'],
 'sampled_individually_feasible':sum(x['max_factor_sampled']>=req['completion_factor_threshold'] for x in rows),
 'scope':'post-run truth; 60s start grid, perfect fiber placement, no shared telescope capacity; not a rigorous infeasibility proof', 'rows':rows}
(r/'long-request-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
