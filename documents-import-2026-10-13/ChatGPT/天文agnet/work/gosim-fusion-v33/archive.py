from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parent;O=R.parents[1]/'outputs'
output=O/'gosim-fusion-v3.3-source-validation.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('README.md','代码与本地验证证据归档，不能直接上传比赛网站。上传使用旁边的 gosim-fusion-v3.3-upload.zip。agent/ 是最终源码；snapshots/ 保留对照及失败原型；experiments/ 有全部 32 次动作、评分、CPU 和哈希；不包含原始卡片真值，重跑评分需要原始数据目录。\n')
    for folder in ['final-steady','incoming','local-baseline','agent','fused','joint-final','release','final','experiments','evidence','tests']:
        prefix='agent' if folder=='final-steady' else 'snapshots/'+folder if folder in ['incoming','local-baseline','agent','fused','joint-final','release','final'] else folder
        for p in sorted((R/folder).rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.so','.dll','.dylib','.zip','.lock') or p.name=='.env':continue
            z.write(p,prefix+'/'+str(p.relative_to(R/folder)))
    for p in sorted(R.iterdir()):
        if p.is_file() and p.suffix in ('.py','.log','.json','.md','.txt'):
            z.write(p,'harness/'+p.name)
    z.write(O/'gosim-fusion-v3.3-comparison.md','comparison.md')
with zipfile.ZipFile(output) as z:assert z.testzip() is None
metadata={'upload':str(O/'gosim-fusion-v3.3-upload.zip'),'validation':str(output),
 'validation_bytes':output.stat().st_size,'validation_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
(O/'gosim-fusion-v3.3-artifacts.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata,indent=2))
