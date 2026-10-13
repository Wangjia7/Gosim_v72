"""Offline question-setter matrix. Truth is never packaged in the upload project."""
from pathlib import Path
import csv, hashlib, json, shutil, sys
ROOT=Path(__file__).resolve().parent
ENGINE=ROOT/'generator'
sys.path.insert(0,str(ENGINE))
from challenge.v4_weather_simulator import generate
from challenge.v4_catalog_generator import generate_catalog
from challenge.v4_observation_requests import generate_requests
from challenge.v4_workflow import validate_bundle
BASE=ROOT/'fixtures'
profiles=[('long-held',10,.16,6000,180,.5,True,202611163,'heldout-long')]
manifest=[]
for name,side,area,count,days,threshold,stress,seed,split in profiles:
 card=ROOT/'cases-v2'/name;card.mkdir(parents=True,exist_ok=True)
 for directory in ('public','truth','config'):(card/directory).mkdir(exist_ok=True)
 cat=json.loads((ENGINE/'challenge/reference/v4/v4_catalog_config.json').read_text())
 cat['seed']=seed;cat['targets']['total_count']=count;cat['targets']['n_cluster_centers']=30
 cat['targets']['required_fraction']=.12
 cat['footprint']['total_area_deg2']=500 if name.startswith('dense') else 2000
 cat['footprint']['component_centers']=[[15,-22],[65,-54],[115,-22]]
 cat['observability']['start_date']='2026-11-01'
 from datetime import date,timedelta
 end=(date(2026,11,1)+timedelta(days=days)).isoformat()
 cat['observability']['end_date']=end
 cat['observability']['minimum_window_seconds']=90
 weather=json.loads((ENGINE/'challenge/reference/v4/v4_weather_config.json').read_text())
 weather['seed']=seed+100000
 weather['survey'].update(start_date='2026-11-01',end_date=end)
 for item in weather['weather_events']['conditions'].values():
  item['count']=1;item['duration_slots']=[2,8]
 weather['earthquake']['count']=1 if stress else 0
 weather['instrument_fault']['count']=1 if stress else 0
 weather['rocket_launch']['count']=1
 weather['terrain_obstruction']['sector_count']=[0,0]
 weather['stress_tests']['enabled']=stress
 catpath=card/'config/catalog-generation.json';catpath.write_text(json.dumps(cat,indent=2)+'\n')
 weatherpath=card/'config/weather-generation.json';weatherpath.write_text(json.dumps(weather,indent=2)+'\n')
 cg=card/'generated-catalog';wg=card/'generated-weather'
 generate_catalog(catpath,cg);generate(weatherpath,wg)
 for f in ('targets.csv','footprint.csv'):shutil.copy2(cg/f,card/'public'/f)
 for f in ('v4_night_calendar.csv','v4_bulletins.jsonl','v4_forecasts.jsonl'):shutil.copy2(wg/f,card/'public'/f)
 for f in ('v4_slots.csv','v4_weather_truth.csv','v4_events.csv','v4_earthquake_effects.csv','v4_stress_events.csv'):
  if (wg/f).exists():shutil.copy2(wg/f,card/'truth'/f)
 fiber=json.loads((BASE/'official-config/v4_fiber_config.json').read_text())
 fiber['field']['n_fibers']=side*side;fiber['field']['fiber_area_deg2']=area
 (card/'config/v4_fiber_config.json').write_text(json.dumps(fiber,indent=2)+'\n')
 score=json.loads((BASE/'official-config/v4_score_config.json').read_text());score['required']['observed_factor_threshold']=threshold;score['observation_requests']['completion_factor_threshold']=threshold
 (card/'config/v4_score_config.json').write_text(json.dumps(score,indent=2)+'\n')
 scenario=json.loads((BASE/'official-config/v4_scenario.json').read_text());scenario['name']='synthetic-'+name
 scenario['task_card']={'card_id':'synthetic-'+name,'scenario_slug':'synthetic-'+name,'phase':'offline-'+split}
 scenario['stress']['enabled']=stress
 if stress:scenario['stress']['stress_events_csv']='../truth/v4_stress_events.csv'
 (card/'config/v4_scenario.json').write_text(json.dumps(scenario,indent=2)+'\n')
 generate_requests(seed=seed+900000,targets_csv=card/'public/targets.csv',night_calendar_csv=card/'public/v4_night_calendar.csv',
   slots_csv=card/'truth/v4_slots.csv',site=scenario['site'],minimum_altitude_deg=scenario['minimum_altitude_deg'],
   output_path=card/'truth/v4_observation_requests.jsonl',settings={'count':2,'window_nights':1,'targets_per_request':8,
    'minimum_completion_fraction':.75,'completion_factor_threshold':threshold,'minimum_feature_flux':.0625},
   flux_zero_point=score['flux_zero_point'],exposure_zero_point_seconds=score['exposure_zero_point_seconds'],
   min_duration_seconds=60,max_duration_seconds=3600)
 validate_bundle(card)
 hashes={str(p.relative_to(card)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ('public','truth','config')
         for p in sorted((card/d).rglob('*')) if p.is_file()}
 manifest.append({'name':name,'split':split,'seed':seed,'targets':count,'days':days,'fibers':side*side,
                  'area':area,'threshold':threshold,'stress':stress,'sha256':hashes})
 print(name,'generated',flush=True)
(ROOT/'long-case-manifest-v2.json').write_text(json.dumps(manifest,indent=2)+'\n')
