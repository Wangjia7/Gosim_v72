from pathlib import Path
import json,os,subprocess,sys,tempfile,zipfile,hashlib,shutil
r=Path(__file__).resolve().parent;outputs=r.parents[1]/'outputs'
subprocess.run([sys.executable,str(r/'agent/pack_agent.py'),'--out',str(outputs/'gosim-desi-v3.0-final-upload.zip')],check=True)
# Saved platform parser; no cloud submission is performed.
sys.path.insert(0,str(r.parent/'official-read'))
from project_platform.manifest import ProjectManifest
sys.path.insert(0,str(r/'tests'))
from test_observer import init
upload=outputs/'gosim-desi-v3.0-final-upload.zip'
with tempfile.TemporaryDirectory(prefix='gosim-release-check-') as tmp:
 root=Path(tmp)
 with zipfile.ZipFile(upload) as z:
  names=z.namelist()
  assert 'observer.project.json' in names
  assert not any(n.endswith(('.so','.dylib','.pyc','.dll')) or Path(n).name=='.env' or '/truth/' in n for n in names)
  z.extractall(root)
 manifest=ProjectManifest.parse((root/'observer.project.json').read_text())
 env={**os.environ,**dict(manifest.environment),'OBSERVER_MODEL_DISABLED':'1'}
 for command in manifest.build:subprocess.run(command,cwd=root,env=env,check=True,timeout=30)
 messages=[{'protocol_version':'participant-agent-protocol-v4','message_type':'initialize','payload':init()},
  {'protocol_version':'participant-agent-protocol-v4','message_type':'decision_request','decision_sequence':42,
   'payload':{'now_utc':init()['survey']['start_utc'],'new_messages':[],'active_requests':[],
    'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
 p=subprocess.run(manifest.run,cwd=root,env=env,text=True,input=''.join(json.dumps(x)+'\n' for x in messages),capture_output=True,timeout=30)
 assert p.returncode==0,p.stderr
 reply=[json.loads(x) for x in p.stdout.splitlines()];assert len(reply)==1;assert reply[0]['decision_sequence']==42;assert reply[0]['action']=='observe'
 check={'root_manifest':True,'official_saved_parser':True,'host_manifest_build_run':True,'response':reply[0],
  'native_binaries_excluded':True,'truth_excluded':True,'credentials_excluded':True,'linux_container_tested':False,
  'upload_sha256':hashlib.sha256(upload.read_bytes()).hexdigest(),'files':names}
 (r/'release-check.json').write_text(json.dumps(check,indent=2)+'\n')
# Include original failed inputs/results and complete new evidence for local reproduction.
source=outputs/'gosim-desi-v3.0-source-validation.zip'
with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(r.rglob('*')):
  rel=p.relative_to(r)
  if not p.is_file() or any(x in {'__pycache__','scratch','.git','reference'} for x in rel.parts):continue
  if p.suffix in {'.so','.pyc','.dylib','.o','.zip','.dll'} or p.name=='.env' or p.name.startswith('.env.'):continue
  z.write(p,rel.as_posix())
(outputs/'gosim-desi-v3.0-checksums.json').write_text(json.dumps({p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in (upload,source)},indent=2)+'\n')
print('upload',upload.stat().st_size,'source evidence',source.stat().st_size)
