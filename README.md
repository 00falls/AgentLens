# AgentLens

面向运维排障 Agent 的执行追踪、评测与回放项目。已验收的主链路：

`FastAPI / CLI → LangGraph → LiteLLM / DeepSeek → MCP HTTP 工具服务 → PostgreSQL`

日志、指标、手册与标准答案均为明确标注的合成演示数据。业务工具查询遥测与知识表；评测标准答案不进入模型上下文。

最新真实评测：固定 **10 条开发集子集**覆盖 8 个故障家族，Flash 本地 **9/10（90%）**；远端正常 **8/10** → 受控退步 **0/10** → 恢复 **9/10**。恢复轮门禁通过，原定“绿→红→绿”未达成；真实失败完整保留，其余 50 条未运行。见 [评测与复现说明](docs/ci-evaluation.md) 和 [各轮证据汇总](reports/ci/campaign.md)。

## 已实现范围

- 两个演示项目、三个服务；开发集覆盖 8 个场景家族，包含正常与证据不足场景。
- 日志、指标、手册与经验四个只读工具实际查询 PostgreSQL；另有只使用已授权日志的 OpenShell 分析工具，隔离环境仍待补验。
- 模型自行选择工具、循环观察，最后输出结构化诊断与实际证据 ID。
- 模型调用与 HTTP SSE 过程事件均使用流式传输。
- 保存每次模型和工具调用的参数、结果、用量、耗时与错误。
- 保留早期 10 条开发用例；第六周新增 40 条开发集、20 条保留集，按故障家族分组。此前阶段只运行一条 `pool-exhaustion-01`；本轮固定选取 10 条开发案例真实评测，保留集未参与选例或调试。
- 独立 MCP Streamable HTTP 业务服务，官方 LangChain MCPAdapter 发现与调用工具。
- 评测 CLI 支持显式选择用例、复核已有运行、输出 JSON/Markdown、比较两次实验。
- 第三周已完成 18 份手册、36 个片段、本地中文 embedding、pgvector 与 MCP 检索工具。环境补齐后发现的泛化查询问题已在第六周修复，同一业务用例通过；历史失败保留于 [pgvector 补验](docs/pgvector-windows.md)。
- 第四周已验收 PostgreSQL Checkpoint、多轮追问、进程重启后的显式恢复、确认后归档经验与跨会话按服务查询，见 [第四周交付记录](docs/week4.md)。
- 第五周已验收 OTel → 官方 Collector → 独立 OTLP 接收端 → PostgreSQL，以及 React 执行详情工作台，见 [第五周交付记录](docs/week5.md)。
- 第六周已交付 AgentEvals 轨迹与参数匹配、独立质量维度、LLM Judge、AI 参考标签一致性报告、逐例工作台与 CI 门禁。该阶段只完成单例与本地门禁，见 [第六周交付记录](docs/week6.md)；本轮已运行远端 10 例门禁，Judge 未参与，也未经独立人工校准。
- 第七周已交付工具结果录制、严格重跑、真实 PostgreSQL / pgvector 冻结场景、执行差异与失败步骤定位。相同故障案例分别验证录制边界停止和冻结场景 16 项规则通过，见 [第七周交付记录](docs/week7.md)。
- 第八周已接入两个项目身份、API / MCP 授权、分析输入来源约束、执行审计和工作台登录；OpenShell 分析适配与策略已编写，真实 Linux 隔离仍待补验，见 [第八周](docs/week8.md)。
- 第九周已交付 Prometheus 账本指标、Grafana 面板、版本化费用、缓存用量、两模型配置的同例比较、告警触发/恢复与性能实测，见 [第九周](docs/week9.md)。

## 环境与安装

需要 Python 3.12、uv、PostgreSQL。完整路线见 [执行计划](执行计划.md)。

```powershell
uv sync --frozen
Copy-Item .env.example .env
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv run python scripts/download_collector.py
```

