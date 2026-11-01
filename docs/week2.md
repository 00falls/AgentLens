# 第二周交付记录

日期：2026-10-31。沿用用户要求：阶段业务验收只运行一条真实用例，不批量运行全部开发集。

## 已交付

- 将日志、指标工具通过独立 MCP Streamable HTTP 服务暴露，复用第一周的查询逻辑。
- 使用 `langchain[mcp]` 的官方 MCPAdapter 发现并调用工具，固定兼容版本于 uv.lock。
- MCP 项目范围来自调用上下文的 HTTP 请求头，模型的工具参数中不包含 project_id。
- 由服务端返回结构化工具结果，Agent 直接读取 MCP artifact，不增加文本解析兜底。
- 保留工具错误消息与失败步骤；有业务错误时允许模型在步数上限内调整调用，传输失败明确终止。
- 新增 POST /agent/stream，直接使用 LangGraph custom/updates 流输出 SSE，无自建事件队列或后台任务平台。
- 保存工具定义哈希、调用参数、结构化结果、错误、用量和耗时；数据库引擎在进程内复用连接池。
- 增加评测 CLI：选定案例或显式全量运行、复核已有运行、生成 JSON/Markdown、比较基线与候选。
- 区分质量失败和执行异常；不完整实验不生成伪造的通过率。

## 唯一真实业务验收

命令：`.venv\Scripts\python.exe -m pytest tests/test_week2_acceptance.py -q`。

结果：`1 passed in 14.47s`。案例为 `pool-exhaustion-01`，运行 ID 为 `1a17ebce-1c7d-476b-8bed-c95f4070608c`。

验收经过实际 HTTP 连接，而不是仅在进程内拼接流式结果：客户端先收到 run_started，随后在任务仍运行时查询到 running 状态，最后收到 run_finished 并读取已落库结果。

本次样本首个事件约 0.470 秒到达，最后事件约 9.315 秒到达，共 454 个事件，包含 run_started、step_started、answer_delta、step_finished、run_finished。数值只描述该次本机样本，不代表 P95 或稳定性能。

Agent 执行两次模型调用和两次经 MCP 的工具调用，总输入 2380 Token、输出 688 Token。九项领域检查全部通过，步骤开始和结束事件与数据库记录逐一匹配。

验收产物：[SSE 与运行详情](../reports/week2-acceptance.json)、[CLI 评测 JSON](../reports/week2-evaluation.json)、[CLI 评测 Markdown](../reports/week2-evaluation.md)。

CLI 对这次已有运行重新评分，没有触发第二次 Agent 执行。其余九条开发用例未执行。

## 与第一周比较

通过 `eval --recorded-run` 用当前规则复核第一周已保存的运行，保持数据集、评估器和选定案例一致，再执行 compare。

结果：第一周和第二周都通过，分类为 unchanged。本次候选输入 Token 增加 48、输出增加 28；不能据此声称质量提升或成本降低。

证据：[基线复核](../reports/week2-baseline-evaluation.json)、[对比结果](../reports/week2-comparison.json)。

## 不调用模型的基础检查

六项真实 MCP/数据库检查通过：工具目录、模型参数不包含项目范围、结构化结果、非法时间窗口拒绝、项目过滤、缺少范围拒绝。

外部模型替身仅用于生命周期检查：提供商失败后落库并输出 run_failed；非流式 HTTP 返回 502；关闭执行生成器或真实 HTTP 连接后状态记录为 cancelled。五项检查通过，未将替身结果计入真实模型质量分数。

证据：[MCP 检查](../reports/week2-mcp-checks.json)、[生命周期检查](../reports/week2-lifecycle-checks.json)。静态检查和语法编译通过。

## 明确边界

API 和 MCP 都只绑定本机回环地址，尚无用户身份认证；项目请求头只表示调用方固定的查询范围，不能作为身份凭证。企业身份与资源授权留到对应里程碑。

answer_delta 是可见回答的未完成 JSON 片段，最终以 run_finished 中经过校验的对象为准。出错时流式接口以 run_failed 表达终态；非流式接口返回 502。客户端断开会取消当前执行，不自动继续运行或恢复检查点。

pgvector、OpenShell 沿用第一周已确认的环境缺口，不计为本阶段通过。未安装 Docker 或启用系统功能。完整保留集、Judge、CI 门禁与工作台仍按后续计划实施。
