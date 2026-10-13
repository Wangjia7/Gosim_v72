import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
R=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='observer-fusion-python312-') as temp:
    target=Path(temp)/'agent'
    shutil.copytree(R/'final-steady',target,ignore=shutil.ignore_patterns('__pycache__','*.so','*.pyc'))
    env={**os.environ,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],
        'PRO_TEST_AGENT':str(target),'PYTHONDONTWRITEBYTECODE':'1'}
    subprocess.run([sys.executable,str(target/'build_native.py')],env=env,check=True,timeout=60)
    log=R/'tests-python312-final.log'
    with log.open('w') as stream:
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(R/'tests'),'-v'],
            env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
    print(log.read_text()[-350:]);result.check_returncode()
