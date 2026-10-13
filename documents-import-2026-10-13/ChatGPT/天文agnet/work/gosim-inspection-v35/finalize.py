from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
R=Path(__file__).resolve().parent;E=R/'experiments';V=R/'evidence/final';O=R.parents[1]/'outputs'
V.mkdir(parents=True,exist_ok=True)
def get(name):
 d=json.loads((E/name/'workflow_result.json').read_text());m=json.loads((E/name/'source-input-manifest.json').read_text())
 return {'run':name,'total':d['score_report']['total'],'counts':d['score_report']['counts'],
 'components':d['score_report']['components'],'clock':d['fair_clock'],'termination':d['termination_reason'],
 'source_manifest':str(E/name/'source-input-manifest.json'),'own_raw_cpu':m.get('own_clock_cpu'),
 'start':m['start'],'end':m['end'],'inspection':m.get('exposure_review',{}).get('inspection',{})}
names=['baseline-normal-b-900','candidate-normal-b-900','baseline-long-900','candidate-long-900','final-normal-b-900','final-long-900']
runs=[get(n) for n in names];assert all(r['termination']=='survey_complete' for r in runs)
check=json.loads((E/'gosim-inspection-v3.5-upload-release-check.json').read_text())
source=R/'agent'
import zipfile
with zipfile.ZipFile(check['zip']) as z:
 expected={str(p.relative_to(source)):p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.so','.dll','.dylib','.zip') and p.name!='.env'}
 assert set(z.namelist())==set(expected)
 assert all(z.read(name)==p.read_bytes() for name,p in expected.items())
final=get('final-long-900');base=get('baseline-long-900');diff=final['total']-base['total']
comparison={'runs':runs,'final_long_difference':diff,'final_source_matches_zip':True,'performance_claim':'not established; final long proxy is lower than baseline; fixed inputs and no variance estimate'}
(V/'comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n')
for file in ('tests-python312-final.log','dependency-lock.txt','DATA_CONTRACT.md'):
 shutil.copy2(R/file,V/file)
shutil.copy2(E/'gosim-inspection-v3.5-upload-release-check.json',V/'release-check.json')
report='''# v3.5：曝光检查与可回放科学收益账本

交付：`gosim-inspection-v3.5-upload.zip`；JSONL-v4 / Python3.12 / 本机构建 C++，无需密钥可运行。

本次依据所附 PFS 讨论实现适用于 Survey26 的工程闭环。附件作为参考资料，不改变计分协议；没有把 PFS 的累计 EET 或附件的卡名/program 名称写入策略。

## 代码变化

1. 新增 `inspection.py`，普通与大光纤/特殊阈值分支都执行 observe → inspect → realized credit → 原有 planner state → replan。保存请求的指向、光纤分配、时长、program、预测，以及实际返回的命中目标和分数。计划、LLM 建议都不能直接认证完成。
2. 更新前检查 observe_index、重复目标、计划外目标、非有限/负数/超配置上限分数、缺失 hits。重复反馈隔离，不能消费下一次 pending plan。非法或缺失结果不进入科学状态。合法空 hits 与缺失 hits 不同；未命中不会被当成低吞吐的数值测量。
3. 原始 QA 事实以序列化 JSON 保留；失效集合、有效 best score、raw lower 和逐 visit credit 是独立可重算状态。state_resync 撤回失效 visit，重算幸存曝光的边际收益，同时服从官方 best_scores。即使旧高分失效后让后来曝光重新产生收益，也不篡改原始日志。
4. 科学收益是最佳单次曝光的增量，完成证据是独立 raw-factor 保守最大值，均不叠加短曝光。记录 hit efficiency、science gain/predicted gain 和每秒科学收益；预测收益仅是基于自身 pending 模型重建的 science 项，不含 uniformity、request 或罚分，也不是评分器真值。零分母为 UNKNOWN。
5. 原始测量与 PASS/WARN/UNKNOWN 判断分开保存；按运行时 program、天体类型、required、光纤、曝光长度、天气公告与夜间阶段诊断。低分原因未必可辨识，因此使用 MISS_CAUSE_UNKNOWN、ZERO_SCORE_CAUSE_UNKNOWN、PROGRAM_MISMATCH_CANDIDATE 等保守标签；不凭 miss 确认碰撞/偏移，不凭质量下降确认隐藏故障。
6. 每次反馈增量记录，原有每 8 次曝光/换夜/失效检查点输出最近 8 次有效 visit。输出最多 32 个 population、每 visit 16 个目标并注明总数；完整事实保留。LLM anomaly_review 获得这些分层证据，旧的 numerical report guard 仍生效。没有未经认证的新吞吐训练权重，也没有把未执行的 shadow plan 当成因果证据。

实际 fibre positions、精确 raw factor、真实 program match 和隐藏故障并未由接口返回；字段保持 UNKNOWN/None 或区间。PASS 只针对可测的合法结果与完成证据，不证明天气或仪器正常。缺失数据没有伪造 confidence 数值。

## 验证与分数

66 项回归检查通过；新增 8 个固定 known-good/bad visit 和 7 项 inspection 回放测试，覆盖 required 仅分配不完成、重复不叠加、失效重算、重复反馈隔离、非法/缺失数据与原因不可辨识。保留初次失败的测试日志，修复 enhanced 缺失 pending_notices 的兼容问题及测试 fixture 的错误 mismatch 常数。

原有本地 mock API 两角色检查随回归套件运行。真实 API、网站评分和 Linux 容器未验证。上传 ZIP 在本机新目录解包、C++ 编译、普通/特殊阈值/100 光纤路由及 Python fallback 通过；源文件与 ZIP 字节一致，未包含密钥、truth、宿主二进制或 pyc。

所有数值 episode 使用每卡 900 标准 CPU 秒与独立 7200 秒本地实际运行保护。time.process_time 计入自身代码、日志/检查开销和 C++ CPU；模型/网络等待与引擎模拟不计 CPU。采用既有冻结评测器和正确本机 CPU hook，ZIP 协议另测。不同运行的本机 speed_factor 有差异，计时自适应会影响搜索路径，不能把分数变化全部归因于 inspection。

| 固定任务 | v3.4 本轮基线 | v3.5 首轮 | v3.5 最终 | 最终−基线 | 必需遗漏（基线/首轮/最终） |
|---|---:|---:|---:|---:|---|
'''
for label,b,c,f in [('正常 B',0,1,4),('180 夜 / 6000 目标',2,3,5)]:
 a,x,y=runs[b],runs[c],runs[f]
 report+=f"| {label} | {a['total']:.6f} | {x['total']:.6f} | {y['total']:.6f} | {y['total']-a['total']:+.6f} | {a['counts']['required_missing']}/{x['counts']['required_missing']}/{y['counts']['required_missing']} |\n"
report+=f'''\n六个 episode 均 survey_complete，均完成 2/2 个请求。正常卡持平，最终长代理比分数基线低 {abs(diff):.6f}（{abs(diff)/base['total']*100:.2f}%）；首轮更低，全部保留，未选择最高分作为交付证据。最终复测是因为发现并修复了 QA credit 回放语义问题，未调搜索参数或卡片权重。当前证据支持账本功能与接口正确性，**不支持“分数优于 v3.4”或泛化提升**。以分数为唯一标准时仍需保留 v3.4 对照。

最终长代理原始自身 CPU 为 {final['clock']['cpu_seconds']:.3f} 秒、标准扣费 {final['clock']['charged_seconds']:.3f} 秒、实际运行 {final['clock']['run_wall_seconds']:.3f} 秒。这不是 D1 实际用时；D1 原卡/日志未提供。等待或引擎耗时超过 900 秒并不等于自身 CPU 超限，应看独立保护限。

最终长代理已处理反馈中有 {final['inspection']['valid_exposures']} 次有效 visit、{final['inspection']['invalidated_exposures']} 次失效 visit，检查层拒绝合法结果数为 {final['inspection']['rejected_results']}。评测器 invalidated_observations 是目标观测行数，单位不同。终局未再次投递的 last_result 不在自身账本内；该账本不冒充评测器完整总账。

## 复现材料

`work/gosim-inspection-v35/experiments/` 保留六次评分、原始消息/动作/观测与输入/源码 SHA256。首轮 candidate 源码另存 `numeric-frozen`；最终源码在 `agent`，v3.4 原封不动另存 `baseline`。最终两次验证另外导出 immutable `inspection-ledger.jsonl` 与独立 `inspection-credit.json`。`evidence/final/comparison.json` 包含分数组件和时钟。实验不读取隐藏真值作为 agent 输入，未进行盲测或多 seed 误差估计。

ZIP SHA256：`'''+check['sha256']+'`。\n'
(O/'gosim-inspection-v3.5-validation.md').write_text(report)
metrics={'paired_scores':{'value':{r['run']:r['total'] for r in runs},'unit':'score','artifact':'evidence/final/comparison.json'},
 'tests':{'value':66,'unit':'count','artifact':'tests-python312-final.log'},'zip_valid':{'value':True,'unit':'boolean','artifact':'evidence/final/release-check.json'}}
(R/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
(R/'registration-times.json').write_text(json.dumps({'start':min(r['start'] for r in runs),'end':datetime.now(timezone.utc).isoformat()})+'\n')
print(json.dumps({'runs':len(runs),'final_long_delta':diff,'report':str(O/'gosim-inspection-v3.5-validation.md')},ensure_ascii=False))
