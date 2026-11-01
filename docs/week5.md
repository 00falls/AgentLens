# 第五周交付记录

日期：2026-10-31。可观测链路与执行详情工作台已交付，唯一真实业务用例通过。pgvector 与 OpenShell 的既有环境缺口继续保留。

## 实现范围

- OTel SDK → 官方 Collector → 独立 OTLP 接收端 → PostgreSQL → 工作台，全部使用真实组件。
- 官方 FastAPI、HTTPX、OpenAI SDK 自动埋点；MCP SDK 原生 Span 和服务端埋点。业务运行、步骤、手册检索补充 Span。
- runs 保存 trace_id、业务 span_id、请求 request_span_id；run_steps 保存对应 span_id。原有 thread_id、checkpoint_id 和恢复来源继续保留。
- SSE 生成器在每次驱动图执行时设置观测上下文，不跨 yield 保存 OTel attachment token，避免响应预取与流式响应在不同任务中运行时发生上下文错误。
- OTLP 接收端复用官方 protobuf 定义，只处理本项目选定的 OTLP/HTTP 二进制 traces；按 trace_id + span_id 去重，增量接收，不要求一次到齐。
- 业务结果、评测、Token 账本以运行记录为准；Span 到达不决定业务是否完成。不对父子 Span 的 Token 再求和。
- GET /runs 支持项目范围、会话、状态、分页；GET /traces/{trace_id}?run_id=... 查询关联调用链。
- React / TypeScript / Vite 工作台：项目选择、运行列表、状态与会话筛选、诊断、引用跳转、步骤参数和结果、错误、耗时、Token、Span 树与时间条、属性检查。包含手机布局。

工作台使用真实 API 数据。历史无 trace_id 的运行显示未采集；未到达的 Span 显示尚未接收，不从业务步骤伪造调用链，也不把已收到根 Span 当成“所有 Span 已到齐”的证明。

## 访问范围与数据边界

OTLP 接收端单独监听 127.0.0.1:8001；不挂载到用户 API。Collector 通过独立的 ingest key 写入。只支持 application/x-protobuf，Collector 输出明确配置为不压缩；JSON、gRPC、metrics、logs 不在本项目接收范围内。

业务埋点记录关联 ID、工具名、状态与用量，不采集 Prompt 或 API Key。OpenAI 内容捕获显式关闭；接收端只保留允许的 Span / Resource 元数据，不保存请求头、URL、Prompt、异常消息或堆栈。原始 OTLP 请求体不入库。

不同项目可能复用同一个外部 traceparent，因此 trace_id 不能单独作为访问边界。查询先核对 run_id 的项目所属关系，再使用业务数据库记录的请求、业务及步骤 Span ID 限定关联子树。权限判断不依赖生产者自行填写的 project 属性。

当前 X-AgentLens-Project 仍是开发阶段的查询范围，不是身份凭证。完整身份与授权仍按第八周推进。

## 环境与依赖

| 组件 | 本次实际版本 |
|---|---|
| OTel SDK / OTLP protobuf HTTP exporter | 1.45.2 |
| FastAPI / HTTPX instrumentation | 0.66b2 |
| OpenAI instrumentation v2 | 2.4b0 |
| GenAI utility | 固定 0.4b0 |
| 官方 Collector Windows amd64 | 0.164.0 |
| React | 19.3.1 |
| TypeScript / Vite | 5.9.3 / 7.3.7 |
| pnpm | 10.28.2 |

OpenAI 埋点包的依赖范围允许解析到 GenAI utility 1.3b0，但实际导入依赖的 instruments 模块已移除。本次固定可工作的 0.4b0，并通过真实 LangChain/OpenAI 流式协议检查验证；没有编写运行时兼容兜底。Python 与前端依赖分别由 uv.lock、pnpm-lock.yaml 固定。

Collector 使用官方便携发行包，不注册系统服务。下载器校验官方 release 资产 SHA-256：

```text
ff9a3d79687cca7863bfbea1198542ca0c1800841289541913211d75ab6fea38
```

数据库的未执行向量迁移现标记为 vectors 分支，观测迁移为 platform 分支，均从 0003_sessions 分叉。本机执行 `alembic upgrade platform@head`，停留于 0005_observability；没有执行 0004_vectors。具备 pgvector 后可执行 `alembic upgrade heads`。

## 唯一真实业务验收

```powershell
uv run pytest tests/test_week5_acceptance.py -q
```

实际结果：`1 passed in 23.76s`。只运行 pool-exhaustion-01，一个回合；未重跑历史周次或全量数据集。

| 字段 | 实际值 |
|---|---|
| run_id | 880de1c6-5127-4f34-8e3b-b736d25fd0bb |
| thread_id | 4a2a0c74-bd36-4cf8-8bfa-df6a760ac637 |
| trace_id | 7895d3d943431cda04c0c77e870da6e9 |
| 模型调用 | 4 次 |
| 工具调用 | 7 次 |
| 输入 / 输出 Token | 10170 / 1306 |
| 报告快照的 Span | 42 个，来自 API 与 MCP 两个服务 |

