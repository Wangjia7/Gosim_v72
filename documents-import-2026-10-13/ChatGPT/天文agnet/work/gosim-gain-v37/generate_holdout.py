"""Fixed fresh seeds, official generator; offline inputs only, never uploaded."""
from pathlib import Path
import csv,hashlib,json,shutil,sys
from datetime import date,timedelta
R=Path(__file__).resolve().parent;G=R.parent/'gosim-desi-v300/generator';B=R.parent/'gosim-desi-v300/fixtures/official-config'
sys.path.insert(0,str(G))
from challenge.v4_weather_simulator import generate
from challenge.v4_catalog_generator import generate_catalog
from challenge.v4_observation_requests import generate_requests
from challenge.v4_workflow import validate_bundle
profiles=[('fresh-sparse',4,.08,900,9,.5,True,20261007101,0.),('fresh-dense',10,.16,2600,10,.5,False,20261007102,0.),('fresh-mixed',5,.25,1400,12,.7,True,20261007103,.08),('fresh-long',10,.25,3500,90,.5,True,20261007104,0.)]
rows=[]
for name,side,area,count,days,threshold,stress,seed,gap in profiles:
 card=R/'cases'/name;assert not card.exists();card.mkdir(parents=True)
 for d in ['public','truth','config']:(card/d).mkdir()
 cat=json.loads((G/'challenge/reference/v4/v4_catalog_config.json').read_text());cat['seed']=seed
 cat['targets'].update(total_count=count,n_cluster_centers=30,required_fraction=.12)
 cat['footprint']['total_area_deg2']=500 if name=='fresh-dense' else 2000
 cat['footprint']['component_centers']=[[15,-22],[65,-54],[115,-22]]
 end=(date(2026,11,1)+timedelta(days=days)).isoformat()
 cat['observability'].update(start_date='2026-11-01',end_date=end,minimum_window_seconds=90)
 wx=json.loads((G/'challenge/reference/v4/v4_weather_config.json').read_text());wx['seed']=seed+100000
 wx['survey'].update(start_date='2026-11-01',end_date=end)
 for item in wx['weather_events']['conditions'].values():item.update(count=1,duration_slots=[2,8])
 wx['earthquake']['count']=int(stress);wx['instrument_fault']['count']=int(stress);wx['rocket_launch']['count']=1
 wx['terrain_obstruction']['sector_count']=[0,0];wx['stress_tests']['enabled']=stress
 cp=card/'config/catalog-generation.json';cp.write_text(json.dumps(cat,indent=2)+'\n')
 wp=card/'config/weather-generation.json';wp.write_text(json.dumps(wx,indent=2)+'\n')
 cg=card/'generated-catalog';wg=card/'generated-weather';generate_catalog(cp,cg);generate(wp,wg)
 for f in ['targets.csv','footprint.csv']:shutil.copy2(cg/f,card/'public'/f)
 for f in ['v4_night_calendar.csv','v4_bulletins.jsonl','v4_forecasts.jsonl']:shutil.copy2(wg/f,card/'public'/f)
 for f in ['v4_slots.csv','v4_weather_truth.csv','v4_events.csv','v4_earthquake_effects.csv','v4_stress_events.csv']:
  if (wg/f).exists():shutil.copy2(wg/f,card/'truth'/f)
 fiber=json.loads((B/'v4_fiber_config.json').read_text());fiber['field'].update(n_fibers=side*side,fiber_area_deg2=area,gap_deg=gap)
 (card/'config/v4_fiber_config.json').write_text(json.dumps(fiber,indent=2)+'\n')
 score=json.loads((B/'v4_score_config.json').read_text());score['required']['observed_factor_threshold']=threshold;score['observation_requests']['completion_factor_threshold']=threshold
 (card/'config/v4_score_config.json').write_text(json.dumps(score,indent=2)+'\n')
 scenario=json.loads((B/'v4_scenario.json').read_text());scenario['name']=name;scenario['task_card']={'card_id':name,'scenario_slug':name,'phase':'v37-fixed-holdout'};scenario['stress']['enabled']=stress
 if stress:scenario['stress']['stress_events_csv']='../truth/v4_stress_events.csv'
 (card/'config/v4_scenario.json').write_text(json.dumps(scenario,indent=2)+'\n')
 generate_requests(seed=seed+900000,targets_csv=card/'public/targets.csv',night_calendar_csv=card/'public/v4_night_calendar.csv',slots_csv=card/'truth/v4_slots.csv',site=scenario['site'],minimum_altitude_deg=scenario['minimum_altitude_deg'],output_path=card/'truth/v4_observation_requests.jsonl',settings={'count':2,'window_nights':1,'targets_per_request':8,'minimum_completion_fraction':.75,'completion_factor_threshold':threshold,'minimum_feature_flux':.0625},flux_zero_point=score['flux_zero_point'],exposure_zero_point_seconds=score['exposure_zero_point_seconds'],min_duration_seconds=60,max_duration_seconds=3600)
 validate_bundle(card)
 rows.append({'name':name,'seed':seed,'targets':count,'nights':days,'fibres':side*side,'area':area,'gap':gap,'threshold':threshold,'stress':stress,'hashes':{str(p.relative_to(card)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['public','truth','config'] for p in sorted((card/d).rglob('*')) if p.is_file()}})
 print(name,'generated and validated',flush=True)
(R/'case-manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
