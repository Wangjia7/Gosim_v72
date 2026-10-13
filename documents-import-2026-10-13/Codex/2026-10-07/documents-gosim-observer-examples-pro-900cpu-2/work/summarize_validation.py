import csv,json,hashlib,shutil
from pathlib import Path
root=Path('outputs/python-pro-v2'); dest=root/'validation'
rows=[]
for card in ('L1','L3'):
    for version,folder in [('baseline',f'baseline-{card}-native'),('v2.0.0',f'final-{card}')]:
        source=Path('work')/folder
        result=json.loads((source/'workflow_result.json').read_text())
        report=result['score_report']; clock=result['fair_clock']
        decisions=list(csv.DictReader((source/'decisions.csv').open()))
        log=(source/'agent.log').read_text()
        item={'card':card,'version':version,'total':report['total'],'required_missing':report['counts']['required_missing'],
              'requests_completed':report['counts']['observation_requests_completed'],
              'observe_actions':report['counts']['observe_actions'],'normalized_cpu_seconds':clock['charged_seconds'],
              'real_cpu_seconds':clock['cpu_seconds'],'wall_seconds':clock['run_wall_seconds'],
              'speed_factor':clock['speed_factor'],'termination':result['termination_reason'],
              'assigned_count':sum(int(r['assigned_count'] or 0) for r in decisions),
              'hit_count':sum(int(r['hit_count'] or 0) for r in decisions),
              'state_resync_count':log.count('state_resync:'),'internal_error_count':log.count('pro: error ')}
        assert result['termination_reason']=='survey_complete', item
        assert clock['charged_seconds']<900 and not clock['hard_cap_reached'],item
        assert not item['internal_error_count'],item
        rows.append(item)
        # Retain compact originals and logs, not entire observation tables.
        prefix=f'{version}-{card}'
        for name in ('score_report.json','agent.log'):
            shutil.copy2(source/name,dest/f'{prefix}-{name}')
metadata={'agent_code_commit':'1892ddd','model':'disabled (OBSERVER_MODEL_DISABLED=1)',
          'python':'/usr/bin/python3 3.9.6 arm64','budget_normalized_cpu_seconds':900,
          'search':'adaptive defaults','runner_modified':False,'seed':'unchanged supplied card data',
          'note':'Single local runs; machine-dependent adaptive search is not bitwise reproducible. No live LLM calls.',
          'runs':rows}
(dest/'benchmark-summary.json').write_text(json.dumps(metadata,indent=2)+'\n')
with (dest/'benchmark-summary.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for card in ('L1','L3'):
    base,new=[r for r in rows if r['card']==card]
    print(card,base['total'],new['total'],(new['total']/base['total']-1)*100,new['normalized_cpu_seconds'])
