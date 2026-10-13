# Pro-first observer v3.1

完整 JSONL-v4 上传项目。开场只读取 initialize 的公开配置选择一套 agent，之后保持该 agent 的状态。默认使用官方 python-pro；不根据卡名、scenario_slug、隐藏真值或未来事件路由。

增强分支触发条件：required 完成门槛不为0.5、罚分不为50，或光纤总数大于16。前两项针对pro的硬编码计分兼容差异；后一项针对pro的固定中心光纤/小邻域搜索。该规则不意味着任何“大光纤卡”都能保证提分。

标准16纤及较小布局保持官方pro。稀疏9纤的已有对照中pro更高，不能把“参数不同”一概当作增强版获胜的证据。

initialize不能识别隐藏偏移、隐藏仪器故障或未来数据丢失。正常分支保留pro原有观测反馈、偏移检测与故障报告逻辑。这个版本不在中途将两个独立agent强行互换；那需要完整转移已执行曝光、失效记录、请求进度和模型证据，否则会破坏状态。后续更精细的局部模块接管需要独立验证。

official_pro目录只对官方文件的内部import改为相对import，数值/模型策略保留。增强实现为enhanced_agent.py以及根目录planner等模块，包含C++搜索、完成度上下界、期限保护、偏移后续验证和专家skill。只初始化被选中的一套，没有双重候选搜索开销。

网站注入OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。平台设置OBSERVER_MODEL_DISABLED=1时执行规则模式。正常分支使用官方pro的LLM流程；增强分支使用operator_nlp/anomaly_review。operator_cli.py可单独提供人类调度文本适配。

manifest的build在部署主机编译C++，ZIP不含本机二进制、密钥、任务卡或真值。找不到编译器时增强分支使用Python缓存搜索。真实远程API和Linux容器构建未测试。

本地测试：8项路由/协议/动作等价测试通过；L1整季验证见外部报告。固定档位动作一致不代表实时CPU自适应运行的分数逐字一致；主机校准和负载会改变搜索档位。
