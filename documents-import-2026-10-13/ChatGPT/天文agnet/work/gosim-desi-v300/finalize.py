from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,os,platform,subprocess,sys,zipfile
r=Path(__file__).resolve().parent;out=r.parents[1]/'outputs'
# Source/test provenance: benchmark is a prepared inner loop, not total-agent speed.
baselines={x['case']:x for x in json.loads((r/'experiments/matrix-results-v2.json').read_text()) if x['family']=='baseline'}
final=json.loads((r/'experiments/request-guard-results.json').read_text())
lines=[]
for x in final:
 b=baselines[x['case']]
 lines.append(f"| {x['case']} | {b['total']:.2f} | {x['total']:.2f} | {x['total']-b['total']:+.2f} | {b['counts']['required_missing']} → {x['counts']['required_missing']} | {x['counts']['observation_requests_completed']}/{x['counts']['observation_requests_issued']} | {x['fair_clock']['charged_seconds']:.2f} | {x['termination']} |")
long=json.loads((r/'experiments/request-guard-long-held/workflow_result.json').read_text());ls=long['score_report']
l1=json.loads((r/'experiments/request-guard-L1/workflow_result.json').read_text());l1s=l1['score_report']
base_l1=json.loads((r/'experiments/baseline-L1/workflow_result.json').read_text())['score_report']
report=f'''# Observer v3.0 验证结果

最终上传包来自 request-guard-v300-final，读取官方 python-pro 新接口。
本轮按用户选择只做本地验证；真实远程 API 和 Linux 容器未测试。

## 修正布局的同输入配对

每次使用官方公开 runner，同输入、同评分器、120 标准化 CPU 秒。
候选源先冻结再运行；动态 CPU 截断与主机负载会改变动作路径。
全管线比较不是任一独立开关的因果增益证明。

| 场景 | 官方 pro | 最终候选 | 差值 | required missing | 请求 | CPU 预算秒实用 | 结束 |
|---|---:|---:|---:|---|---|---:|---|
'''+ '\n'.join(lines)+f'''

agent_finished 表示智能体主动结束，需结合动作末时刻检查；本轮这些记录
均在最后一晚剩余少于合法最短 60 秒曝光时结束，分数已正常结算。
没有将 CPU 超时部分成绩纳入完整窗口比较。

这些六组数据在早期迭代中已经使用。long 请求被用于诊断候选池拥挤，
因此最终表是回归证据，不应称为完全盲测或稳定普适收益。

L1：最终 {l1s['total']:.2f}，相同 180 秒预算官方 pro {base_l1['total']:.2f}，
差值 {l1s['total']-base_l1['total']:+.2f}；required missing
{base_l1['counts']['required_missing']} → {l1s['counts']['required_missing']}；
请求 {l1s['counts']['observation_requests_completed']}/{l1s['counts']['observation_requests_issued']}；
最终结束 {l1['termination_reason']}。没有宣称原四卡不退步或取代旧高分版本。

## 180 夜长任务

6000 目标，实际100根光纤、0.16 deg²单格，180 夜，120 标准化 CPU秒预算。
最终得分 {ls['total']:.2f}，required missing {ls['counts']['required_missing']}，
请求 {ls['counts']['observation_requests_completed']}/{ls['counts']['observation_requests_issued']}，
使用 {long['fair_clock']['charged_seconds']:.3f} 标准化 CPU秒，
实际 CPU {long['fair_clock']['cpu_seconds']:.3f} 秒，结束 {long['termination_reason']}。

修复前同100纤长任务完成全部required，但只完成1/2请求。事后独立真值扫描
显示第一请求8个目标各自都有factor达到1的机会；扫描忽略共享时间/几何约束，
不能证明完整联合可行，但足以拒绝“每个目标均天气不可达”的解释。
修复将活动请求从全局required代理池中显式保留，并按最后合法开曝时刻排序；
同时限制miss保护边距不超过单格25%，防止历史miss永久拒绝新请求目标。
请求奖励随预测单次factor的安全余量提升，避免给刚达阈值的预测全部奖励。
数据真值扫描脚本不进入上传包。

## 测试与接口

23项有意义测试通过：动态1/9/16/25/100纤；官方共享边界、有间隙；native与
Python逐格赢家一致；截止/重叠请求；单次最佳与raw上下界；短曝光不累加；
state_resync撤销重放；偏移独立后续验证/全miss拒绝；CPU截止后返回incumbent；
拥挤候选池保留deadline目标；两角色模拟chat/completions请求；类偏好源引用；
旧账本/过期消息/未知ID/坏数组/重复键/NaN/截断响应拒绝；JSONL单响应。

专家skill通过官方quick_validate，两个LLM system prompts实际读取它。
模拟API传输验证了operator_nlp/anomaly_review，没有发送真实供应商请求。
错误、超时、陈旧结果保留规则策略；付费报告依赖数值证据门。

保存的官方manifest解析器通过，按照manifest的build/run在主机上编译并
产生一条合法JSONL动作。ZIP根目录清单、run一维argv、密钥/本机二进制排除
已检查；Docker不可用，所以Linux镜像准备需在网站验证。

C++prepared inner-loop benchmark：600目标、100纤、15个T/program组合，
150次平均，比Python内循环快84.52倍；不含收益表构建，不代表端到端提速。
源码和指标在native-benchmark.json，不能替换实跑CPU比较。

## 保留的失败与范围

最初离线生成器把fiber参数写到field之外，使六场与第一长任务实际仍16纤，
单格0.4；它们的输入和结果保留并标记，不能作为多布局证据。
修正inputs在cases-v2，最终表只使用这些实际布局。
初次复杂候选L1为5502.10，性能下降；缓存收益与只返回native赢家后5881.94，
最终再次复测如上。最初16纤实验及修正布局后的未修复deadline版均保留。

历史v0251联合包与patient geometry有局部正证据；不是每一项开关都独立证明。
本轮复用几何的未来验证/回滚和公开Q/B区分，没有直接套用旧版本成绩。
光纤偏移假设当前有0.20度/单格35%的较小范围界限；范围外诊断未证明。
当前数值质量依赖近似曝光中点模型、粗天气公告与经验估计，没有整季最优性证明。
公开类别没有额外计分倍率；未新增DESI物理项改变官方scorer。

## 复现

```sh
python3 runner/verify_engine.py
python3 agent/build_native.py
python3 -m unittest discover -s tests -v
python3 generate_cases.py
python3 generate_long.py
```

研究包含原始结果和case真值，仅用于本地复现，不能上传为参赛项目。
生产ZIP只含agent目录下代码、manifest、README、许可证和专家skill。
'''
(r/'VALIDATION.md').write_text(report)
(r/'CURRENT.md').write_text(f'''# Observer v3.0 交接

最终生产源 request-guard-v300-final，上传 final-upload.zip。23测试通过，官方runner17文件hash一致，专家skill验证通过，manifest主机构建/JSONL验证通过。
180夜/6000目标/100纤最终分{ls['total']:.6f}，required缺失{ls['counts']['required_missing']}，请求{ls['counts']['observation_requests_completed']}/{ls['counts']['observation_requests_issued']}，CPU{long['fair_clock']['charged_seconds']:.3f}/120，{long['termination_reason']}。
L1最终{l1s['total']:.6f}，官方基线{base_l1['total']:.6f}。存在回归，不能宣称普遍提分。
用户选先本地验证和ZIP，真实API未测。Linux Docker构建未测。网站不提供原生human chat字段，随包operator_cli旁路适配。
初次generator的field层级错位原结果保留；cases-v2用于正确多布局证据。最后因长卡请求池拥挤补保留deadline anchors，全部修正布局及L1重新回归。详见VALIDATION.md。
''')
summary={'final_numeric_family':'request-guard-v300-final','tests_passed':23,'remote_api_tested':False,
 'paired_rows':[{**x,'baseline_total':baselines[x['case']]['total'],'delta':x['total']-baselines[x['case']]['total']} for x in final],
 'long':long,'L1':l1,'limitations':['regressions retained','not blind final holdout','no Linux container test','no remote API']}
(r/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('report written',ls['total'],l1s['total'])