在 `.env` 中配置 `DEEPSEEK_API_KEY`。默认通过 OpenAI 兼容接口连接 DeepSeek，并关闭 thinking；网关模型名为 `agentlens-agent`。`DEEPSEEK_MODEL` 包含 LiteLLM 提供商前缀，例如 `openai/deepseek-flash`。密钥不得提交。

本机 uv 位于 `.venv\Scripts\uv.exe`，以下 `uv run` 可替换为 `.\.venv\Scripts\uv.exe run`。

## 本机 PostgreSQL

可连接已有 PostgreSQL，设置 `.env` 的 `AGENTLENS_DATABASE_URL`。本机也已准备 EDB 的 PostgreSQL 17.11 便携发行包，将其 bin/lib/share 放在 `.tools/pgsql`，不注册 Windows 服务。

```powershell
.\scripts\local_postgres.ps1 start
uv run python scripts/create_local_database.py
uv run alembic upgrade heads
uv run agentlens checkpoint-setup
uv run agentlens seed
uv run agentlens knowledge-import
uv run python scripts/init_identities.py
```

便携脚本只绑定 127.0.0.1，使用明确的本地开发凭证。数据在被 Git 忽略的 `data/postgres`；不要用于生产。停止命令：`.\scripts\local_postgres.ps1 stop`。

平台与向量迁移目前为两个分支。本机已为原有便携 PostgreSQL 17.11 编译安装 pgvector 0.8.7，并应用两个分支、导入知识向量。新环境应先安装服务端扩展，再执行 `alembic upgrade heads` 与 `agentlens knowledge-import`；暂时没有扩展的环境可仅执行 `upgrade platform@head`，此时手册检索不可用。Windows 配置与实际结果见 [补验记录](docs/pgvector-windows.md)。

当前 Windows 上 PostgreSQL 无法在中文安装路径完成初始化，因此脚本使用 `subst` 将当前项目映射到 `L:`。文件仍在原项目目录。若盘符已占用，可用 `-Drive R` 指定空闲盘符；同一数据目录须保持相同盘符。停止数据库后可执行 `subst L: /d` 移除映射。

## 启动模型网关、MCP 与 API

数据库完成迁移和导入、工作台完成构建后，先启动观测接收链路，再启动业务服务：

```powershell
uv run python scripts/run_telemetry.py
```

```powershell
uv run python scripts/run_collector.py
```

```powershell
uv run python scripts/run_gateway.py
```

```powershell
uv run uvicorn agentlens.mcp_server:app --host 127.0.0.1 --port 8010
```

```powershell
uv run python scripts/run_api.py
```

`AGENTLENS_MCP_URL` 默认 `http://127.0.0.1:8010/mcp`，可在 `.env` 配置。

工作台位于 `http://127.0.0.1:8000/workbench/`。先使用 `.tools/identities.json` 中对应项目的 Key 登录，再查看诊断、工具参数与结果、引用、错误与 Span 树，以及用量与审计。Key 仅存页面内存，退出或刷新后重新登录。`GET /runs` 支持会话、状态和分页；调用链查询为 `GET /traces/{trace_id}?run_id=...`。

SDK 的 OTLP 目标为 4318，Collector 转发到独立的 8001 接收端。Span 异步到达，业务完成不等待观测数据；接收端按 trace_id + span_id 去重。Token 以业务运行账本为准，不能把父子 Span 用量重复累加。

`POST /agent/invoke` 接收 `project_id` 和 `prompt`，返回最终 JSON；`POST /agent/stream` 使用相同请求体返回 SSE；`GET /runs/{run_id}` 返回执行详情。OpenAPI 在本机 `/docs`。

会话接口为 `POST /threads`、`GET /threads/{id}`、`POST /threads/{id}/runs` 和 `POST /threads/{id}/resume`。这些接口、运行读取和经验查询都按已认证身份的项目范围访问；可选的 `X-AgentLens-Project` 必须与身份一致。新回合可附带 experience 申请保存，暂停后由客户端显式确认或拒绝；请求体示例见 [第四周](docs/week4.md)，当前调用还须提供 Bearer Key。API 启动脚本为 Windows 异步 PostgreSQL 选择 Selector 事件循环。

