# 第八、九周验收摘要

日期：2026-11-01。

第八周：已接入两个项目演示身份、API / MCP 授权、已检索日志来源约束、执行审计与工作台登录。真实 PostgreSQL / API 与 MCP 的越权路径已验证。OpenShell 适配、镜像、策略和独立补验脚本已编写；本机没有 Linux / Docker / OpenShell，真实隔离未验证，M8 不计完整通过。

第九周：Prometheus / Grafana 真实启动、两个认证抓取目标、两条规则、六个面板和数据源通过。版本化计价、未知费用、提供商缓存用量、同例两模型配置对比、固定 API / MCP 性能、官方 promtool 告警触发与恢复已验证。

仅选择 pool-exhaustion-01，在同一冻结数据上各运行一次：

| 配置 | 质量 | 秒 | 估算 USD |
|---|---|---:|---:|
| Flash | 16 项规则通过 | 15.233 | 0.001335210 |
| Pro | 16 项规则通过 | 11.463 | 0.006909232 |

合计 7 次业务模型请求，输入 26474、输出 2115 Token，Judge 为零。费用按观察用量及本轮已核对的本机网关配置补算，保留原始未计价报告与补算审计；不是提供商账单核对。没有为取得更优结果重复运行；单例单次结果不作为稳定性能或一般质量结论。

36 项确定性 / 真实组件测试、7 项 MCP HTTP 检查、15 项工作台检查、6 项监控集成检查通过；实际 Grafana 页面、ruff、compileall、TypeScript / Vite 构建通过。两条告警的触发与恢复由官方 promtool 验证，未发外部通知。

远端 Actions 未执行。临时服务与 PostgreSQL 在交付时关闭，配置、便携包与数据保留。

完整记录：[第八周](../docs/week8.md)、[第九周](../docs/week9.md)。证据：[阶段验收](week89-acceptance.json)、[模型比较](week9-model-comparison.md)、[性能](week9-performance.json)、[告警](week9-alerts.json)、[监控](week9-monitoring.json)、[缺口](week8-sandbox.json)。
