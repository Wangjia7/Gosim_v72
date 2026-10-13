from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,yaml
R=Path(__file__).resolve().parent;E=R/'experiments';V=R/'evidence/final';O=R.parents[1]/'outputs'
def get(name):
 d=json.loads((E/name/'workflow_result.json').read_text())
 m=json.loads((E/name/'source-input-manifest.json').read_text())
 return {'run':name,'total':d['score_report']['total'],'counts':d['score_report']['counts'],
         'components':d['score_report']['components'],'clock':d['fair_clock'],'termination':d['termination_reason'],
         'own_audit':m.get('exposure_review'), 'own_raw_cpu':m.get('own_clock_cpu')}
pairs=[('正常样例 B','baseline-normal-b-900','accepted-normal-b-900'),
 ('L1','baseline-L1-900','candidate-L1-900'),('180 夜晚 / 6000 目标代理样例','baseline-long-900','release-long-900')]
paired=[{'card':label,'baseline':get(a),'candidate':get(b)} for label,a,b in pairs]
all_runs=[get(p.name) for p in sorted(E.iterdir()) if p.is_dir() and (p/'workflow_result.json').exists()]
assert len(all_runs)==9,len(all_runs)
assert all(r['termination']=='survey_complete' for r in all_runs)
(V/'comparison.json').write_text(json.dumps({'paired':paired,'all_runs':all_runs},ensure_ascii=False,indent=2)+'\n')
check=json.loads((E/'gosim-logcpu-v3.4-final-upload-release-check.json').read_text())
report='''# v3.4：累计观测日志审阅与 CPU 额度

交付文件：`gosim-logcpu-v3.4-final-upload.zip`。以已交付 v3.3 为基线，默认保留原有搜索宽度；增加逐曝光增量审阅、跨夜晚质量回看、CPU/保护时限分离，并修正大布局异常证据的失效处理。

## 实测

两版均使用 **每卡 900 标准 CPU 秒**，读取平台 `remaining_real_cpu_seconds` 对应的本机 CPU 秒分配工作；本地独立实际运行保护限设为 7200 秒。引擎模拟和等待不扣 CPU；本程序的日志统计、JSON 处理、Python/C++ 和本地线程实际占用的 CPU 仍计入。

| 样例 | v3.3 | v3.4 | 差值 | 必观测遗漏 | 请求完成 | 标准 CPU（旧→新） | 本机 CPU（旧→新） |
|---|---:|---:|---:|---|---|---|---|
'''
for p in paired:
 b,c=p['baseline'],p['candidate'];bc,cc=b['counts'],c['counts'];bf,cf=b['clock'],c['clock']
 report+=f"| {p['card']} | {b['total']:.3f} | {c['total']:.3f} | {c['total']-b['total']:+.3f} | {bc['required_missing']} → {cc['required_missing']} | {bc['observation_requests_completed']}/{bc['observation_requests_issued']} → {cc['observation_requests_completed']}/{cc['observation_requests_issued']} | {bf['charged_seconds']:.3f} → {cf['charged_seconds']:.3f} | {bf['cpu_seconds']:.3f} → {cf['cpu_seconds']:.3f} |\n"
