from pathlib import Path
import hashlib,json,platform,subprocess,sys,os
r=Path(__file__).resolve().parent
sys.path.insert(0,'/private/tmp/thoughtgraph-validation-deps')
import yaml
rows=json.loads((r/'experiments/request-guard-results.json').read_text());summary=json.loads((r/'summary.json').read_text())
(r/'dependency-lock.txt').write_text('Agent dependencies: Python standard library and compiled C++17 kernel\n'+sys.version+'\n'+platform.platform()+'\n'+subprocess.run(['c++','--version'],capture_output=True,text=True).stdout)
metrics={'totals':{'value':[x['total'] for x in rows],'unit':'points','sample_count':len(rows),'denominator':'one final scorer total per corrected card','artifact':'experiments/request-guard-results.json'},
 'required_missing':{'value':[x['counts']['required_missing'] for x in rows],'unit':'count','sample_count':len(rows)},
 'requests_completed':{'value':[x['counts']['observation_requests_completed'] for x in rows],'unit':'count','sample_count':len(rows)},
 'cpu_charged':{'value':[x['fair_clock']['charged_seconds'] for x in rows],'unit':'standard_cpu_seconds','sample_count':len(rows)}}
(r/'experiments/final-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
config={'schema_version':1,'experiment_id':'gosim-desi-final-layout-regression','project_id':'astronomy-observer-v300','parent_run_id':None,
 'hypothesis':'Window, raw-bound and geometry safeguards execute under official interface/CPU budget; unknown-layout nonregression is evaluated, not assumed.',
 'baseline':'official python-pro in experiments/matrix-results-v2.json','command':sys.executable+' run_request_guard.py','output_dir':'evidence/final-series',
 'data_contract_revision':'DATA_CONTRACT.md v300','datasets':[{'name':'corrected synthetic layouts','version':'v2','uri':'cases-v2',
 'identity':hashlib.sha256((r/'case-manifest-v2.json').read_bytes()).hexdigest()}],
 'random':{'stochastic':True,'seed':202610061,'rng':'official Python random.Random MT19937; individual seeds in case manifest',
 'stream_policy':'same frozen generated catalogue/weather/request products per baseline/candidate pair'},
 'parallel':{'backend':'serial inside each matrix; independent L1/long processes on host','workers':1,'threads_per_worker':1,'reduction':'no threaded numeric reduction'},
 'environment':{'dependency_lock':'dependency-lock.txt','hardware':platform.machine(),'software':platform.python_version()+' stdlib; C++17; PyYAML used only for registry'},
 'parameters':{'api':False,'standard_cpu_budget':120,'final_source_manifest':'request-guard-source-frozen.json'},
 'controls':{'sample_ids':'identical target IDs within each paired card','skeleton':'not-applicable; telescope scheduler',
 'selection':'all corrected cases; preserve both gains and regressions','units_and_coordinates':'UTC and degrees; gnomonic Alt-Az as public engine',
 'bin_edges_and_denominator':'one total per task card; no selected-target renormalization'},
 'metrics':{key:{'definition':key+' from full official score_report/fair_clock','unit':value['unit'],'uncertainty':'single per-case measurement; OS pacing variation not estimated'} for key,value in metrics.items()},
 'reproducibility':{'level':'numerical','tolerance':'exact scorer for saved action trace; fresh adaptive run action identity not guaranteed'},
 'success_criterion':'Interface/legal actions/no CPU expiry; no universal score nonregression assumed',
 'budget':{'max_runs':8,'max_walltime_hours':1,'stop_condition':'six corrected paired-input candidate runs plus long and L1 regression; retain failures'}}
(r/'experiments/final-config.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
cmd=[sys.executable,'/Users/jqwang/.codex/skills/research-experiment/scripts/register_experiment.py','--project-root',str(r),'--config','experiments/final-config.yaml',
 '--status','completed','--run-id','gosim-v300-final-20261006','--metrics','experiments/final-metrics.json',
 '--started-at',min(x['started_at'] for x in rows),'--ended-at',max(x['ended_at'] for x in rows),'--allow-no-git','--allow-dirty','--hash-outputs']
p=subprocess.run(cmd,env={**os.environ,'PYTHONPATH':'/private/tmp/thoughtgraph-validation-deps'},text=True,capture_output=True)
print(p.stdout,p.stderr);raise SystemExit(p.returncode)
