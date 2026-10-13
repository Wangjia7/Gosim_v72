from pathlib import Path
import json,os,sys,subprocess,tempfile,zipfile,hashlib
r=Path(__file__).resolve().parent;sys.path.insert(0,str(r.parent/'official-read'))
from project_platform.manifest import ProjectManifest
sys.path.insert(0,str(r.parent/'gosim-desi-v300/tests'))
from test_observer import init
pzip=r.parents[1]/'outputs/gosim-pro-first-v3.1-upload.zip'
with tempfile.TemporaryDirectory(prefix='pro-first-zip-') as tmp:
 p=Path(tmp)
 with zipfile.ZipFile(pzip) as z:
  assert z.testzip() is None
  assert not any(n.endswith(('.so','.dll','.dylib')) or Path(n).name=='.env' for n in z.namelist())
  z.extractall(p)
 m=ProjectManifest.parse((p/'observer.project.json').read_text());env={**os.environ,**dict(m.environment),'OBSERVER_MODEL_DISABLED':'1'}
 for c in m.build:subprocess.run(c,cwd=p,env=env,check=True,timeout=30)
 replies=[]
 for side,threshold in ((4,.5),(4,.7),(10,.5)):
  data=init(side,threshold)
  msgs=[{'message_type':'initialize','payload':data},{'message_type':'decision_request','decision_sequence':1,
    'payload':{'now_utc':data['survey']['start_utc'],'new_messages':[],'active_requests':[],
    'wallclock':{'remaining_real_cpu_seconds':100,'wall_remaining_seconds':300}}}]
  result=subprocess.run(m.run,cwd=p,env=env,text=True,input=''.join(json.dumps(x)+'\n' for x in msgs),capture_output=True,timeout=30)
  assert result.returncode==0,result.stderr
  reply=json.loads(result.stdout);assert reply['action']=='observe';replies.append(reply)
 (r/'release-check.json').write_text(json.dumps({'manifest_parse_build_run':True,'both_routes':True,'native_binaries_excluded':True,
    'linux_container_tested':False,'sha256':hashlib.sha256(pzip.read_bytes()).hexdigest(),'replies':replies},indent=2)+'\n')
print('ZIP manifest/build/run and both routes verified')
