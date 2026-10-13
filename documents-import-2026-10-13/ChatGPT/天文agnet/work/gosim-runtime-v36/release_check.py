"""Fresh upload archive host build/JSONL smoke. No live network or secret output."""
import copy,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'))
from test_normal import fixture
P=R.parent/'official-read/project_platform/manifest.py'
spec=importlib.util.spec_from_file_location('manifest_check',P);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
archive=R.parents[1]/'outputs/gosim-runtime-v3.6-upload.zip'
checks=[]
with tempfile.TemporaryDirectory(prefix='observer-v36-release-') as td:
    dst=Path(td)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();assert 'observer.project.json' in names
        assert not any(Path(n).name=='.env' or n.endswith(('.so','.pyc')) for n in names)
        z.extractall(dst)
    m=mod.ProjectManifest.parse((dst/'observer.project.json').read_text())
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY','TOKEN','SECRET','PASSWORD'))}
    env.update(dict(m.environment));env['PYTHONDONTWRITEBYTECODE']='1'
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env['PATH']
    for command in m.build:subprocess.run([sys.executable,*command[1:]],cwd=dst,env=env,check=True,timeout=60)
    for name,side,threshold,native,disabled in [('standard',4,None,1,1),('threshold',4,.7,1,1),('large',10,None,1,1),('python-fallback',4,None,0,1),('missing-key',4,None,1,0)]:
        d=fixture(side)
        if threshold:d['scoring']['required']['observed_factor_threshold']=threshold
        payload={'now_utc':d['survey']['start_utc'],'active_requests':[],'last_result':None,'new_messages':[],
                 'latest_bulletin':{'notices':[]},'wallclock':{'remaining_real_cpu_seconds':900,'wall_remaining_seconds':7200}}
        decision={'protocol_version':'participant-agent-protocol-v4','message_type':'decision_request','decision_sequence':7,'payload':payload}
        messages=[{'message_type':'initialize','payload':d},decision,decision,{'message_type':'finish','payload':{'termination_reason':'smoke'}}]
        e={**env,'OBSERVER_NATIVE':str(native),'OBSERVER_MODEL_DISABLED':str(disabled)}
        q=subprocess.run([sys.executable,'-u','agent.py'],cwd=dst,env=e,input=''.join(json.dumps(x)+'\n' for x in messages),text=True,capture_output=True,timeout=60)
        assert q.returncode==0,q.stderr[-300:]
        lines=q.stdout.splitlines();assert len(lines)==2 and lines[0]==lines[1],lines
        a=json.loads(lines[0]);assert a['message_type']=='decision_response' and a['decision_sequence']==7
        assert a['action']=='observe',a
        assert d['instrument']['exposure']['min_duration_seconds']<=a['duration_seconds']<=d['instrument']['exposure']['max_duration_seconds']
        assert 0<=a['pointing']['alt_deg']<=90 and 0<=a['pointing']['az_deg']<360
        assignments=a['assignments'];assert all(0<=int(f)<side*side for f in assignments)
        assert len(set(assignments.values()))==len(assignments)
        assert set(assignments.values())<={r[0] for r in d['targets']['rows']}
        assert 'final runtime audit:' in q.stderr and 'error ' not in q.stderr,q.stderr[-400:]
        if not disabled:assert 'missing API key' in q.stderr
        checks.append({'name':name,'duplicate_exact':True,'reply':a,'runtime_summary':next(x.split('final runtime audit: ',1)[1] for x in q.stderr.splitlines() if x.startswith('final runtime audit: '))})
result={'zip':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'official_manifest':True,'host_build':True,'jsonl_routes':True,'python_fallback':True,'missing_key_fallback':True,'remote_api':False,'linux_container':False,'checks':checks}
(R/'experiments/release-check.json').write_text(json.dumps(result,indent=2)+'\n');print('fresh ZIP: official manifest, host build, 5 JSONL cases and duplicate replay passed')
