# Observer v3.0 验证结果

最终上传包来自 request-guard-v300-final，读取官方 python-pro 新接口。
本轮按用户选择只做本地验证；真实远程 API 和 Linux 容器未测试。

## 修正布局的同输入配对

每次使用官方公开 runner，同输入、同评分器、120 标准化 CPU 秒。
候选源先冻结再运行；动态 CPU 截断与主机负载会改变动作路径。
全管线比较不是任一独立开关的因果增益证明。

| 场景 | 官方 pro | 最终候选 | 差值 | required missing | 请求 | CPU 预算秒实用 | 结束 |
|---|---:|---:|---:|---|---|---:|---|
| sparse | 371.69 | 341.75 | -29.94 | 0 → 0 | 2/2 | 6.68 | survey_complete |
| dense | 2459.28 | 2563.38 | +104.11 | 0 → 0 | 2/2 | 45.56 | survey_complete |
| stress | 717.66 | 718.63 | +0.97 | 0 → 0 | 2/2 | 10.14 | agent_finished |
| mixed | -595.62 | 820.59 | +1416.21 | 31 → 2 | 2/2 | 16.92 | agent_finished |
| dense-held | 2546.12 | 2645.90 | +99.78 | 0 → 0 | 2/2 | 43.80 | survey_complete |
| stress-held | 498.60 | 671.86 | +173.26 | 1 → 0 | 2/2 | 9.03 | survey_complete |

agent_finished 表示智能体主动结束，需结合动作末时刻检查；本轮这些记录
均在最后一晚剩余少于合法最短 60 秒曝光时结束，分数已正常结算。
没有将 CPU 超时部分成绩纳入完整窗口比较。

这些六组数据在早期迭代中已经使用。long 请求被用于诊断候选池拥挤，
因此最终表是回归证据，不应称为完全盲测或稳定普适收益。

L1：最终 5976.63，相同 180 秒预算官方 pro 6125.03，
差值 -148.41；required missing
2 → 2；
请求 2/2；
最终结束 survey_complete。没有宣称原四卡不退步或取代旧高分版本。

## 180 夜长任务

6000 目标，实际100根光纤、0.16 deg²单格，180 夜，120 标准化 CPU秒预算。
最终得分 6678.48，required missing 0，
请求 2/2，
使用 41.718 标准化 CPU秒，
实际 CPU 36.065 秒，结束 survey_complete。

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
