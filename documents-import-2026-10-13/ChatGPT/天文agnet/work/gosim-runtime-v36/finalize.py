"""Register every attempted matrix and deliver source/evidence with actual scores."""
from pathlib import Path
import csv,hashlib,json,subprocess,zipfile
R=Path(__file__).resolve().parent;OUT=R.parents[1]/'outputs'
matrices=[('initial','initial','matrix-progress.json'),('corrected','final','final-progress.json'),('accepted','accepted','accepted-progress.json'),('release-fallback','release','release-progress.json'),('release-native','release-native','release-native-progress.json')]
allrows=[]
for stage,config,file in matrices:
    rows=json.loads((R/'experiments'/file).read_text());assert len(rows)==json.loads((R/'experiments/configs'/f'{config}.yaml').read_text())['budget']['max_runs']
    d=R/'evidence'/stage;d.mkdir(exist_ok=True,parents=True)
    value=[]
    for x in rows:
        s=x['score'];manifest=json.loads((R/'experiments'/x['label']/'source-input-manifest.json').read_text())
        row={'label':x['label'],'total':s['total'],'components':s['components'],'counts':s['counts'],'clock':x['clock'],'termination':x['termination'],'start':x['start'],'end':x['end'],'native_loaded':manifest.get('native_loaded'),'native_cells':manifest.get('native_cells'),'input_hashes':manifest['inputs']}
        value.append(row);allrows.append(row)
    (d/'metrics.json').write_text(json.dumps({'paired_results':{'value':value,'unit':'score/count/seconds'}},indent=2)+'\n')
    if stage in ('release-fallback','release-native'):
        command=['/Users/jqwang/anaconda3/bin/python3','/Users/jqwang/.codex/skills/research-experiment/scripts/register_experiment.py','--project-root',str(R),'--config',f'experiments/configs/{config}.yaml','--status','completed','--run-id',f'gosim-runtime-v36-{stage}-20261007','--metrics',f'evidence/{stage}/metrics.json','--started-at',min(x['start'] for x in rows),'--ended-at',max(x['end'] for x in rows),'--allow-dirty','--allow-no-git','--hash-outputs']
        q=subprocess.run(command,capture_output=True,text=True);(d/'registration.log').write_text(q.stdout+q.stderr);q.check_returncode()
(R/'evidence/all-results.json').write_text(json.dumps(allrows,indent=2)+'\n')
base={x['label'].split('-')[0]:x for x in allrows if x['label'].endswith('-base')}
for x in allrows:assert x['input_hashes']==base[x['label'].split('-')[0]]['input_hashes']
latest=[x for x in allrows if x['label'].endswith('-release-native')]
assert all(x['native_loaded'] and x['native_cells'] and x['termination']=='survey_complete' for x in latest)
scorelines=[]
for x in latest:
    card=x['label'].split('-')[0];b=base[card];c=x['counts'];bc=b['counts'];clock=x['clock']
    scorelines.append(f"| {card} | {b['total']:.6f} | {x['total']:.6f} | {x['total']-b['total']:+.6f} | {bc['required_missing']} → {c['required_missing']} | {c['observation_requests_completed']}/{c['observation_requests_issued']} | {clock['charged_seconds']:.3f} |")
report='''# v3.6 调度框架验证（2026-10-07）

已完成异常估计、工程事件队列、必选目标与请求联合规划、CPU 调度四项修改；保留 v3.5 的观测前 inspection 和独立单次曝光账本。源码、数值失败案例、测试和实验登记均保留。此版属于框架修复与可测试交付，不能据此声称全面超越 v3.4。

## 改动

- 异常估计：用可信 program/饱和观测约束天空与吞吐区间，无法识别时保留 inconclusive；去除 0.05 的物理效率地板。曝光级独立证据累计、维修分阶段、失效回放；持续低吞吐触发短诊断，纯零分不单独认证故障，报告和重复零分探测有上限。
- 工程队列：完整来源保留，长文本分块并批量读取；在调用预算内处理，暴露待处理事件供更正。明确 UTC/本地锚点、开始与结束原文，支持延期、更正、取消、重复和跨夜事件；灯测试/停机作为不可用区间，未来事件跨越载体请求的失效时间。成功旧模型回复也必须匹配当前来源摘要。
- 联合规划：按一次完整曝光越过各自门槛计算可行性；维护剩余几何窗口、停机区间、多个请求的最小可行子集与日历竞争。不同光纤的同场成员共享曝光成本；搜索只看前几个窗口时不能伪称最后窗口。保留未进入联合规划的请求奖金，大组回退既有搜索。
- 搜索算力：先形成既有数值搜索的合法方案，再用剩余自身 CPU 做联合搜索；共享 C++ 内核与两条几何分支。限制组合与窗口扫描、保留后续决策额度；失败恢复原方案，二次搜索从相同时间价格开始。接受检查保护预测科学收益的保守下界、必选集合及逐请求进度，预测绝不写成实际完成。
- 模型：operator_nlp 解析文本；anomaly_review 读取 inspection、分类统计、近期与累计误差。随包天文专家 skill 规定时间证据、更正和未识别情况。没有真实 API 调用；本地模拟 HTTP 已走通两条分支的长日志→事件→等待/一次报告全流程。

## 验证与实际评分

108 项自动检查通过；独立审阅另执行 28 项重点检查，并确认最后两处状态修正。上传 ZIP 解压后通过官方清单解析、宿主 C++ 构建及五类 JSONL 请求检查（标准、非默认门槛、100 根光纤、纯 Python、无密钥），重复 decision_sequence 回复完全一致。

以下使用相同冻结输入和 v3.4 代码基线、官方本地引擎/计分器、Python 3.12.14 与真实 native 内核。每卡预算 900 秒计费 CPU，另设 7200 秒运行保护；模型关闭。计费只覆盖代理程序自身，模型等待/网络/引擎模拟不计代理 CPU。宿主原始子进程计量偏小，因此本地对照使用同进程 process_time 包围代理调用并保留平台归一化；接口另由 ZIP 子进程检查。

| 本地卡 | v3.4 | 最终 v3.6 | 分差 | 必选遗漏 | 请求完成 | 计费 CPU 秒 |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(scorelines)+'''