API 和 MCP 现在都要求 `Authorization: Bearer API_KEY`，身份绑定单个项目；省略项目头时使用身份项目，显式传入不一致项目则返回 403。旧 invoke / stream 的请求体项目同样不能越权。模型参数不包含项目或凭证；CLI 使用本机受保护的项目 Key 访问 MCP。只有健康检查与静态页面可匿名访问。当前为演示 API Key 接入，尚未实现企业 SSO、密钥轮换或独立数据库角色，启动地址保持本机回环。详见 [身份与审计](docs/week8.md)。

## SSE 事件契约

正常顺序：`run_started → step_started / answer_delta / step_finished → run_finished`。

申请归档经验且诊断成立时，终止事件为 `run_interrupted`，返回检查点与待确认对象；通过 resume 接口恢复后产生新的关联运行。进程重启后的显式恢复已验证，不自动恢复或重放 SSE 事件。

每个事件包含 `event`、`run_id`；步骤事件包含 `step`、`kind`、`name`；`answer_delta.delta` 是可见回答的原始 JSON 文本片段，尚未完成最终校验。`run_finished` 的 `diagnosis` 是已经校验并落库的最终对象。

运行出错时发送 `run_failed` 并保留数据库中的失败原因；流式响应已开启时 HTTP 状态仍为 200，客户端须检查最终事件。非流式接口在对应失败时返回 502 及 run_id。

客户端断开会关闭执行流并记录 `cancelled`，不自动在后台继续执行。重新连接可查询运行记录，并按最新检查点显式恢复；当前不支持事件重放或服务故障后的自动任务接管。

## 只运行一条验收用例

上述服务启动后执行第八、九周验收。新数据库还需先导入已保存的历史参考；该步骤不调用模型：

```powershell
uv run python scripts/prepare_week7_reference.py
uv run pytest tests/test_week89_components.py -q
uv run python scripts/check_week8_mcp.py
uv run pytest tests/test_week89_acceptance.py -q
```

组件与 MCP 检查不调用提供商。真实验收只选择一条 `pool-exhaustion-01`，在同一冻结数据上分别使用 Flash、Pro 两个网关配置，共两次模型执行，不调用 Judge。报告写入 `reports/week89-acceptance.json`。本轮两种配置均通过 16 项规则；OpenShell 的独立隔离探针仍因缺少 Linux 运行时未通过完整验收。

前七周测试保留作历史入口；早期无身份的 HTTP 探针不再适用于当前接口，使用本节检查。不要执行整个 tests 目录来进行阶段验收，避免重复付费运行同一案例。

工作台“重跑与差异”支持创建录制和冻结副本、显式选择执行方式、比较完整工具参数与答案，以及跳转失败步骤。历史比较不调用模型；录制重跑不会自动改用现场工具。CLI 的 `record`、`freeze-scenario`、`replay`、`scenario-eval`、`run-diff` 用法和退出码见 [第七周](docs/week7.md)。

## 离线评测与对比

发起一次新的真实模型评测：

```powershell
uv run agentlens eval --dataset datasets/week6/dev.jsonl --case pool-exhaustion-01 --judge --name baseline --report reports/experiments/baseline.json
```

复核已有运行，不调用业务模型；省略 `--judge` 时也不调用评分模型：

```powershell
uv run agentlens eval --dataset datasets/week6/dev.jsonl --case pool-exhaustion-01 --recorded-run RUN_ID --name candidate --report reports/experiments/candidate.json
```

对比使用相同数据集、评估器和案例选择的两个报告：

```powershell
uv run agentlens compare --baseline reports/experiments/baseline.json --candidate reports/experiments/candidate.json --report reports/local/comparison.json
```

