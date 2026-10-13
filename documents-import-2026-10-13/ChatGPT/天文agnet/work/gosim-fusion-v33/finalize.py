from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,platform,sys,yaml,zipfile
R=Path(__file__).resolve().parent;E=R/'experiments';O=R.parents[1]/'outputs'
V=R/'evidence/final';V.mkdir(parents=True,exist_ok=True)
def get(name):
 d=json.loads((E/name/'workflow_result.json').read_text())
 return {'run':name,'total':d['score_report']['total'],'components':d['score_report']['components'],
    'counts':d['score_report']['counts'],'clock':d['fair_clock'],'termination':d['termination_reason']}
pairs=[('L1','local-L1-native-r2','incoming-L1-r1','final-steady-L1-r6'),
       ('L2','local-L2-native-r2','incoming-L2-r1','final-steady-L2-r6'),
       ('正常场景 A','local-normal-a-native-r2','incoming-normal-a-r1','final-steady-normal-a-r6'),
       ('正常场景 B','local-normal-b-native-r2','incoming-normal-b-r1','final-steady-normal-b-r6'),
       ('100 光纤密集场景',None,'incoming-dense-r1','final-steady-dense-r6')]
rows=[{'card':label,'local':get(local) if local else None,'incoming':get(upstream),'fusion':get(fusion)} for label,local,upstream,fusion in pairs]
all_runs=[get(p.name) for p in sorted(E.iterdir()) if p.is_dir() and (p/'workflow_result.json').exists()]
assert len(all_runs)==32,len(all_runs)
assert all(r['termination']=='survey_complete' for r in all_runs)
(V/'comparison.json').write_text(json.dumps({'paired':rows,'all_runs':all_runs},ensure_ascii=False,indent=2)+'\n')
check=json.loads((E/'gosim-fusion-v3.3-upload-release-check.json').read_text())
report='''# 天文观测调度项目对比与融合 v3.3

交付：`gosim-fusion-v3.3-upload.zip`，根目录接口完整。对比对象是用户提供的 participant ZIP 与本地 v3.2，最终数值核心以附件算法为基础，合入本地的共同 program 边际收益、C++ 批量评估、曝光账本、失效回放、请求窗口和受约束 LLM 流程；大布局保留本地 enhanced 分支。

## 实测结论

融合版相对本地 v3.2 的四个复测场景均提分，但没有全面超过附件。两个正常小布局场景与附件基本持平；L1、L2、100 光纤场景这次最终运行略低。接口与状态处理方面的改进有测试证据，不能将其等同于所有未知卡片得分改善。

每例 180 标准 CPU 秒，360 秒实时时限。所有模型调用关闭，不进行真实 API 请求。下表为单次完整季节的官方评分。

| 场景 | 本地 v3.2（C++） | 附件 | 融合版 | 融合−本地 | 融合−附件 | 必观测遗漏（本地/附件/融合） | 融合请求完成 |
|---|---:|---:|---:|---:|---:|---|---|
'''
for row in rows:
 l,u,f=row['local'],row['incoming'],row['fusion'];c=f['counts']
 report+=f"| {row['card']} | {l['total']:.3f}" if l else f"| {row['card']} | 未复测"
 report+=f" | {u['total']:.3f} | {f['total']:.3f} | "+(f"{f['total']-l['total']:+.3f}" if l else '—')+f" | {f['total']-u['total']:+.3f} | "+(str(l['counts']['required_missing']) if l else '—')+f"/{u['counts']['required_missing']}/{c['required_missing']} | {c['observation_requests_completed']}/{c['observation_requests_issued']} |\n"
