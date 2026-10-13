from pathlib import Path
import json
p=Path('outputs/python-pro-v2'); data=json.loads((p/'validation/benchmark-summary.json').read_text())
rows=data['runs']; lines=[]
for card in ('L1','L3'):
 b,n=[r for r in rows if r['card']==card]
 delta=(n['total']/b['total']-1)*100
 lines.append(f"| {card} | {b['total']:.3f} | {n['total']:.3f} | {delta:+.2f}% | {b['normalized_cpu_seconds']:.3f} / {n['normalized_cpu_seconds']:.3f} | {b['required_missing']} / {n['required_missing']} |")
text='''# v2.0.0 验证记录

测试日期：2026-10-07。原版基线导入提交 `3912b11`；最终调度行为提交 `1892ddd`（后续只追加文档、类型注解和验证记录）。原目录逐文件哈希未变，裁判 17 个引擎文件与原始 ENGINE_MANIFEST.json 全部匹配。

## 最终全季对照

两边都使用原生 `/usr/bin/python3`（3.9.6，arm64），原始 runner、原始练习卡，关闭模型 `OBSERVER_MODEL_DISABLED=1`，默认自适应搜索，900 标准化 CPU 秒预算。卡片/RNG 无修改；输入与引擎哈希保存在 `validation/benchmark-input-hashes.json`。

| 卡 | 原版得分 | v2 得分 | 变化 | 原版 / v2 标准化 CPU 秒 | 原版 / v2 required 未完成 |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(lines)+'''

四次最终对照运行都以 `survey_complete` 结束，没有超 CPU/墙钟预算，没有 `pro: error`；每次都完成了 2 个已发布请求。L3 实际触发 state_resync。**单次本地对照不等于普遍提分；自适应预算分配会随机器速度和时序改变搜索轨迹。** 最终指标、完整分数组成和 agent 日志保存在 `validation/`。

复现命令（在本项目目录运行，将路径替换为本机位置）：

```bash
OBSERVER_MODEL_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 \
  /Users/jqwang/Documents/gosim-observer-examples/runner/run_local.py \
  --inherit-env --card /Users/jqwang/Documents/gosim-observer-examples/local-cards/L1 \
  --agent '/usr/bin/python3 agent.py' --agent-cwd . --wallclock 900 --out /tmp/gosim-v2-L1
```

L3 替换 card 与输出目录。原版复现使用 `upstream-import` 对应工作副本。固定搜索档可减小时序变化，但它绕过本版回合搜索限额，仅适合另外的算法对照，不是上述自适应预算测试的同一条件。

## 回归与独立审查

`python3 -m unittest discover -s tests -v`：**22/22 通过**。记录见 `validation/unit-tests.txt`。涵盖 1/4/16/25 光纤各搜索档、对角视场、RA 跨零/极点、非标准曝光上限、请求截止相等/晚一秒/重叠/短窗口、失效历史、偏移证据与扫描续算/保优、CPU 耗时档位、紧急档模型等待、LLM 非法回答/队列上限/网络失败释放。

独立只读 Reviewer 复审了最终保留的核心逻辑并运行了 21 项测试；随后新增的 180 秒请求测试在撤回粗搜索下限实验后仍通过，总计 22 项。审查记录见 `validation/independent-review.md`。

恒定质量受控样例中，原版选择 750 秒，v2 选择 631 秒，16 根光纤均分配；解析饱和点约 630.928 秒。该结果验证断点搜索机制，不用于推断真实全季收益。见 `validation/controlled-exposure.json`。

## 未筛选的中间结果与限制

- 初始无通用粗搜索下限的版本大量选择 60 秒曝光：L1 409 次，L3 530 次。全季得分为 6088.980 / 6677.167，低于基线约 2.37% / 1.33%。随后实验 300 秒常规粗搜索起点：L1 得 6126.083，L3 得 6336.528（较原版 -6.36%），L3 请求完成从 2/2 降为 1/2，因此撤回该实验，恢复提交 `1892ddd` 的已测调度行为。实验记录见 `validation/rejected-floor-experiment.json`。保留 `validation/pre-floor-*` 作为回退依据。
- 更早候选曾得到 L1 6215.103、L3 6830.992；保存在 `validation/exploratory-benchmarks.json`，未当作最终成绩。尚未做多次重复、完整消融或 L2/L4 全季评估，不能归因某一改动必然提分。
- Conda Python 3.10.9 x86_64 在这台 ARM Mac 上的 runner CPU 读数未通过校验：0.25 秒 process_time 对应约 0.006 秒计量。原生 Python 校验为 0.200002 / 0.200017 秒一致。因此 Conda 早期试跑不作为 CPU 预算证据；未修改裁判代码。
- 没有真实外部 LLM 调用；已验证本地 mock、错误恢复、输入/输出结构及日志预览。真实 API 的延迟、费用和复盘质量未验证。
- required 因子仍是由公开观测得分推断的估计；协议没有暴露真实 factor。状态更正保持官方分数权威，但无法把未知历史变成精确完成状态。
- 本机未运行 manifest 的 Python 3.12 Docker 镜像；代码只用标准库，本地 Python 3.9/3.10 单测通过。
'''
(p/'VALIDATION.md').write_text(text)
