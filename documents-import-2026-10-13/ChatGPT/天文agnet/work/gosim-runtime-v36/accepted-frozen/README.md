# v3.6 runtime control update

JSONL-v4 project. Both numeric geometry kernels share own-result health monitoring, a source/time-checked engineering queue, and bounded group/required obligation planning. No API key continues in rules mode. Model roles are operator_nlp and anomaly_review.

Program/sky constraints that cannot identify throughput remain inconclusive. Matched saturation constrains sky; mismatch-looking scores stay ambiguous. Three independent low diagnostic exposures can support a bounded free probe relative to a healthy reference. Zero exposures alone never certify a fault. A correct repair needs subsequent validation.

Operational text is processed completely in overlapping chunks (up to four same-source chunks per call); future validated events survive request expiry. Start/end clocks, UTC references and corrections/cancellations are checked. Confirmed and rejected events are audited separately; an uncertain event does not discard valid events in the same answer. Purely encoded times without a verifiable numeric/Chinese/solfege clock and UTC anchor remain unaccepted. No arbitrary source code or instructions are executed.

Joint planning accounts for distinct fibres sharing a visit, whole exposure windows, downtime and competing groups. The original legal numeric incumbent is computed first; only spare measured CPU is used for a second search. Acceptance requires forecast science/obligation dominance, not a predicted-completion credit. Larger unmanageable groups retain legacy planning. Ordinary search breadth stays1. All C++ work and local parsing count toward CPU; model/network waits and engine simulation do not.

Final runtime/model audit is written at termination. Full factual inspection stays independent of derived scientific credit; invalidations replay the valid best-single-exposure and raw-bound ledger.

Original implementation notes follow; the v3.6 section supersedes older call budgets/soft-preference descriptions.

# 天文观测调度融合版 v3.5

上传本目录打包的 ZIP；根目录 `observer.project.json` 声明 JSONL v4 接口、构建和运行命令。构建使用宿主 C++17 编译器；不可用时保留 Python 搜索。无需 API 密钥即可运行数值规则。

## 组合方式

| 能力 | 来源与实现 |
|---|---|
| 长期天区/LST 机会定价、密集区锚点、宽搜索、按实测 CPU 成本分配搜索 | 附件项目的 `fusion_core/season.py`、`planner.py`、`agent.py` |
| 偏移网格、光纤边缘落入概率、曝光级故障证据、监测曝光 | 附件算法，保留运行时尺寸/数量/布局读取 |
| 整次曝光共同 program 的真实边际收益 | 本地算法合入附件搜索；`joint.cpp` 批量比较所有 program/时长/光纤分配 |
| 独立最佳科学分数与原始因子下界、重复反馈去重、数据失效回放、维修阶段隔离 | `fusion_core/guarded.py`，保留全部自有反馈，按失效区间重放有效记录 |
| 各请求独立门槛、发出时间、截止时间与剩余可见窗口 | 本地 `Opportunities` 与曝光全时长门控；不可达请求不获得规划奖励 |
| 两个 LLM 流程、结构校验、有限调用/等待、证据与版本验证、无密钥回退 | 本地 `advisor.py`、`llm_client.py` 与 `skills/astronomy-observer/` |
| 大布局/非默认 required 配置 | 沿用本地 enhanced 分支及 C++ 搜索 |

`routing.py` 只使用公开的布局与评分兼容条件选择一个代理并保持其状态；隐藏光纤偏移/故障从观测反馈学习。正常标准小布局进入 `fusion_core`，超过 16 根光纤或非默认 required 门槛/罚分进入本地 enhanced。没有根据卡片名称、隐藏事件或真值切换算法。

曝光收益使用最好一次曝光，逐次部分曝光不相加。Season 的需求量是分配机会的近似代理，不是实际曝光积分或可完成性证明。模型相关的效率区间只用于异常分析，不能认证原始因子达到门槛。

## 模型设置

平台设置 `OBSERVER_MODEL_DISABLED=1` 时不调用模型。未配置密钥也使用数值规则。需要模型时通过环境变量配置 `OPENAI_API_KEY` 和现有客户端支持的服务地址/模型；不要把密钥或 `.env` 打包。