report+='''
这不是独立盲测：A/B 输入来自此前本地生成卡（seed 2026100617/2026100618），结果用于诊断实现。真实 CPU 计时决定搜索档位，主机校准/并发负载会影响动作轨迹，未估计分数误差条。相同大布局分支在前一完整运行得到 2597.256，本次得到 2522.010；不应把几十分的差值视为稳定排名。大布局本地列未另跑基线。

## 两者优点怎样组合

- 附件：天区/LST 时间供需与未来机会价格、密集区锚点、CPU 有余量时宽搜索、按实际观测速率预估剩余决策、4% 算力预留、光纤边缘偏移概率、曝光级变点及 program-band 效率证据、无科学收益时的短监测曝光。
- 本地：整次曝光使用同一个 program 后的真实边际科学增分，C++ 批量候选评估与 Python 回退；独立最佳分数/原始因子下界；重复 observe_index 和 decision_sequence 去重；按 action 区间失效回放，维修前后的质量学习隔离；每个请求分别检查完整曝光截止窗口。
- LLM：保留本地的 `operator_nlp` 与 `anomaly_review`、天文专家 skill、严格 JSON/ID/来源/有效期校验、有限调用/并发/等待、无密钥可运行。新曝光/重同步使旧版本异常审阅失效。报告需要数值证据，LLM 不直接认证曝光达标。
- 路由：公开标准小布局走融合核心；超过 16 根光纤或非默认 required 门槛/罚分走本地 enhanced。初始数据无法可靠判断隐藏故障；整季使用同一个代理，从自己的反馈学习异常。没有按卡名或真值切换。

## 合并时修复与保留的边界

- 按 `_pace` 实际选出的搜索档位/宽搜索状态记录 CPU 成本。
- 原始完成度下界用可行 program 乘子的上界反推，并独立取单次曝光最大值。较差科学分数的一次曝光仍可贡献较高 raw 下界。原始因子不累计；先处理在途曝光，再处理失效通知；报告额度不会在重同步时重置。
- 已完成、过期、目标尚未升起或无法容纳最短曝光的请求不重复获奖；重叠请求使用各自门槛与截止时间。窗口是公开几何上界，不保证在天气/容量不足时所有 req 可达标；遗漏数量如表。
- BandFit 的评分配置属于每个实例，避免不同卡片互相污染。方向污染命中不进入共享天气的 band 区间推断；无命中视为几何问题，不当作关闭。区间依赖共享天气和近似天空模型，不能用作原始因子认证。
- 月亮历元与目标高度/LST 保持一致：主搜索在曝光起点建模，监测使用对应的曝光中点。
- 曝光结束时收到的新天气条件会过滤在途异常样本。重复发布、已经在曝光开始时已知的持续天气不会被再次剔除；否则故障校准会被长期屏蔽。地震不作为天气过滤掉 program-band 证据。
- 默认关闭附件中固定常数的地震恢复曲线（`FUSION_QUAKE_CURVE=0`），地震期间保留相对下降证据。继承的其他故障阈值仍是启发式，附件注释中的高分/样本量没有独立实测文件支持。
- 固定 UTC 时刻报告和开发命中转储已从融合运行代码删除。运行只读取 initialize/公开消息/自己的观测结果；上传包不带卡片、真值、密钥或宿主二进制。

## 验证与限制

39 项测试在 Python 3.10 和原生 Python 3.12 分别通过，覆盖保留的本地模块及新增融合核心。包括共同 program 边际收益、C++/Python 选择与 tie 一致性、监测路径、请求完整窗口、数据失效/维修 epoch/重复反馈、独立 raw 最大值、实例评分隔离、地震/新天气/持续天气过滤、实际 CPU 档位，以及两个本地模拟 LLM 流程与过期证据拒绝。

ZIP 经官方 `ProjectManifest` parser 解析，解压到新目录，重新编译并运行正常、非默认 required 和大布局三种 JSONL 路由；另检查 Python 回退、无密钥启动和重复 sequence。只验证了 macOS 宿主，Linux 容器/cgroup、网站运行与远程 API 尚未验证。

最初两轮 local-r1 未构建 C++，作为 Python 回退诊断保留；正式本地表格使用重新构建后的 native-r2。官方 macOS 子进程 CPU meter 在这台主机的 Python 3.10 环境低报约 41.7 倍，因此复用冻结官方 workflow/scorer，在每轮外包裹同进程 `time.process_time` CPU hook；未修改评分器或预算。入口 ZIP 的子进程协议另行检查。输入/source 哈希、环境、校准、全部动作和观察保留在证据归档。

32 次完整评分对局及原型失败测试日志全部保留。曾经尝试“本地 + 附件机会定价”、中期 Moon 取样、过宽天气过滤等方案，其中存在退步；它们不作为最终默认包，记录没有删除。评分预算和原型日志归档属于事后证据登记，不宣称预注册统计实验。

'''
report+=f"上传 ZIP：{check['bytes']} 字节；SHA256 `{check['sha256']}`。\n"
(O/'gosim-fusion-v3.3-comparison.md').write_text(report)
(V/'gosim-fusion-v3.3-comparison.md').write_text(report)
(V/'release-check.json').write_text(json.dumps(check,indent=2)+'\n')
lock=f'Numerical experiments: {sys.executable}\nPython {sys.version}\nPlatform {platform.platform()}\nstdlib only; C++17, -O3, -ffp-contract=off; source-compiled binary\nProtocol/build tests: native Python 3.12.14\nFrozen official workflow: work/gosim-desi-v300/runner\n'
(R/'dependency-lock.txt').write_text(lock)
metrics={'scores':{'value':rows,'unit':'score','sample_count':5,'denominator':'one complete official task card per row; one run each algorithm', 'artifact':'comparison.json'},
 'all_experiments':{'value':all_runs,'unit':'score','sample_count':32,'denominator':'all 32 complete local workflow runs including prototypes','artifact':'comparison.json'},
 'tests':{'value':{'python310':39,'python312':39},'unit':'count','sample_count':39,'denominator':'39 distinct boundary/integration checks'},
 'zip_valid':{'value':1,'unit':'boolean','sample_count':1,'denominator':'one extracted final upload archive'}}
