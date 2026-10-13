from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parent;EXP=ROOT/'experiments'
def row(name):
    w=json.loads((EXP/name/'workflow_result.json').read_text())
    return {'out':name,'total':w['score_report']['total'],'components':w['score_report']['components'],
        'counts':w['score_report']['counts'],'termination':w['termination_reason'],'clock':w['fair_clock']}
names=[('L1','cpu-L1-baseline','repaired-L1-minimal'),('L2','cpu-L2-baseline','minimal-L2'),
       ('500目标正常样例','cpu-sparse-baseline','minimal-sparse'),('新正常卡 normal-a','new-normal-a-baseline','minimal-normal-a'),
       ('新正常卡 normal-b','new-normal-b-baseline','minimal-normal-b')]
paired=[]
for card,base,candidate in names:
    b,c=row(base),row(candidate)
    paired.append({'card':card,'baseline':b,'candidate':c,'delta':c['total']-b['total']})
report='''# v3.2 本地验证与交付

默认上传包：gosim-pro-normal-v3.2-upload.zip。阶段包：gosim-pro-normal-v3.2-stage-upload.zip，采用全组合搜索。

默认使用保守组合：JOINT_PROGRAM=1；FULL_FIELD=0、BREAKPOINTS=0、REQUEST_BATCH=0、CONSERVATIVE_REQUIRED=0、WINDOW_URGENCY=0。每轮缓存、C++ 几何预筛、请求各自窗口/门槛、运行时 required 配置、回放账本和 CPU 档位归档修正开启。阶段包及可选开关保留全组合，默认没有启用的功能不能当作本版本已证实提分功能。

## 整季官方评分器对照

API 关闭，相同冻结输入、相同官方评分器，每例 180 标准 CPU 秒和 360 秒实时时限。actual CPU 用离线 time.process_time hook 正确计量，理由见下文。下表每个候选使用默认组合，均走过完整季节，没有 CPU 耗尽。单次自适应计时会改变轨迹，未重复估计主机负载带来的成绩方差。

| 数据 | 官方 pro | 默认组合 | 差值 | required missing | 请求完成 |
|---|---:|---:|---:|---|---|
'''
for p in paired:
    b,c=p['baseline'],p['candidate'];bc,cc=b['counts'],c['counts']
    report+=f"| {p['card']} | {b['total']:.2f} | {c['total']:.2f} | {p['delta']:+.2f} | {bc['required_missing']} → {cc['required_missing']} | {cc['observation_requests_completed']}/{cc['observation_requests_issued']} |\n"
