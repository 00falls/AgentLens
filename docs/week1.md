# 第一周交付记录

日期：2026-10-31。当前阶段为个人开发环境中的第一周最小实现。

## 已交付

- Python 3.12.14 项目虚拟环境、pyproject.toml、uv.lock 和静态检查配置。
- LiteLLM 1.106.6 网关，接入用户配置的 DeepSeek；上游配置为 `openai/deepseek-flash`。
- LangGraph 1.2.19 自定义决策—工具—观察循环，模型调用上限与请求超时。
- FastAPI 的调用入口和执行详情查询。
- PostgreSQL 17.11 便携开发数据库、Alembic 初始迁移、种子数据导入。
- 两个按项目、服务、时间真实查询的只读工具；标准答案未提供给工具和模型。
- 两个项目、三个服务、五类故障、正常和数据不足场景，合计 12 条日志、17 个指标点、10 条开发用例。
- 结构化答案、真实证据 ID 校验，以及模型/工具参数、结果、耗时和 Token 记录。
- MCP SDK 2.3.0 的 Streamable HTTP 服务发现与工具调用探针。
- 单条真实业务验收与可阅读的 JSON 报告。

## 唯一业务验收

命令：`.venv\Scripts\python.exe -m pytest tests/test_week1_acceptance.py -q`。

结果：`1 passed in 29.74s`。没有运行其余九条开发用例，没有使用固定答案模型替代真实模型。

案例：`pool-exhaustion-01`。运行 ID：`057292e4-d583-421d-9357-b04d5dce1dfb`。

链路：FastAPI 路由 → LangGraph → LiteLLM → DeepSeek → search_logs / query_metrics → PostgreSQL → 最终诊断。

模型做了两次流式调用，执行了两次工具查询。总输入 2332 Token、输出 660 Token。模型调用耗时约 22.38 秒与 3.49 秒；单次样本不能代表 P95 或生产性能。

诊断识别出连接池 active=20 已达到 max=20、waiters=48，结合连接获取超时日志与 5xx 比例判断连接池耗尽，并明确指出慢 SQL、长事务和连接泄漏仍需进一步调查。

八项检查通过：输出状态、必要工具、查询范围、根因关键词、必要证据、引用有效性、窗口外数据排除、Token 用量记录。

原始验收产物在 `reports/local/week1.json`；便于查看的副本在 `reports/week1-acceptance.json`。副本只规范了模型标识字段名称并补充网关配置核实结果，保留相同运行、分数和原始模型输出，没有重新执行案例。

LiteLLM 返回的 response model 是网关别名 `agentlens-agent`，不能把它当作提供商实际版本。上游配置通过本机 `/model/info` 核实为 `openai/deepseek-flash`；不声称已观测到提供商背后的精确模型快照。后续运行记录区分请求别名、上游配置与响应中的模型名称。

## 基础验证与环境缺口

| 项目 | 结果 | 证据或限制 |
|---|---|---|
| Python 与锁定依赖 | 通过 | 项目 .venv 和 uv.lock |
| PostgreSQL | 通过 | 真实服务、迁移、导入及验收查询 |
| 模型工具调用与流式传输 | 通过 | 单条案例内的两次真实模型调用 |
| MCP Streamable HTTP | 通过 | 发现 echo_service 并远程调用成功，报告见 reports/mcp-probe.json |
| pgvector | 未验证 | 当前便携 PostgreSQL 没有 vector 扩展 |
| Docker | 未发现 | 当前 PATH 中不存在 Docker CLI |
| WSL | 未确认可用 | wsl --list --quiet 返回非零退出码 |
| OpenShell | 未验证 | 未安装 CLI，也没有已提供的 Linux 容器环境 |
| 静态检查与语法编译 | 通过 | ruff check 与 compileall |

环境报告：`reports/environment.json`，只记录是否配置密钥，不包含密钥值。

用户已确认：“没有，先记录环境缺口。”因此本次保留 OpenShell、pgvector 的后续补验项，不将它们计为通过。

## 当前实现边界

业务工具当前直接调用 Python 逻辑，MCP 仅完成独立协议可行性验证；业务工具 MCP 化与 SSE 事件在第二周实施。

API 只绑定本机回环地址，尚未实现身份认证。项目过滤是查询范围，不是用户授权系统。知识向量检索、Checkpoint、长期经验、OTel、沙盒业务集成、工作台和完整 CI 门禁仍属于后续任务。

当前不计算费用，不从 Token 总量或本地价格表伪造账单。模型输出格式错误、无效引用和运行失败直接保留错误，不使用万能降级答案。

PostgreSQL 在本机中文路径下出现 UTF-8 初始化错误，已通过映射当前项目到 `L:` 解决。没有安装数据库系统服务，也没有启用 Windows 系统功能或安装 Docker。

## 下一步

第二周沿用现有工具业务逻辑实现 MCP 服务接入，再增加 SSE 和首批评测 CLI。回归验收继续按用户当时确认的案例范围执行。Linux/容器环境可用后补测 pgvector 和 OpenShell。
