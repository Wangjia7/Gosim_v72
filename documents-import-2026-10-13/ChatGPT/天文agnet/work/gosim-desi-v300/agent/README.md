# GOSIM DESI observer v3.0

以 GOSIM 官方 `python-pro` 为基础的 JSONL-v4 完整上传项目。联合选择指向、光纤、曝光时长和唯一 program；读取本次 initialize 的光纤格数、面积、间隙、曝光上下限和计分常数。

`observer.project.json` 位于 ZIP 根目录，run 为一维参数数组。build 在部署主机编译 `joint.cpp`；找不到编译器时使用 Python 缓存搜索。ZIP 不含本机 `.so`、密钥、卡片或天气真值。已验证保存的官方 manifest 解析器、主机 build/run 和 JSONL；本机没有 Docker，Linux 镜像构建仍需网站验证。

网站注入 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`；兼容 OpenAI chat completions。没有平台配置时默认为官方示例的 Kimi k3。平台选择不提供模型时设置 `OBSERVER_MODEL_DISABLED=1`，执行规则模式。不要把密钥写进 manifest 或 ZIP。

## 调度与科学状态

每目标的最高科学分与最高 raw factor 下界分开保存。只取一次最佳有效曝光，多次短曝光不累加。公开 score 无法唯一反解 program 时，保存 raw 上下界；不会从猜测值认证 required 完成。state_resync 按 observe 编号撤销并重放曝光账本。

连续几何窗口与夜历相交。required 的最后可用机会进入优先级，曝光候选包含阈值和截止点。每个重叠请求分别检查发布/截止时间与门槛，跨窗口不计请求收益。
活动请求显式保留在候选池，并按剩余合法开曝时间排序；预测完成奖励需要阈值以上的安全余量。未知天气、总容量和曝光上限可能使部分要求不可行；此版本没有所有 required 必定完成或全局最优证明。

目标类别不会被私自添加倍率，数值收益由公开 flux、science_weight、天气/月光模型及窗口决定。真实 DESI 的扩展源光纤损失仅作为专家解释的背景。

搜索使用 process CPU 截止点、剩余真实 CPU 预算及决策成本 EMA；API 等待使用独立墙钟预算。C++ 在同一进程中运行，CPU 已计入进程测量。优先得到可返回动作，再扩展候选。C++ 只加速几何及每格择优，不读取隐藏状态。

偏移通过已指派目标与公开 hit IDs 拟合，必须由后续独立曝光验证，采纳后仍可回滚。历史 miss 的保护边距最多为单格边长的25%，避免产生永久不可配纤状态；新活动请求的历史 miss 降权有下限。当前数值假设范围上限为 0.20 度及单格边长 35% 的较小者，这是已验证组件的范围，不是平台给出的真实偏移上限。

## 两个模型流程

- `operator_nlp`：将调度文本、请求 reason、公告与预报转成带引用和有效期的软偏好。只接受已知目标、活动请求、五种公开天体类别和有证据的方位。不会改官方截止、奖励、门槛或坐标。
- `anomaly_review`：读取累计 E/scale 历史、偏移验证、地震/天气解释及账本版本。paid report 可被模型否决；规则证据门仍决定是否允许报告。过期或旧账本答案无效。

专家 skill 位于 `skills/astronomy-observer`，两个 system prompts 实际加载该 skill。每季最多 16 个 NLP / 32 个异常逻辑调用，每调用最多两次有总时限的传输尝试，最多两个在途请求；累计主动等待目标上限 192 秒。

公开网站 v4 协议没有独立自由文本操作员字段。正式比赛可读取请求 reason；外部集成可传入内部 `operator_messages`，例如 `{ "message_id": "o1", "text": "今晚优先类星体", "expires_utc": "2026-11-02T03:00:00Z" }`。输出动作仍严格保持官方字段。

另外提供 `python3 operator_cli.py --input notes.json`，用于实际人类调度员的旁路输入。输入含 now_utc、known_target_ids、active_requests、operator_messages、forecast_tonight、bulletin_now；输出为内部偏好，不直接向网站发送动作。

## 本地使用

```sh
python3 build_native.py
OBSERVER_MODEL_DISABLED=1 python3 -u agent.py
python3 pack_agent.py --out ../observer-upload.zip
```

原示例的 `PRO_<NAME>` 搜索参数仍可调。`OBSERVER_NATIVE=0` 可做本地 Python 内核对照；`OBSERVER_GEOMETRY=0` 可做偏移消融。正式比较必须固定同一输入、评分器和预算，并记录整季是否完成。

本轮真实远程 API 未测试。模拟传输验证了两角色、skill 加载、严格 JSON 和失效门。完整分数与下降结果见研究包 VALIDATION.md，不能据此宣称普遍超过官方基线。
