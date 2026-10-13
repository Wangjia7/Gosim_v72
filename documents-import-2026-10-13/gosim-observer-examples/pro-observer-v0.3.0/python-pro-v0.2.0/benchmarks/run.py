#!/usr/bin/env python3
"""Run the unmodified local judge with an isolated no-model observer environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

NATIVE=Path('/Library/Developer/CommandLineTools/usr/bin/python3')
BASE=Path('/Users/jqwang/Documents/gosim-observer-examples')
OUTPUTS=Path(__file__).resolve().parents[2]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-dir',type=Path,required=True)
    parser.add_argument('--card',choices=['L1','L2','L3','L4'],required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--set',action='append',default=[],metavar='POLICY_NAME=value')
    parser.add_argument('--adaptive',action='store_true')
    parser.add_argument('--fixed-level-env',choices=['PRO_FIXED_LEVEL','V5_FIXED_LEVEL'],default='PRO_FIXED_LEVEL')
    parser.add_argument('--manifest-settings',action='store_true',help='load only nonsecret policy flags from the observer manifest; never execute build/image directives')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--project-root',type=Path,default=BASE,help='supplied examples root containing runner and local-cards')
    parser.add_argument('--python',type=Path,default=NATIVE if NATIVE.exists() else Path(sys.executable),help='native interpreter for judge, calibration and observer')
    args=parser.parse_args()
    interpreter=args.python.resolve()
    project=args.project_root.resolve()
    if not interpreter.is_file(): parser.error('Python interpreter does not exist')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.label): parser.error('label must use letters, numbers, underscore or hyphen')
    agent_dir=args.agent_dir.resolve()
    if not (agent_dir/'agent.py').is_file(): parser.error('agent-dir must contain agent.py')
    settings={}
    manifest_evidence=None
    if args.manifest_settings:
        manifest_path=agent_dir/'observer.project.json'
        public_manifest=json.loads(manifest_path.read_text())
        supplied=public_manifest.get('environment',{})
        allowed=lambda key: re.fullmatch(r'(?:PRO_|V[0-9]+_)[A-Z0-9_]+|PYTHONDONTWRITEBYTECODE',key) and not any(token in key for token in ('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL','AUTH'))
        settings.update({key:str(value) for key,value in supplied.items() if allowed(key)})
        manifest_evidence={'sha256':digest(manifest_path),'policy_settings':dict(settings),'ignored_variable_names':[key for key in supplied if not allowed(key)],'protocol_declaration':public_manifest.get('protocol'),'note':'Native source execution only; manifest image/build directives not executed.'}
    settings.update({'OBSERVER_MODEL_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1',args.fixed_level_env:'-1' if args.adaptive else '0'})
    for assignment in args.set:
        key,sep,value=assignment.partition('=')
        if not sep or not re.fullmatch(r'(?:PRO_|V[0-9]+_)[A-Z0-9_]+',key): parser.error('--set permits only PRO_ or versioned Vn_ policy settings')
        if any(token in key for token in ('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL','AUTH')): parser.error('credential settings are prohibited')
        settings[key]=value
    out=(args.out or OUTPUTS/'pro-evaluation-v0.2.0'/args.label/args.card).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/'benchmark.json').exists(): parser.error('output already contains a benchmark; choose a fresh label/out')
    cwd=out/'agent-cwd'; cwd.mkdir(exist_ok=True)
    if (cwd/'.env').exists(): parser.error('isolated agent cwd must not contain .env')
    # Copy only Python source: agent.main also loads .env beside __file__, so cwd isolation alone is insufficient.
    execution_dir=out/'agent-source'; execution_dir.mkdir(exist_ok=True)
    if (execution_dir/'.env').exists(): parser.error('isolated source must not contain .env')
    for source in agent_dir.glob('*.py'): shutil.copyfile(source,execution_dir/source.name)
    settings.setdefault('PRO_LOG_PATH',str(out/'decision-log.jsonl'))
    agent_command=['/usr/bin/env']+[f'{key}={value}' for key,value in sorted(settings.items())]+[str(interpreter),'-B',str(execution_dir/'agent.py')]
    runner=project/'runner'/'run_local.py'
    card=project/'local-cards'/args.card
    command=[str(interpreter),'-B',str(runner),'--card',str(card),'--agent',shlex.join(agent_command),'--agent-cwd',str(cwd),'--wallclock','900','--out',str(out),'--quiet']
    # No inherited credentials or .env; native executable and PATH apply to runner/calibration/observer.
    environment={'PATH':str(interpreter.parent)+':/usr/bin:/bin:/usr/sbin:/sbin','PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
    metadata={'schema_version':'pro-benchmark-v1','label':args.label,'card':args.card,'agent_dir':str(agent_dir),'command':command,'command_shell':shlex.join(command),'settings':settings,'runner_environment':environment,'agent_cwd':str(cwd),'execution_source':str(execution_dir),'budget_seconds':900,'adaptive':args.adaptive,'source_hashes':{str(p.relative_to(agent_dir)):digest(p) for p in sorted(agent_dir.glob('*.py'))},'execution_source_hashes':{str(p.relative_to(execution_dir)):digest(p) for p in sorted(execution_dir.glob('*.py'))},'engine_hashes':{str(p.relative_to(project)):digest(p) for p in sorted((project/'runner').rglob('*.py'))},'card_config_hashes':{str(p.relative_to(card)):digest(p) for p in sorted((card/'config').glob('*.json'))},'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'running','note':'Observer reads protocol stdin only; card files are read by unmodified judge. Python source-only snapshot is executed by absolute path from isolated output cwd; neither source nor cwd .env is available.'}
    metadata['card_file_hashes']={str(p.relative_to(card)):digest(p) for p in sorted(card.rglob('*')) if p.is_file()}
    metadata['manifest_settings']=manifest_evidence
    metadata['fixed_level_env']=args.fixed_level_env
    (out/'benchmark.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    print(f'Running {args.label}/{args.card}; outputs {out}',flush=True)
    start=time.monotonic()
    with (out/'runner.stdout').open('w') as stdout,(out/'runner.stderr').open('w') as stderr:
        result=subprocess.run(command,cwd=out,env=environment,stdout=stdout,stderr=stderr)
    metadata.update(returncode=result.returncode,harness_wall_seconds=round(time.monotonic()-start,3),finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    try: summary=json.loads((out/'runner.stdout').read_text())
    except (ValueError,OSError): summary={}
    metadata['summary']=summary
    report_path=out/'score_report.json'
    if report_path.exists(): metadata['official_score_report']=json.loads(report_path.read_text())
    metadata['source_unchanged']=all(digest(agent_dir/name)==value for name,value in metadata['source_hashes'].items())
    metadata['execution_source_unchanged']=all(digest(execution_dir/name)==value for name,value in metadata['execution_source_hashes'].items())
    metadata['card_files_unchanged']=all(digest(card/name)==value for name,value in metadata['card_file_hashes'].items())
    metadata['status']='success' if result.returncode==0 and summary.get('termination_reason')=='survey_complete' and metadata['execution_source_unchanged'] and metadata['card_files_unchanged'] else 'incomplete_or_failed'
    (out/'benchmark.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    (out/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':metadata['status'],'summary':summary},indent=2),flush=True)
    return result.returncode
if __name__=='__main__': raise SystemExit(main())
