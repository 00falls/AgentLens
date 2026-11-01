# 第五周单条真实验收

日期：2026-10-31。结果：`1 passed in 23.76s`。

仅运行 `tests/test_week5_acceptance.py` 中的 pool-exhaustion-01，一次业务回合。使用真实模型网关、MCP、PostgreSQL、OTel SDK 与官方 Collector；界面检查复用同一条运行，没有额外调用模型。

| 字段 | 值 |
|---|---|
| run_id | 880de1c6-5127-4f34-8e3b-b736d25fd0bb |
| thread_id | 4a2a0c74-bd36-4cf8-8bfa-df6a760ac637 |
| trace_id | 7895d3d943431cda04c0c77e870da6e9 |
| 输入 / 输出 Token | 10170 / 1306 |
| 模型 / 工具步骤 | 4 / 7 |
| 调用链快照 | 42 个 Span，来自 API 与 MCP 服务 |
| 业务诊断检查 | 9 项通过 |
| pgvector 验证 | 未完成，保留既有环境缺口 |

请求、业务运行、模型和工具步骤可关联；调用链包含 FastAPI、OpenAI SDK、HTTPX、MCP、业务步骤和手册检索 Span。验收还检查已收到 Span 的父子关系、会话筛选、跨项目查询返回 404，以及已构建工作台可访问。

两次 search_runbooks 因向量片段表不可用失败，原始错误保留在步骤和 Trace 中。最终诊断由现场日志和指标支持；本次通过不代表向量检索通过。Token 使用运行账本，不累加父子 Span。单条耗时不代表吞吐、P95 或性能提升。

原始事件、诊断、版本字段、逐项检查和 Trace 快照见 [week5-acceptance.json](week5-acceptance.json)。交付记录见 [../docs/week5.md](../docs/week5.md)。
