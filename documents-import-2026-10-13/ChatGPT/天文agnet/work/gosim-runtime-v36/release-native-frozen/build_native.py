"""Compile on the deployment host; never ship a platform-specific binary."""
import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
compiler = shutil.which(os.environ.get('CXX', 'c++'))
if compiler is None:
    print('C++ compiler unavailable; cached Python search remains usable')
else:
    subprocess.run([compiler, '-std=c++17', '-O3', '-ffp-contract=off', '-shared', '-fPIC',
                    str(root/'joint.cpp'), '-o', str(root/'libjoint.so')], check=True)
