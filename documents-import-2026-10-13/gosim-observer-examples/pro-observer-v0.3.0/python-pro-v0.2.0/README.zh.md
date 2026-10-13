# Pro observer v0.2.0

这是原始 `python-pro` 的独立版本，保留原始 Python/Rust/TypeScript Pro 实现。英文 [README.md](README.md) 为本版本完整使用说明；规则见 [rules-snapshot.md](rules-snapshot.md)，来源见 [PROVENANCE.md](PROVENANCE.md)。当前实现已加入回归测试，配对性能评估仍在进行，尚不宣称隐藏赛题上的性能提升。

实现沿用标准库与原有 agent/planner/advisor 结构，保持 JSONL v4 公共接口。改动涵盖实际光纤覆盖、请求完整时间区间、合法曝光时长、原始完成因子证据上下界、有限事件时长搜索、CPU 储备及结构化日志。具体开关、当前默认值与回滚方式见英文说明；最终默认值以完成评估后的版本为准。

无模型也能运行：设置 `OBSERVER_MODEL_DISABLED=1`，或未配置 API 密钥时自动使用规则。配置密钥后保留原有每夜建议与付费故障报告确认；观察后复盘是独立 CLI，不参与数值调度。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 qa_review.py run decision-log.jsonl
python3 qa_review.py step decision-log.jsonl --step 12
python3 qa_review.py replay decision-log.jsonl > reviews.jsonl
```

复盘默认离线；远程调用需显式 `--remote` 与 `PRO_REVIEW_BASE_URL/MODEL/API_KEY`。复盘只能解释、诊断和提出实验，不修改分数、状态、几何或截止时间。未知真实质量与必做目标状态不会伪造。

900预算单位为标准化 CPU 秒。CPU/速度系数、真实经过时间、模拟观察时间及模型等待时间分别记录。本地 Rosetta 计时存在已复现的41.67倍低估；基准使用原生 arm64 解释器与校准环境，官方判分器源码保持不变。平台 Python3.12 容器尚未实测；本地分数不等于隐藏官方结果。原始版本和分阶段消融均可用于回滚。请勿提交密钥或 `.env`；上传与远程评测需另行授权。
