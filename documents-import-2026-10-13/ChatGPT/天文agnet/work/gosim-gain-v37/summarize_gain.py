"""Equal card weight, averaged predeclared repeats; never omit failures."""
from pathlib import Path
from statistics import mean,median
import csv,json
R=Path(__file__).resolve().parent
rows=[]
for file in ['holdout-progress.json','holdout-repeat-progress.json']:
 p=R/'experiments'/file
 if p.exists():rows+=json.loads(p.read_text())
names=['L2','L3','L4','dense-held','stress-held','fresh-sparse','fresh-dense','fresh-mixed','fresh-long']
expected={n:(2 if n in {'L2','fresh-long'} else 1) for n in names}
pairs=[];complete=len(rows)==22
for name in names:
 groups={f:[x for x in rows if x['card']==name and x['family']==f] for f in ['baseline','final-frozen']}
 complete &= all(len(v)==expected[name] for v in groups.values())
 if not all(groups.values()):continue
 summaries={}
 for family,group in groups.items():
  if any('score' not in x for x in group):complete=False;continue
  for x in group:
   m=json.loads((R/'experiments'/x['label']/'source-input-manifest.json').read_text())
   x['inputs']=m['inputs'];x['native']=m.get('native_loaded') and m.get('native_cells')
  summaries[family]={
    'total':mean(x['score']['total'] for x in group),
    'components':{k:mean(x['score']['components'][k] for x in group) for k in group[0]['score']['components']},
    'required_missing':mean(x['score']['counts']['required_missing'] for x in group),
    'paid_failed':mean(sum(r['completion_reward']>0 and not r['completed'] for r in x['score']['observation_requests']) for x in group),
    'paid_issued':mean(sum(r['completion_reward']>0 for r in x['score']['observation_requests']) for x in group),
    'cpu':mean(x['clock']['charged_seconds'] for x in group),
    'run_wall':mean(x['clock']['run_wall_seconds'] for x in group),
    'episodes':[x['label'] for x in group],
    'score_range':[min(x['score']['total'] for x in group),max(x['score']['total'] for x in group)]}
 if len(summaries)!=2:continue
 b,c=(summaries[f] for f in ['baseline','final-frozen'])
 hashes=[x['inputs'] for g in groups.values() for x in g]
 same=all(h==hashes[0] for h in hashes)
 valid=all(x.get('returncode')==0 and x.get('termination')=='survey_complete' and x['native'] and not x['clock']['hard_cap_reached'] for g in groups.values() for x in g)
 complete &= same and valid
 pairs.append({'card':name,'repeats':expected[name],'baseline':b,'candidate':c,'delta':c['total']-b['total'],'relative':(c['total']-b['total'])/max(abs(b['total']),1.),'inputs_same':same,'valid_complete_native':valid})
summary={'schema':'v37-local-fixed-matrix','expected_cards':9,'expected_episodes':22,'complete':complete and len(pairs)==9,'cards':pairs,'aggregate':None,'verdict':'incomplete'}
if summary['complete']:
 a={'baseline_total':sum(x['baseline']['total'] for x in pairs),'candidate_total':sum(x['candidate']['total'] for x in pairs),'total_delta':sum(x['delta'] for x in pairs),'mean_relative':mean(x['relative'] for x in pairs),'median_relative':median(x['relative'] for x in pairs),'improved_cards':sum(x['delta']>0 for x in pairs),'regressions_over_half_percent':[x['card'] for x in pairs if x['relative']<-.005],
    'baseline_required_missing':sum(x['baseline']['required_missing'] for x in pairs),'candidate_required_missing':sum(x['candidate']['required_missing'] for x in pairs),'baseline_paid_failed':sum(x['baseline']['paid_failed'] for x in pairs),'candidate_paid_failed':sum(x['candidate']['paid_failed'] for x in pairs)}
 passed=a['total_delta']>0 and a['mean_relative']>0 and a['candidate_required_missing']<=a['baseline_required_missing'] and a['candidate_paid_failed']<=a['baseline_paid_failed']
 summary.update(aggregate=a,verdict='pass' if passed else 'fail')
(R/'evidence/comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
with (R/'evidence/comparison.csv').open('w') as f:
 writer=csv.writer(f);writer.writerow(['card','baseline','candidate','delta','relative_percent','required_old','required_new','paid_failed_old','paid_failed_new','cpu_new','repeats'])
 for x in pairs:writer.writerow([x['card'],x['baseline']['total'],x['candidate']['total'],x['delta'],100*x['relative'],x['baseline']['required_missing'],x['candidate']['required_missing'],x['baseline']['paid_failed'],x['candidate']['paid_failed'],x['candidate']['cpu'],x['repeats']])
print(json.dumps({k:v for k,v in summary.items() if k!='cards'},indent=2))
