# v3.2 对照数据与计时合同

评分器和 workflow：复用 `work/gosim-desi-v300/runner/challenge` 官方文件；正式候选运行不得读取任务卡或真值，只接收 initialize、snapshot 和自身观测结果。离线 evaluator 可读取冻结任务卡。

训练/开发参考：既有 L1/L2、500 目标正常样例；新增正常验证 normal-a/normal-b 的 catalogue seed 为 2026100617/2026100618，weather seed=seed+100000，request seed=seed+900000。默认 16 纤、0.4 平方度、默认 scoring；无隐藏故障、地震或数据丢失，保留正常天气和限时请求。

每次运行的 `source-input-manifest.json` 保存代码与 config/public/truth 产品 SHA256。不同修订或输入不能只按 family 标签合并；首次 pruned L1 的 agent_error 保留，修复后单独运行 r2。

主指标：官方整季 total points，同时报告 required_missing、requests completed/issued、结束原因和实际 CPU。未完整结束的负分属于失败诊断，不作为完整季节提分证据。新正常卡虽在代码候选完成后生成，但不是预登记的大型盲测；不据此声称普遍优势。

本机 macOS 官方 subprocess CPU reader 实测：time.process_time 增长约 0.200 秒时，reader 只增长约 0.0048 秒。保留初步 transport 对照，不用于同 CPU 预算的成绩比较。

`run_cpu.py` 使用不修改的官方 workflow、calibration workload 和 scorer，向离线 agent 提供公开消息，在相同进程内以 time.process_time 作为 CPU hook。这是本地可信计时方法，模型关闭，按相同 180 标准 CPU 秒与 360 秒实时时限比较；不是部署后的 cgroup 计量验证。比赛网站仍由其 CPU/cgroup 计量；ZIP 的 manifest/build/JSONL transport 另行验证。
