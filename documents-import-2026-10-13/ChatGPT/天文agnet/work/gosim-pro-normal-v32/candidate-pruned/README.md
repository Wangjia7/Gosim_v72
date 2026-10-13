# Pro normal optimizer v3.2

接口完整的 JSONL-v4 上传项目，入口 agent.py，根目录 observer.project.json。网站在部署主机编译 C++，无编译器时使用缓存 Python 搜索。ZIP 不含平台二进制、任务卡、真值或密钥。

默认 16 纤及较小布局使用优化后的 Python pro。内部包名 official_pro 为兼容导入保留，代码已修改。非默认 required 门槛、罚分或大于 16 根光纤走 v3.0 增强路径。只按公开 initialize 选择，不根据卡名或隐藏故障路由，中途不互换独立 agent。

正常路径新增缓存、共同 program 搜索、请求截止保护、批量奖励封顶、运行时 required 配置、保守完成度账本、失效曝光回放、完整视场搜索、曝光断点、实际档位 CPU 计时和每轮算力限制。Moon 与 LST 使用一致时刻。科学分数取最佳一次曝光，raw completion 独立取最大值。

结构化天气、时间窗与数值调度由规则控制。模型运行 operator_nlp / anomaly_review 两个低频流程，读取专家 skill。建议须引用已有来源、目标和请求，带有效期；异常诊断带账本版本，数值规则决定报告。官方接口无原生人类聊天字段，operator_cli.py 提供旁路适配。

网站可注入 OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL。OBSERVER_MODEL_DISABLED=1 或无密钥时继续规则模式。只接受完整 JSON 或一个 JSON fence，丢弃错误回复，重试共用总超时。真实远程 API 未测试。

PRO_ 实验开关：JOINT_PROGRAM、FULL_FIELD、BREAKPOINTS、REQUEST_BATCH、CONSERVATIVE_REQUIRED、WINDOW_URGENCY。WINDOW_URGENCY 默认关闭，其他默认开启。这一阶段包采用全组合，部分本地卡有回归，不能宣称普遍超过 pro。最终推荐包另附对照报告。

最近 16 个重复 decision_sequence 回送原回复，曝光按 observe_index 去重。stdout 仅 JSONL，日志写 stderr。已验证主机 manifest/build/run、正常与增强路由、Python fallback、规则模式和本地模拟模型。Linux 容器与网站成绩仍需实测。