全部最终 native 配对运行正常结束，没有 CPU 额度耗尽或运行保护终止。单卡分差没有统计置信区间；搜索受实际 CPU 时序影响。普通卡仅微小变化，长卡即便减少必选遗漏也可能因科学收益与报告结算损失而总分下降。L1 的科学分数仍有明显退步，不应将该包标记为已认证的普遍提分版本。

## 失败实验与边界

首次版本 normal 370.386109、long 6517.314807、L1 6270.645203（请求仅 1/2）；中间版本 normal 272.738385（请求 1/2）、long 6495.645252、L1 6345.924373。发现共享曝光成本重复计费、有限窗口误当最后窗口、请求与实际候选不一致后逐项修正；失败结果、开关消融和后续结果全部保存，未更换输入或筛选 seed。修正时间价格后首次冻结版遗漏 native 构建，三个纯 Python 完整运行另外登记为回退证据，未与 native 基线冒充等价比较；随后同一源码完整重跑 native 三卡。

真实网站八张卡的初始化输入未随反馈提供，无法仅凭行动日志重放 D1；本轮没有 D1/网站、Linux 容器或真实模型质量验证。纯摩斯/凯撒编码若缺乏可验证的数字、中文或唱名时刻与 UTC 锚点，事件保守拒收。未来天气不可知，当前质量续排只是预测；已发布地形限制不能被模型放宽。调用预算上限可能留下待处理文本；所有时间段均为有限候选搜索，不保证全局最优。保守下界的 Pareto 保护也不保证实际总分不退步。

上传包仅包含运行源码、清单和 skill，构建时编译 native，缺编译器可用 Python 搜索；不包含密钥、二进制或卡片真值。证据包保存全部源码快照、实验结果、日志、输入哈希与登记；重新执行仍需原始本地卡输入/官方 runner 路径。未创建 git commit，独立源码快照作为审计依据。
'''
(OUT/'gosim-runtime-v3.6-validation.md').write_text(report)
(R/'DATA_CONTRACT.md').write_text((R/'DATA_CONTRACT.md').read_text()+'\nFinal source is agent == release-frozen == release-native-frozen (apart from compiled binaries); accepted-frozen is preserved before final time-price/source fixes. Both fallback and native final matrices are separately recorded. Forecast guard protects only a conservative lower bound.\n')
(OUT/'CURRENT.md').write_text('''# Current observer delivery

Latest: [gosim-runtime-v3.6-upload.zip](gosim-runtime-v3.6-upload.zip).
Source: `work/gosim-runtime-v36/agent`; frozen source: `release-native-frozen`.
Validation: [gosim-runtime-v3.6-validation.md](gosim-runtime-v3.6-validation.md).
Offline snapshots/evidence: `gosim-runtime-v3.6-source-validation.zip`.
Checksums: `gosim-runtime-v3.6-artifacts.json`.

Own-result health intervals, verified engineering event queue, bounded required/request group planning, incumbent-first CPU search. Retains v3.5 pre-credit inspection/single-exposure/resync. 108 tests + independent 28-check review; fresh ZIP manifest/build/five JSONL cases and duplicate replay pass. Paired fixed native episodes complete, regressions preserved; no universal score-improvement claim. Read validation table for exact final values. D1/website, Linux and real API not validated; mock model pipeline is tested. No commit; snapshots retained. Prior v3.4/v3.5 packages and evidence remain available.
''')
# Complete source and evidence snapshots; omit host caches/binaries/secrets.
evidencezip=OUT/'gosim-runtime-v3.6-source-validation.zip'
with zipfile.ZipFile(evidencezip,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(R.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name=='.env' or p.suffix in {'.so','.pyc','.zip'}:continue
        z.write(p,'gosim-runtime-v36/'+str(p.relative_to(R)))
    z.write(OUT/'gosim-runtime-v3.6-validation.md','gosim-runtime-v3.6-validation.md')
artifacts=[]
for name in ['gosim-runtime-v3.6-upload.zip','gosim-runtime-v3.6-source-validation.zip','gosim-runtime-v3.6-validation.md']:
    p=OUT/name;artifacts.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(OUT/'gosim-runtime-v3.6-artifacts.json').write_text(json.dumps(artifacts,indent=2)+'\n')
print('\n'.join(scorelines));print(json.dumps(artifacts,indent=2))