已验证请求、业务运行、每个模型和工具步骤均可关联；调用链包含 FastAPI、官方 OpenAI、HTTPX、MCP 和检索 Span。业务诊断检查通过，已知片段的父子关系完整，跨项目读取返回 404。

两次 search_runbooks 因向量片段表尚不可用而失败，错误在业务步骤和调用链中可见。诊断仍由现场日志和指标支持。模型重复查询过遥测，原始轨迹与用量照实保留；本周没有优化或隐藏这些行为。

报告中的模型名称包含网关别名，不代表提供商精确快照。费用未计算；单条耗时不代表 P95，也不能与第四周多回合流程直接比较速度。

报告见 `reports/week5-acceptance.json` 与同名 Markdown；交付文件哈希见 `reports/week5-manifest.json`。这份 manifest 是交付清单，不替代原始运行自身记录的版本字段。

## 软件与界面检查

- 17 项 Collector / PostgreSQL / API 检查：在暂缓 SDK 导出时业务仍完成；子 Span 先到、根 Span 后到；重复去重；MCP 加入同一 trace；敏感属性过滤；跨项目复用 trace_id 隔离；分页参数和独立接收入口。外部模型决策与导出时序受控，不计为业务质量样本。
- 4 项 SDK 协议检查：真实 LangChain/OpenAI 流式栈，通过 MockTransport 返回标准 SSE；流式内容、用量、自动 Span、Prompt 与密钥 canary 均通过。没有请求模型提供商。
- 5 项已有 HTTP 生命周期回归：失败落库、失败事件、关闭生成器、HTTP 502、真实 socket 断开取消。没有新增提供商请求。
- 9 项本机无头 Edge / Playwright 检查：真实诊断、Span 树、属性展开、引用打开工具证据、会话筛选、项目切换清空详情、跨项目 404、手机无整页横向溢出、无浏览器运行时错误。只读取同一条真实验收记录。
- Python ruff / compileall、TypeScript 检查和 Vite 构建通过。

证据：`week5-contracts.json`、`week5-sdk-checks.json`、`week5-lifecycle-checks.json`、`week5-ui.json`；界面截图为 `week5-workbench-desktop.png`、`week5-workbench-trace.png`、`week5-workbench-mobile.png`，均在 reports 目录。

软件探针使用明确命名的受控运行；工作台状态统计包含匹配范围内的所有运行，不代表真实模型任务成功率。完整业务质量评分仍以所选评测用例为准。

一处可选手机按钮样式微调的重新构建遇到自动审批超时，已撤回该未验证改动，交付版本与已经通过构建、浏览器检查的版本保持一致。

## 启动方法

首次准备，已有配置文件不要覆盖：

```powershell
uv sync --frozen
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv run python scripts/download_collector.py
.\scripts\local_postgres.ps1 start
uv run alembic upgrade platform@head
uv run agentlens checkpoint-setup
uv run agentlens seed
```

本机 pnpm 在内置 Node 的 node_modules/pnpm/bin/pnpm.cjs 中，可用 `node <该绝对路径> --dir web build`；普通开发环境安装匹配的 pnpm 10.28.2 后直接使用上述命令。

分别启动以下进程，全部只监听回环地址：

```powershell
uv run python scripts/run_telemetry.py   # 8001，内部 OTLP 接收
uv run python scripts/run_collector.py   # 4318，官方 Collector
uv run python scripts/run_gateway.py     # 4000，模型网关
uv run uvicorn agentlens.mcp_server:app --host 127.0.0.1 --port 8010
uv run python scripts/run_api.py         # 8000，用户 API 与已构建工作台
```

浏览器打开 `http://127.0.0.1:8000/workbench/`。先构建 web 再启动 API，静态资源在启动时挂载。Vite 开发模式可使用 `pnpm --dir web dev`，其业务 API 请求代理到 8000。

SDK 导出目标默认 4318；Collector 脚本从同一 Settings 读取 ingest key 并传给 Collector。自定义环境变量见 .env.example；它与模型密钥相互独立。不能把用户 API 当成 OTLP 接收端。

## 当前边界与后续

尚未实现 OTel 指标与日志信号接收、通用 APM、全量生产数据 DLP、Span 到齐判定、Collector 磁盘持久队列和生产级高可用。本次没有引入这些复杂度。

业务恢复仍由 PostgreSQL Checkpoint 和显式操作负责；OTel 不承担任务恢复。pgvector、经验语义检索与 OpenShell 缺口不因本周通过而消失。

下一周完善评测集、逐例比较、Judge 校准与 CI 门禁；当前运行记录与调用链可作为定位质量问题的证据。

参考：[OTel Python](https://opentelemetry.io/docs/languages/python/instrumentation/)、[官方 OpenAI 埋点](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html)、[OTLP 规范](https://opentelemetry.io/docs/specs/otlp/)、[Collector Windows](https://opentelemetry.io/docs/collector/install/binary/windows/)。