`operator_nlp` 解析调度员文本，校验证据引用、目标/请求 ID 和有效期，产生有限期软偏好。`anomaly_review` 审阅光纤几何、天气、地震、吞吐下降及累计证据。新的曝光或数据失效使旧版本审阅失效；报告仍需数值判据。

## 默认开关与限制

`FUSION_JOINT_PROGRAM=1` 启用共同 program。`FUSION_QUAKE_CURVE=0` 禁用附件中按固定常数推算地震恢复的绝对阈值；地震期保留相对下降证据。附件的故障阈值仍是启发式，不视为已认证泛化效果。

开发用固定时刻报告与命中转储逻辑已从融合运行代码移除。运行时不读取本地卡片或真值。ZIP 不包含平台二进制、API 密钥或训练数据。

详细同预算对比、失败实验与环境边界见交付包旁的 `gosim-logcpu-v3.4-validation.md`。真实网站评分、Linux 容器及远程 API 需另行验证。


## v3.4：日志审阅与 900 秒 CPU 额度

每卡 900 秒是程序自身 CPU 计算额度；平台提供的 `remaining_real_cpu_seconds` 优先，按当前机器 CPU 秒分配搜索。网络/模型等待与两轮之间的引擎模拟不减少这项额度。程序实际编码、解析和日志统计占用的 CPU 仍计入。实际运行保护倒计时独立处理，只在接近保护上限时限流。D1 多夜晚、多日志的引擎时间可能较长，不因此提前停止或主动缩短巡天。

`log_review.py` 每次曝光增量保存自己的观测证据；每 8 次曝光、夜晚切换、数据失效回放时审阅累计日志。按天体类别、program、曝光长短汇总命中/漏失/零分，保留曝光索引和时间，比较近期与此前的独立清洁曝光，并回看最近 8 个夜晚/维修阶段的质量区间。质量区间以公开天空模型归一化，避免自适应吞吐尺度掩盖持续下降。天气、地震、维修 epoch 与失效数据分别处理。日志摘要进入异常 LLM 流程；诊断提示不能直接认证完成度或触发故障报告。

有限的模型审阅额度按剩余观测机会分配，并允许新的明显异常提前审阅；原有 48 次总调用上限不变。等待只受独立保护倒计时限制。默认保持已有候选宽度（`FUSION_MAX_BREADTH=1`），每轮有 CPU 上限。可在对照实验中将该值设为 3，允许 CPU 富余时扩宽候选池/锚点；首次加宽冒烟出现遗漏退步，尚不作为默认优化开关。随着剩余 CPU 减少仍自动降级。


## v3.5：每次曝光的 inspection

新增 `inspection.py`，两个调度分支均在状态更新前检查实际返回结果。
记录 requested 配置和 returned hit/score；只有有效结果进入科学状态。重复 observe_index、
非法分数、重复/计划外目标和缺失 hits 不产生 credit。实际光纤坐标与精确 raw factor 不可见，保持 UNKNOWN。

最佳单次得分和独立保守完成因子不累加。QA 原始事实以不可变 JSON 存储；state_resync
保留这些事实、撤回失效 visit，并重新计算有效 visit 的边际收益。原始测量增益与
重放后的 credit 分开展示，官方 best_scores 快照仍为科学得分权威。

日志 checkpoint 含最近 8 次有效曝光的计划/结果、science gain、预测兑现率及按 program、
天体类别、required、光纤、曝光区间、天气公告、夜间阶段的分组。LLM anomaly_review
可读这些证据，但诊断候选不改变完成阈值、不自动触发故障报告。运行时分组最多展示 32 项，
每个 visit 最多展示 16 个目标并给出总数；完整事实在内存账本保留，本地验证 runner 导出
`inspection-ledger.jsonl` 与独立的 `inspection-credit.json`。

本次不依据少量卡片训练新的吞吐修正权重，也不把未执行方案当成因果对照。
接口仍为 JSONL-v4；900 秒额度仍只计自身 CPU，独立 wall 上限继续保护运行。
完整测试和实际分数差异见交付包旁 `gosim-inspection-v3.5-validation.md`。
