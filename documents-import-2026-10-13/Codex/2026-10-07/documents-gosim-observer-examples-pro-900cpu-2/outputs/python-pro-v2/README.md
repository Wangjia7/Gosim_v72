# GOSIM Python Pro v2.0.0（实验优化版）

基于 `Documents/gosim-observer-examples/python-pro` 的独立版本，保持标准库依赖与 `participant-agent-protocol-v4`。原目录不变。原版说明保存在 `UPSTREAM_README.md` / `UPSTREAM_README.zh.md`；其中的历史成绩不代表 v2。

## 本版改动

- 光纤数量、中央候选和单位光纤时间成本由协议布局决定；邻域覆盖 anchor 到对角视场边缘及指向微调余量，支持 RA 跨零与极区查询。
- 请求逐条保留开始、截止、门槛和奖励。只有完整曝光在窗口内才估算请求收益；不同门槛的重叠请求独立计奖。
- 最短合法曝光即可进入可见候选，时长始终限制在仪器范围、剩余夜间和目标可见窗口内。
- 先搜索粗时长，再为领先视场加入饱和、required/request 门槛、项目档位、落下时刻、夜末及截止断点，搜索断点两侧整数秒并局部细化。
- 质量模型使用起点／中点／终点的公开月亮和气团质量，积分三点二次近似；它仍是天气未知时的预测，不是裁判真值。
- `cur` 表示官方最高得分，`factor_history` 表示本地逐曝光完成因子估计。状态更正按 `observe_index` 删除失效历史，再重建最大有效因子，避免最高分与 required 完成混用。
- 根据剩余真实 CPU、墙钟及预计决策数控制搜索；保留合法候选后可提前结束，修复速度档耗时串档和紧急档数组越界。
- 光纤偏移搜索保持与引擎一致的 `actual = command + offset`；检查指令可达性及并列解均值的真实命中一致性。

## 使用

运行无模型回归：

```bash
OBSERVER_MODEL_DISABLED=1 python3 -m unittest discover -s tests -v
```

使用官方本地裁判（路径按本机调整；900 是标准化 CPU 秒，另有墙钟上限）：

```bash
OBSERVER_MODEL_DISABLED=1 python3 /Users/jqwang/Documents/gosim-observer-examples/runner/run_local.py \
  --inherit-env --card /Users/jqwang/Documents/gosim-observer-examples/local-cards/L1 \
  --agent "python3 agent.py" --agent-cwd . --wallclock 900 --out /tmp/gosim-v2-L1
```

接入模型：复制 `.env.example` 为 `.env`，配置 `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`，然后由裁判启动。保留原版 OpenAI-compatible `/chat/completions` 接口与 Kimi 默认配置；打包不会包含 `.env`。

```bash
python3 pack_agent.py --out ../python-pro-v2.0.0.zip
```

## 每步复盘与读取日志

`StepReviewer.record` 每步接收上一动作、本步结果、下一动作、剩余预算、请求窗口与规划诊断。模型调用后台执行，无同步等待，不修改官方状态、不直接下达指令。输出是复盘建议，供日志分析和后续策略迭代使用。原版夜间建议及故障报告确认仍照常工作。

| 环境变量 | 默认 | 含义 |
|---|---:|---|
| `PRO_STEP_REVIEW` | `1` | 模型可用时启用后台逐步复盘接口 |
| `PRO_REVIEW_EVERY` | `1` | 每多少步尝试提交一次 |
| `PRO_REVIEW_MAX_CALLS` | `120` | 单季复盘调用上限，独立于夜间调用 |
| `PRO_REVIEW_LOG` | 空 | 可选 JSONL 审计文件；记录每步输入及已收到回复 |
| `PRO_DURATION_LEADERS` | `3` | 最多对几个领先视场细化时长，随搜索档降低 |
| `PRO_BREAKPOINT_TARGETS` | `24` | 每个领先视场最多为几个目标生成断点 |
| `PRO_FIXED_LEVEL` | `-1` | 自适应；非负值固定档位，供确定性算法对照 |

每步都触发接口；网络来不及时合并最近最多 16 步，旧记录的丢弃数量随请求上报。达到调用上限、剩余预算不足或模型被关闭时跳过网络调用；已启用的本地审计仍记录每步。每次最多一条复盘调用在途，为原版夜间调用预留并发槽。迟到回复标注原步骤与接收步骤，仅作为历史复盘。

日志阅读工具默认只生成发送预览：

```bash
python3 review_logs.py /path/to/agent.log --out /tmp/review-input.json
python3 review_logs.py /path/to/agent.log --send --out /tmp/review-result.json
```

`--send` 才调用配置的模型。工具只读取日志末尾，默认 48 KB；已知 API key 会被遮盖，日志中的自然语言作为不可信证据处理。模型返回须通过 JSON/schema 校验，失败不会改变观测数据。完整审计建议保存到项目外，避免打包进提交 ZIP。

## 版本与验证

源目录没有 Git 元数据。`SOURCE_MANIFEST.json` 保存原版逐文件 SHA-256；本目录独立 Git 仓库保存基线和 v2 修改，未推送远端。验证结果见 `VALIDATION.md`，已知限制与设计取舍见 `DECISIONS.md`。

全季得分可能随卡片和自适应搜索时序下降，不能把本版当作已证实普遍提分的策略；实测结果见 `VALIDATION.md`。

本地 factor 来自公开 score 和项目匹配的估计；协议未公开真实 factor，因此无法保证 required 估计完全准确。状态更正不再从最高分伪造 factor；若缺少可用历史，按未知／未确认完成处理。搜索保留启发式 anchor 和池大小限制，邻域补全不等同于穷举全天所有指向。

许可沿用 CC BY-NC 4.0，见 `LICENSE.md`。来源：GOSIM 2026 Agentic Observer Hackathon。