long=paired[-1];b,c=long['baseline'],long['candidate']
report+=f"\n长代理样例总分提高 {(c['total']/b['total']-1)*100:.2f}%，包含请求奖励和必观测罚分的改善；不能全部归因为光谱质量提高。分数组件见 `comparison.json`。新版累计日志留下 {c['own_audit']['checkpoint']} 次审阅检查点，已处理反馈中 {c['own_audit']['valid_exposures']} 次有效曝光、{c['own_audit']['invalidated_exposures']} 次失效曝光；评测器的 invalidated_observations 是目标观测行数，单位不同。\n"
report+='''
这是固定输入的一次对照，不是盲测或多 seed 泛化认证。D1 本体/实际日志未提供，180 夜晚样例只是本地工作量代理，实际运行约 89 秒，不代表 D1 的实际运行时长。D1 日志/引擎量更大导致运行时间超过 900 秒时，不能据此判定 CPU 耗尽；按平台独立保护倒计时判断。

## 日志怎样参与观测

- 每次收到曝光反馈，将命中、漏失、零分、program、时长、类别、曝光索引、时间和维修阶段写入自己的紧凑日志；重复反馈不重复记账。
- 每 8 次曝光、夜晚切换或数据失效时审阅。最近 64 次曝光用于近期/此前独立曝光比较；最近 8 个夜晚/维修阶段的质量区间用于跨夜回看；类别/program/时长计数覆盖累计有效历史。
- 非饱和质量区间由单次原始因子可行区间除以公开天空模型因子得到，先于学习的吞吐尺度归一化，避免自适应尺度掩盖持续下降。已知全局天气、地震和区域污染分别过滤；其他方向的已知天气不自动抹掉清洁视场证据。饱和/模糊 program 结果不当成精确吞吐。
- 摘要进入 `anomaly_review`，保留具体曝光 IDs 与时间；支持几何、吞吐、天气混杂的审阅提示。提示不能直接发起故障报告，也不能认证 raw 完成度，更不能把多次部分曝光相加。
- 失效区间会撤销对应曝光的分组和夜晚统计。维修后质量比较另起 epoch。大布局分支同时清除失效数据派生的 E/质量/波段缓存及旧模型判断，保留报告额度与物理几何证据。
- 两个 LLM 流程保留严格 schema、ID、引用、有效期和版本验证。模型总调用上限仍为 48，正常异常审阅按剩余观测机会分配，新的明显异常可以提前审阅；每个新日志版本使旧审阅失效。只在本地模拟模型中验证，没有真实 API 调用。

## CPU 与运行时间

`AgentClock` 优先使用平台提供的 CPU 余量，缺失时使用初始化额度（默认 900）和自身轮次 CPU 计数。实际模型/网络等待、引擎两轮之间的工作不扣这个计数；已有明确 `charged_wait` 的旧模式另按其声明处理。

正常 CPU 模式的搜索档位由 CPU 成本和 CPU 余量决定，不再用“预计引擎耗时 / 剩余轮数”缩小搜索。实际运行保护限只在接近当前轮所需时间时限流。模型等待分配从独立保护余量得到，去掉原有累计等待 192 秒与引擎耗时预测造成的额外压缩。原生 C++ 仍在程序 CPU 内计费。

新开关为 `FUSION_LOG_REVIEW=1`、`FUSION_MAX_BREADTH=1`。搜索可在实验中扩大至 3 倍，受到每轮 CPU 上限和全局降级策略约束；第一次 3 倍冒烟总分为 339.122、遗漏 5，基线为 379.935、遗漏 4，未作为默认优化开关。保留了该原型及中期长样例的 6687.297 分结果。

## 验证与可复现边界

59 项测试通过，包括实际空闲等待与轮间 CPU 工作的计费隔离、长引擎间隔不影响 CPU 搜索档位、保护限仍有效、日志去重/撤销/跨夜/维修阶段、清洁质量区间、天气混杂、quota 在长巡天中分配、旧审阅过期、共同 program、请求窗口与 C++/Python 一致性。

解压最终 ZIP 到新目录，使用官方 ProjectManifest parser，重新构建 C++，验证标准小布局、非默认 required、大布局三种 JSONL 路由、无密钥与 Python 回退；包不含密钥、`.env`、真值、卡片或宿主二进制。打包曾因新增 `OBSERVER_` 前缀被平台保留规则拒收，已改用私有 `FUSION_` 前缀并通过最终校验；没有在 manifest 放入凭据。

数值对照全部使用原生 macOS Python 3.12.14、冻结官方 workflow/scorer 和同进程 process_time hook；模型关闭。9 次完整对局的输入/source/环境哈希、分数、原始动作、观察、计费与全部原型失败测试日志均保留。标准 CPU 与实际 CPU 因机器校准系数不同而不相等；未估计 CPU 自适应轨迹方差。旧版 v3.3 的 180 秒结果不与本表混排。

L1 数值模块自对照以来未改变。长巡天数值回放缓存修正由 release-long-900 验证。之后增加的大布局模型审阅过期保护只在模型开启时执行，另有模拟模型测试；最终再将私有环境开关改名以符合 manifest，同值控制参数与数值算法不变，最终源码的 normal-b 重新跑完整季节得到同分。每次源码快照分别归档，不能只凭一个工作目录假设所有实验使用同一字节版本。

真实网站/Linux 容器/cgroup 和真实远程 API 尚未测试。重跑需原始任务卡数据；上传只含代理接口与源码。后续优先用这个最终 ZIP 在网站 D1 测试，并提供卡片或观测日志路径以作针对性复核。

'''
report+=f"ZIP {check['bytes']} 字节，SHA256 `{check['sha256']}`。\n"
(O/'gosim-logcpu-v3.4-validation.md').write_text(report);(V/'validation.md').write_text(report)
metrics={'paired_scores':{'value':paired,'unit':'score','sample_count':3,'denominator':'one complete task card per algorithm','artifact':'comparison.json'},
 'smoke_score':{'value':get('accepted-normal-b-900')['total'],'unit':'score','sample_count':1,'denominator':'one exact-final full smoke episode'},
 'tests':{'value':59,'unit':'count','sample_count':59,'denominator':'59 distinct checks on native Python3.12'},
 'zip_valid':{'value':1,'unit':'boolean','sample_count':1,'denominator':'one fresh extracted final archive'}}
(V/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
config=yaml.safe_load((R/'experiments/configs/accepted-plan.yaml').read_text());(V/'config.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
manifests=[json.loads((p/'source-input-manifest.json').read_text()) for p in E.iterdir() if p.is_dir() and (p/'source-input-manifest.json').exists()]
(V/'times.json').write_text(json.dumps({'started_at':min(m['start'] for m in manifests),'ended_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
(V/'release-check.json').write_text(json.dumps(check,indent=2)+'\n')
(O/'CURRENT.md').write_text('''Current release: gosim-logcpu-v3.4-final-upload.zip, source work/gosim-logcpu-v34/agent. Cumulative own exposure/night/class review and CPU-only pacing. Private manifest switches FUSION_LOG_REVIEW=1 and FUSION_MAX_BREADTH=1. 59 Python3.12 checks and fresh ZIP builds/routes pass. 9 complete 900-standard-CPU local runs retained; local independent wall cap 7200. Normal-b/L1 unchanged vs v3.3; 180-night proxy 6452.893→6662.998, requests 1/2→2/2, required missing 1→0. D1/real website/API not tested. Scores use models off. API-only freshness patch and private switch rename have separate tests/final normal-b check, unchanged numeric rules. Next: website D1 evidence; do not adopt unvalidated 3x breadth by default.
''')
print(json.dumps({'report':str(O/'gosim-logcpu-v3.4-validation.md'),'paired':[{'card':p['card'],'delta':p['candidate']['total']-p['baseline']['total']} for p in paired],'runs':len(all_runs)},ensure_ascii=False))
