import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
args=argparse.ArgumentParser();args.add_argument('--folder',default='agent');args.add_argument('--name',default='gosim-pro-normal-v3.2-upload.zip')
args=args.parse_args();source=ROOT/args.folder
sys.path.insert(0,str(ROOT.parent/'official-read'))
from project_platform.manifest import ProjectManifest
sys.path.insert(0,str(ROOT/'tests'))
from test_normal import fixture
output=ROOT.parents[1]/'outputs'/args.name
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(source.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.so','.dll','.dylib','.zip') or p.name=='.env':continue
        z.write(p,str(p.relative_to(source)))
with tempfile.TemporaryDirectory(prefix='observer-v32-release-') as tmp:
    target=Path(tmp)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert not any('truth/' in n or n.endswith(('.so','.pyc','.dylib','.dll')) or Path(n).name=='.env' for n in z.namelist())
        z.extractall(target)
    manifest=ProjectManifest.parse((target/'observer.project.json').read_text())
    env={**os.environ,**dict(manifest.environment),'OBSERVER_MODEL_DISABLED':'1'}
    for command in manifest.build:subprocess.run(command,cwd=target,env=env,check=True,timeout=60)
    replies=[]
    for side,threshold in ((4,.5),(4,.7),(10,.5)):
        data=fixture(side);data['scoring']['required']['observed_factor_threshold']=threshold
        messages=[{'message_type':'initialize','payload':data},
          {'message_type':'decision_request','decision_sequence':7,'payload':{'now_utc':data['survey']['start_utc'],
            'new_messages':[],'active_requests':[],'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
        r=subprocess.run(manifest.run,cwd=target,env=env,input=''.join(json.dumps(m)+'\n' for m in messages),
            text=True,capture_output=True,timeout=30)
        assert r.returncode==0,r.stderr
        reply=json.loads(r.stdout);assert reply['action']=='observe';assert 'error ' not in r.stderr
        replies.append(reply)
    # Exercise the cached Python fallback from exactly the extracted ZIP.
    r=subprocess.run(manifest.run,cwd=target,env={**env,'OBSERVER_NATIVE':'0'},
        input=''.join(json.dumps(m)+'\n' for m in messages),text=True,capture_output=True,timeout=30)
    assert r.returncode==0,r.stderr;assert json.loads(r.stdout)['action']=='observe'
check={'zip':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
       'manifest_host_build_jsonl':True,'normal_and_enhanced_routes':True,'python_fallback':True,
       'linux_container':False,'remote_api':False,'replies':replies}
(ROOT/'experiments'/f'{output.stem}-release-check.json').write_text(json.dumps(check,indent=2)+'\n')
print(json.dumps({k:v for k,v in check.items() if k!='replies'},ensure_ascii=False,indent=2))
