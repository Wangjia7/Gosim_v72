from pathlib import Path
import hashlib,json,shutil,zipfile
R=Path(__file__).resolve().parent;O=R.parents[1]/'outputs'
# Preserve rejected prototypes away from the deliverable folder.
P=R/'experiments/prototype-artifacts';P.mkdir(exist_ok=True)
for name in ('gosim-logcpu-v3.4-upload.zip','gosim-logcpu-v3.4-release.zip'):
 p=O/name
 if p.exists():shutil.move(str(p),str(P/name))
(P/'failure.txt').write_text('First package validation failed: project_platform.manifest.ProjectError: Credentials and platform settings must not be placed in the project manifest. Cause: reserved OBSERVER_LOG_REVIEW and OBSERVER_MAX_BREADTH keys. Final changes use private FUSION_LOG_REVIEW and FUSION_MAX_BREADTH. No credentials were stored. Rejected archives retained here as evidence.\n')
output=O/'gosim-logcpu-v3.4-source-validation.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('README.md','源码与本地验证证据，不能直接上传网站。上传使用 gosim-logcpu-v3.4-final-upload.zip。agent/ 为最终源码；snapshots/ 保存原型；9 个完整对局、日志、哈希、分数和失败测试保留。重跑仍需原始卡片。模型只做本地模拟验证。\n')
 for folder in ('agent','baseline','expanded-smoke','pre-resync-frozen','numeric-final-frozen','experiments','evidence','tests'):
  prefix=folder if folder in ('agent','experiments','evidence','tests') else 'snapshots/'+folder
  for p in sorted((R/folder).rglob('*')):
   if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.so','.pyc','.dll','.dylib','.zip','.lock') or p.name=='.env':continue
   z.write(p,prefix+'/'+str(p.relative_to(R/folder)))
 for p in sorted(R.iterdir()):
  if p.is_file() and p.suffix in ('.py','.md','.log','.txt'):z.write(p,'harness/'+p.name)
 z.write(O/'gosim-logcpu-v3.4-validation.md','validation.md')
with zipfile.ZipFile(output) as z:assert z.testzip() is None
check=json.loads((R/'experiments/gosim-logcpu-v3.4-final-upload-release-check.json').read_text())
p=O/'gosim-logcpu-v3.4-final-upload.zip'
assert hashlib.sha256(p.read_bytes()).hexdigest()==check['sha256']
with zipfile.ZipFile(p) as z:
 for n in z.namelist():assert z.read(n)==(R/'agent'/n).read_bytes(),n
 assert not any(Path(n).name=='.env' or n.endswith(('.so','.pyc')) or '/truth/' in n for n in z.namelist())
 metadata={'upload':str(p),'upload_sha256':check['sha256'],'files':len(z.namelist()),
  'validation':str(output),'validation_bytes':output.stat().st_size,'validation_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
(O/'gosim-logcpu-v3.4-artifacts.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata,indent=2))