`--case` 可以重复指定；全量评测须显式传入 `--all`。本次只运行一个业务案例，没有执行其余 59 条。JSON 旁生成同名 Markdown 报告；失败列给出未通过的检查名。旧默认开发集为 `datasets/dev.jsonl`，第六周显式指定上述数据集路径。

工作台的“评测对比”读取 `reports/experiments` 中的实验，支持失败过滤、规则差异、Judge 理由和打开原始运行。该目录只放实验报告。门禁用法、AI 标签来源和 Actions 配置见 [第六周](docs/week6.md)。

评测退出码：0=所选用例全部通过，1=质量检查失败，2=执行异常或输入错误。执行异常单列 errors，实验不完整时 pass_rate 为 null，不冒充零分或通过。复核运行须与案例输入、项目一致。

## 基础探针与检查

当前组件与性能探针不运行其他故障案例：

```powershell
uv run python scripts/environment_probe.py
uv run pytest tests/test_week89_components.py -q
uv run python scripts/check_week8_mcp.py
uv run python scripts/benchmark_week9.py
```

MCP 检查使用真实 HTTP 和数据库，不产生提供商调用。早期独立协议探针有自己的示例服务，可单独运行：

```powershell
uv run python scripts/mcp_probe.py --serve
# 另开终端
uv run python scripts/mcp_probe.py
```

静态检查：`uv run ruff check src scripts migrations tests`。

遥测数据由 `scripts/generate_fixtures.py` 生成；手册由 `datasets/runbooks/catalog.json` 与 `scripts/generate_runbooks.py` 生成。修改生成源后再生成与导入，不要只改生成文件。第六周开发集与保留集按故障家族划分，见 `datasets/week6/manifest.json`。

## 指标、费用与告警

API 启动后，`/metrics` 使用项目 Key 抓取业务账本指标；工作台“用量与审计”展示 Token、已知费用部分、未知调用数和执行事件。当前费用快照只覆盖核对过的日期，历史或无完整依据的费用保持未知。

```powershell
uv run python scripts/download_monitoring.py
uv run python scripts/generate_dashboard.py
uv run python scripts/run_monitoring.py
```

Prometheus 在 `127.0.0.1:9090`，Grafana 在 `127.0.0.1:3000`。Grafana 为本机运维视角，随机管理员密码位于 `.tools/monitoring/grafana-admin.txt`；详细计量口径、告警测试和实测条件见 [第九周](docs/week9.md)。

## 当前边界

知识向量检索、Checkpoint、确认经验、OTel traces 与工作台已验收。严格录制只支持单个初始用户回合；冻结数据与审计不提供管理员级防篡改。项目 Key 已接入，但企业 SSO、数据库角色分权与密钥轮换未实现。Actions 工作流尚未远端运行，Judge 仍是辅助评分。OpenShell 真实隔离缺口保留。经验检索按服务结构化查询，尚未建立经验向量索引。模型性能只比较同一合成案例的单次观测，不能外推生产容量；费用超出已核对的日期窗口保持未知。

代码复用 LangGraph 的状态图机制、LiteLLM 的网关能力和 MCP 官方 SDK；本项目的排障流程、数据、执行记录和评测条件独立实现。

交付证据见 [第一周](docs/week1.md)、[第二周](docs/week2.md)、[第三周](docs/week3.md)、[第四周](docs/week4.md)、[第五周](docs/week5.md)、[第六周](docs/week6.md)、[第七周](docs/week7.md)、[第八周](docs/week8.md) 和 [第九周](docs/week9.md)。

参考：[LangGraph](https://github.com/langchain-ai/langgraph)、[LiteLLM](https://github.com/BerriAI/litellm)、[MCP SDK](https://github.com/modelcontextprotocol/python-sdk)、[DeepSeek 接口](https://api-docs.deepseek.com/)、[PostgreSQL Windows 发行入口](https://www.postgresql.org/download/windows/)。