(V/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
manifests=[json.loads((p/'source-input-manifest.json').read_text()) for p in E.iterdir() if p.is_dir() and (p/'source-input-manifest.json').exists()]
identity=hashlib.sha256((V/'comparison.json').read_bytes()).hexdigest()
config={'schema_version':1,'experiment_id':'gosim-fusion-v33-comparison','project_id':'astronomy-observer','parent_run_id':None,
 'hypothesis':'Combine incoming season/fault search with local program/replay/request/LLM correctness; measure scores without assuming universal improvement.',
 'baseline':'incoming-L1/L2/normal-a/normal-b/dense-r1 and native local-r2; immutable source snapshots',
 'command':'run_cpu.py --family <family> --card <card> --out <unique-run> --budget 180; unittest; verify_py312.py; package.py (commands recorded retrospectively)',
 'output_dir':'evidence/final','data_contract_revision':'DATA_CONTRACT.md-v33',
 'datasets':[{'name':'five fixed local task cards and all intermediate runs','version':'frozen official v4 scorer and input manifests','uri':'experiments/*/source-input-manifest.json','identity':identity}],
 'random':{'stochastic':False,'seed':None,'rng':'no runtime agent RNG; pre-generated input cards are fixed','stream_policy':'same target/weather/request truth products in paired runs; adaptive timing changes paths'},
 'parallel':{'backend':'independent host processes across cases; serial CPU-charged agent/scorer per run','workers':1,'threads_per_worker':1,'reduction':'serial per fibre; no parallel numerical reduction'},
 'environment':{'dependency_lock':'dependency-lock.txt','hardware':platform.machine(),'software':platform.python_version()+' stdlib, C++17; process CPU hook'},
 'parameters':{'api':False,'standard_cpu_budget':180,'real_cap':360,'FUSION_JOINT_PROGRAM':1,'FUSION_QUAKE_CURVE':0,'max_concurrent_cases':6},
 'controls':{'sample_ids':'same public catalogue target IDs per pair','skeleton':'not-applicable: telescope scheduling',
  'selection':'all completed prototypes retained; no independent final holdout; initial unbuilt local runs not ranked as C++ baseline',
  'units_and_coordinates':'UTC seconds, degrees, alt-az gnomonic square fibre geometry','bin_edges_and_denominator':'one official total per complete task card'},
 'metrics':{k:{'definition':k+' from saved workflow, tests and archive checks','unit':v['unit'],'uncertainty':'single paired scores; host timing variance not estimated'} for k,v in metrics.items()},
 'reproducibility':{'level':'numerical','tolerance':'saved score/action evidence exact; adaptive CPU reruns can differ'},
 'success_criterion':'complete legal episodes and interface checks; tests pass; preserve all regressions, no universal score threshold',
 'budget':{'max_runs':32,'max_walltime_hours':2,'stop_condition':'32 recorded comparisons complete; stop further score tuning; retrospective budget record'}}
(V/'config.yaml').write_text(yaml.safe_dump(config,sort_keys=False,allow_unicode=True))
(R/'DATA_CONTRACT.md').write_text('''# v3.3 comparison data contract

Fixed official L1/L2 cards, prior generated normal-a/normal-b, and prior 100-fibre dense card. Catalogue, calendar, bulletin, forecast, request and private engine inputs are frozen and hashed per run. Runtime agents receive only public messages and own feedback; the trusted offline engine consumes truth. The upload excludes truth and card files. Re-running full scoring requires the original card directories; the validation archive stores hashes and scored traces, not a complete data redistribution. CPU-adaptive reruns may differ. Snapshots preserve all agent variants and runner code. Experiments are retrospectively registered; no pre-registration or blind generalization claim.
''')
(V/'times.json').write_text(json.dumps({'started_at':min(m['start'] for m in manifests),'ended_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
(O/'CURRENT.md').write_text('''Fusion v3.3 delivered with full JSONL interface. Final source: work/gosim-fusion-v33/final-steady. 39 tests pass on Python3.10/3.12. 32 offline scored runs preserved. Four final small-layout scores exceed local v3.2; incoming slightly leads three final rows and normal A is effectively tied. No blind or website test and no remote API run. Next discriminator: same ZIP on website CPU/container; compare confidence across repeated CPU-calibrated runs before changing defaults.
''')
print(json.dumps({'report':str(O/'gosim-fusion-v3.3-comparison.md'),'completed_runs':len(all_runs),'zip':check['zip']},ensure_ascii=False))