report+='''
结论限定：工程与边界正确性已改善，L2 与 500 目标正常样例提分；L1 和两个新正常随机卡存在回归。不能宣称所有正常卡超过 pro，默认组合也不是未知卡最优解。两个新随机卡是在候选完成后生成，但结果参与了本次开关取舍，因此最终推荐配置没有独立盲测成绩。

## 测试与接口

- 23 项边界/状态/模型测试：共同 program 的真实边际增分、请求截止、尚未升起目标、过期请求、完成度下界、最佳一次曝光、独立 raw 最大值、失效回放、维修阶段隔离、重复结果/sequence、CPU 档位归档、原生/Python 一致性、两个模拟 LLM 流程、严格 JSON。
- 最終 ZIP 解压后使用官方保存的 ProjectManifest parser，执行 build/run，验证正常、非默认 required 和大布局路由；另验证 OBSERVER_NATIVE=0 的 Python 回退。
- 宿主机 Python 3.10 与打包对应的 Python 3.12 环境均运行协议检查。Linux Docker/cgroup、网站评分、真实远程 API 尚未测试。
- 不打包 .env、密钥、任务卡、真值、共享库或 Python bytecode；部署主机重新构建 C++。正常与增强路径只初始化一套 agent，初始信息无法识别未来隐藏故障。

## 计时限制与保留失败

官方 macOS subprocess meter 在本机 Python 3.10/x86_64 环境下低计约 41.7 倍：实际进程 CPU 0.200 秒只记录 0.0048 秒。未修改官方引擎；初步 transport 成绩 retained，不能用来证明相同 CPU 预算下的提升。后续用原官方 workflow/scorer/calibration，加同进程可信 CPU hook，只在 agent 回答窗口按 time.process_time 计费。比赛网站仍采用其 cgroup CPU 计量，本地可信 hook 不代替网站计量验证。

首次全组合 L1 在尚未升起的请求目标上出现 KeyError，已保留失败，补过滤和回归测试。另修复公告污染判断：earthquake 改变仪器效率，不能被当成破坏天空 program 校准的天气消息；之前过度过滤使故障报告延迟，失败修订的负面结果也保留。

纯缓存控制 L1：5954.64，pro 6164.81；CPU 下降但少完成一个请求，所以不采用“缓存就一定提分”的解释。全组合最新 L1：5956.01、请求1/2；L2：6259.87、请求2/2。窗口紧迫度实验没有消除较暗正常卡回归，因此不默认开启。各修订及不利结果在 experiments 中保留。

## 使用

直接上传 upload.zip，根目录含 observer.project.json，不需要把 source-validation.zip 上传网站。主机命令 python3 build_native.py 后 python3 -u agent.py。可由环境或本地 .env 覆盖 PRO_ 实验开关，显式模型禁用或无密钥时继续规则模式。模型与数值规划收益分开：本次对照未证明 LLM 带来分数提升。

源代码、输入身份、动作序列、计时、测试记录和实验配置可用于复核。没有按卡名、C00/C01、scenario_slug、目标 ID 或隐藏真值设置运行时策略。
'''
(ROOT/'VALIDATION.md').write_text(report)
(ROOT/'agent/VALIDATION.md').write_text(report)
snapshot={str(p.relative_to(ROOT/'agent')):hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (ROOT/'agent').rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.json','.md')}
(ROOT/'final-source.json').write_text(json.dumps(snapshot,indent=2)+'\n')
(EXP/'selected-results.json').write_text(json.dumps(paired,indent=2)+'\n')
(ROOT/'CURRENT.md').write_text('''默认保守组合，最终上传 gosim-pro-normal-v3.2-upload.zip；全组合阶段包保留。23 项测试、manifest/build/JSONL/Python fallback。L2 +293.52，L1 -61.38；两个新正常卡仍有回归，非普遍超越。真 API、Linux、网站成绩未测。CPU 计量本机 subprocess reader 异常，使用官方 scorer + 可信同进程 hook。详见 VALIDATION.md。
''')
(ROOT/'dependency-lock.txt').write_text(sys.version+'\n'+platform.platform()+'\nAgent: stdlib, optional C++17; evaluator official copied runner; PyYAML '+yaml.__version__+' only for registry.\n')
metrics={'total_points':{'value':[p['candidate']['total'] for p in paired],'unit':'points','sample_count':len(paired),'denominator':'one final score per frozen task card'},
    'paired_delta':{'value':[p['delta'] for p in paired],'unit':'points','sample_count':len(paired)},
    'required_missing':{'value':[p['candidate']['counts']['required_missing'] for p in paired],'unit':'count','sample_count':len(paired)},
    'cpu_charged':{'value':[p['candidate']['clock']['charged_seconds'] for p in paired],'unit':'standard_cpu_seconds','sample_count':len(paired)}}
(EXP/'final-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
manifests=[json.loads((EXP/p['candidate']['out']/'source-input-manifest.json').read_text()) for p in paired]
config={'schema_version':1,'experiment_id':'gosim-pro-normal-v32-conservative','project_id':'astronomy-observer-v32','parent_run_id':None,
 'hypothesis':'Cached common-program search and deadline protection can improve some normal cases within CPU budget; universal nonregression is tested, not assumed.',
 'baseline':'paired official python-pro runs in selected-results.json','command':'python3 cpu_matrix.py; python3 cpu_followup.py; python3 cpu_minimal.py; python3 cpu_repaired.py; python3 cpu_windows.py',
 'output_dir':'experiments','data_contract_revision':'DATA_CONTRACT.md v32',
 'datasets':[{'name':'L1 L2 sparse and two new normal seeds','version':'v32 frozen products','uri':'per-run source-input-manifest.json',
              'identity':hashlib.sha256((ROOT/'case-manifest-v2.json').read_bytes()).hexdigest()}],
 'random':{'stochastic':True,'seed':2026100617,'rng':'official generator random.Random; per-case seeds/product hashes preserved',
           'stream_policy':'identical frozen target/weather/request products in each pair; no runtime RNG; adaptive timing nondeterministic'},
 'parallel':{'backend':'serial charged runs; passive supervisors and occasional unit tests on host','workers':1,'threads_per_worker':1,'reduction':'serial per fibre'},
 'environment':{'dependency_lock':'dependency-lock.txt','hardware':platform.machine(),'software':platform.python_version()+' stdlib; C++17; official scorer; local process CPU hook'},
 'parameters':{'normal_preset':{'JOINT_PROGRAM':1,'FULL_FIELD':0,'BREAKPOINTS':0,'REQUEST_BATCH':0,'CONSERVATIVE_REQUIRED':0,'WINDOW_URGENCY':0},'api':False,'standard_cpu_budget':180},
 'controls':{'sample_ids':'fixed public target IDs per pair','skeleton':'not-applicable; telescope schedule',
             'selection':'all named pairs with gains/regressions retained; selection after development results, no blind final holdout',
             'units_and_coordinates':'UTC/degrees, public alt-az gnomonic mapping','bin_edges_and_denominator':'one official total per complete task card'},
 'metrics':{k:{'definition':k+' from official final score/fair clock','unit':v['unit'],'uncertainty':'one run per card; OS pacing variance not estimated'} for k,v in metrics.items()},
 'reproducibility':{'level':'numerical','tolerance':'saved action traces exactly scoreable; adaptive reruns need not produce identical actions'},
 'success_criterion':'legal complete episodes, interface checks, retain regressions; no universal score threshold claimed',
 'budget':{'max_runs':32,'max_walltime_hours':1,'stop_condition':'planned source/switch comparisons and ZIP verification complete; stop further tuning'}}
(EXP/'final-config.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
(EXP/'registry-times.json').write_text(json.dumps({'started_at':min(x['start'] for x in manifests),'ended_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
print(json.dumps([{'card':p['card'],'delta':p['delta']} for p in paired],ensure_ascii=False))
