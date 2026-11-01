# 第七周交付记录

日期：2026-11-01。受控录制重跑、冻结场景、执行差异和失败证据定位已交付。只选择 pool-exhaustion-01：一次真实模型录制重跑按预期停止，一次真实模型冻结场景评测通过；没有执行其他故障案例或 Judge。

## 三种操作

| 操作 | 模型调用 | 工具数据 | 新路径 |
|---|---|---|---|
| 历史查看 / run-diff | 无 | 已存运行与步骤 | 不执行 |
| recorded_replay | 有 | 录制中的结果或错误 | 未录制的参数或调用立即停止 |
| frozen_scenario | 有 | 项目范围的 PostgreSQL 冻结副本 | 可执行新查询 |

两种新执行均建立新会话和新运行，关联 source_run_id。重跑使用原始用户输入、当前业务 Prompt 和选定模型；它不自动恢复旧系统 Prompt，也不声称确定性复现。模型别名可通过请求 model 或 CLI --model 指定，必须在模型网关已配置；不同别名的上游映射未核实时记录为未知。本次真实模型验收使用现有 DeepSeek 别名，没有宣称已实测第二个提供商。

## 录制与匹配

- recordings 表保存来源运行、工具目录、参数、结果或错误、原始步骤序号、案例契约和内容哈希。读取时核对内容哈希；没有编辑录制的 API。
- 新现场运行保存完整工具目录。早期运行只存目录哈希，因此导出时可以读取当前 MCP 目录元数据，只有哈希与来源一致才接受。导出不执行业务工具；录制重跑本身完全不连接 MCP。
- 参数在边界按现有 Pydantic 工具契约校验，补齐默认值，时间统一为 UTC；未知参数不被静默丢弃。普通查询字符串保持原样，不把不同语义查询强行视作相同。
- 工具串行执行，按“工具名 + 规范化参数 + 相同键的第几次调用”取结果。重复调用分别消费录制中的不同结果；不同键可以改变相对次序。
- 原工具错误仍以 ToolMessage error 返回，结果使用独立副本，不修改录制。新参数、未知工具或重复次数超出录制均记录 replay_mismatch，保存请求参数、出现次数、录制候选参数和来源步骤；禁止自动访问现场工具或补造结果。
- replay RunStep 保存 source_step_sequence。隔离执行的会话不能作为现场会话继续或恢复；重跑尝试也不能再作为新的现场观察录制。首版只接受单个初始用户回合，不支持导出多轮或确认恢复流程来重放副作用。

## 冻结 PostgreSQL 与向量数据

冻结过程在一个 REPEATABLE READ 事务中，将选定项目的 log_events、metric_points、knowledge_documents、knowledge_chunks 复制到独立 schema。复制的向量仍是真实 pgvector 类型，没有替换成内存检索或录制查询结果。

manifest 保存表行数、内容哈希、固定 embedding 文件清单哈希与案例契约。执行前核对副本完整性和查询 embedding 配置。MCP 由调用方通过内部 x-agentlens-scenario 头选择已授权项目的副本，模型参数不包含 schema 或项目范围；不存在或跨项目的场景直接报错，不回落到 public 表。

副本没有应用编辑入口，四个工具继续只读；这不是数据库管理员级的防篡改系统。检查后被特权管理员并发修改的防护、独立数据库角色和完整身份认证仍不属于本周范围。当前项目头仍是开发查询范围，正式权限按第八周处理。

早期 dataset_sha256 字段保留旧演示文件的标识。隔离执行的实际数据边界以 recording_sha256 或 scenario_manifest.sha256 为准，不把旧文件哈希当作数据库完整快照证明。

## 实际验收

来源为先前真实质量失败记录：`302c48a7-9420-4b60-9ee6-477f6da3e6f0`。它已查询日志与指标，但手册查询仅为“order-api 服务异常 错误日志 排查”，未命中和引用标注相关片段。

```powershell
uv run pytest tests/test_week7_acceptance.py -q
```

结果：`1 passed in 21.11s`。一个 pytest 场景中包含同一业务案例的两种模型执行，并非只新增一个 Run。

| 字段 | 录制重跑 | 冻结场景评测 |
|---|---|---|
| run_id | 7e675c9c-22d1-4707-9e44-1790eb168488 | 7d81edc0-496d-42ee-a739-77c0d98f2bd1 |
| 状态 | replay_mismatch，预期边界停止 | diagnosed，16 项质量规则通过 |
| 模型调用 | 2 | 3 |
| 输入 / 输出 Token | 3597 / 387 | 9001 / 1102 |
| 工具来源 | 仅录制，无 MCP 连接 | 冻结 PostgreSQL 与向量副本 |

实际录制 ID 为 `4b4ee796-3108-48b5-a2fb-a80a0c80627d`，冻结场景 ID 为 `90691dfa-f09b-4850-9cc1-9c6c5e576718`。

重跑成功复用了来源步骤 2 的日志与步骤 3 的指标。新模型随后用 HikariPool 原始错误、active/idle/max 和 db_pool_waiters 组成新手册查询，在候选步骤 5 触发 unrecorded_arguments；报告同时展示来源步骤 4 的旧查询。验收特意将重跑的 MCP 地址设为不可连接，未发生现场查询或自动回退。

相同的新查询路径随后在冻结场景中完成，通过相关手册召回与引用规则。保留来源失败事实，不把 mismatch 当作成功诊断，也不通过修改录制来容纳新查询。

总业务模型用量为输入 12598、输出 1489 Token，共 5 次模型调用，Judge 请求为 0。两个受控软件组件探针另存运行记录，提供商调用均为 0，不计作新的真实业务质量样本。见 `reports/week7-usage.json`。

## 差异与事实定位

JSON / Markdown 报告展示工具选择、完整原始及规范化参数、重复次数和次序、来源步骤链接、引用增加与移除、最终答案、Token 与耗时。未完成执行的答案为空；较少的 Token 或耗时不代表性能改善，尤其不能把提前停止与完成诊断比较效率。

规则仅标注可核对事实：工具执行错误、标注相关片段未召回或未引用、无效引用、重跑不匹配、模型调用上限。每项附 run_id、步骤序号或答案字段位置。不把“片段未召回”直接归因于向量模型，也不推断不可见的模型内部思考。

实际报告：

- `reports/week7-acceptance.json`：真实阶段验收。
- `reports/week7-replay-difference.json` / `.md`：严格录制停止与来源差异。
- `reports/week7-frozen-difference.json` / `.md`：冻结场景修复前后差异。
- `reports/week7-cli-difference.json` / `.md`：只读 CLI 导出复核，没有新增执行。
- `reports/week7-components.json`、`week7-ui.json`、`week7-usage.json`：组件、界面和用量证据。

## 工作台与接口

新增“重跑与差异”页面：三种执行方式、来源录制与冻结场景选择、候选模型别名、创建录制与快照、查看候选运行、两侧参数与答案、失败事实和步骤跳转。执行按钮明确会调用模型，没有隐式重跑。当前工作台的冻结按钮针对已验证的 pool-exhaustion-01；API / CLI 可以显式选其他开发案例，但本轮没有执行它们。

录制或冻结之后会自动选中新资源。切换项目清空旧对比；API 读取和执行前均核对项目范围。历史读取和界面检查不会创建业务 Run。

| 接口 | 作用 |
|---|---|
| POST /runs/{id}/recordings | 导出已完成来源的工具观察 |
| GET /recordings、/recordings/{id} | 当前项目的录制与内容 |
| POST /recordings/{id}/replay | 调用模型，严格录制重跑；mismatch 返回 409 和 run_id |
| POST /scenarios | 从开发案例复制当前项目数据 |
| GET /scenarios、/scenarios/{id} | 当前项目的冻结场景 |
| POST /scenarios/{id}/evaluate | 调用模型，在冻结数据上允许新路径 |
| GET /run-comparison | 只读比较相同输入、相同项目的两个运行 |

## 软件检查和 CI

- 27 项确定性契约通过：第七周 12 项与第六周 15 项。覆盖默认值与时区规范化、重复次数、未知参数、未知工具、录制错误保留、差异字段、失败定位及既有评估器。
- 4 项真实组件测试通过：PostgreSQL 向量副本、修改现场数据不影响副本、篡改副本被拒绝、项目范围、不存在场景不回落、录制哈希、真实 LangGraph 在禁用 MCP 的情况下消费录制、来源步骤链接、隔离恢复与再录制边界。仅替换外部模型决策，探针输出明确命名 Controlled，不能计为真实质量通过。
- 15 项 Edge / Playwright 界面检查通过：三种模式提示、参数和答案、创建后选择、原始失败步骤和 mismatch 步骤跳转、跨项目读取 404、切换项目清空、手机无整页横向溢出、无浏览器异常、没有新增业务执行。
- ruff、compileall、TypeScript、Vite 构建通过。

Actions 工作流已加入第七周契约和组件/真实验收入口；付费部分依然必须手动 run_real=true。新 CI 数据库通过 `scripts/prepare_week7_reference.py` 导入仓库中冻结的历史参考，不伪造新的模型执行，也不覆盖已有来源。本次只检查工作流 YAML，没有推送仓库或执行远端 Actions。

## 本机复现

```powershell
.\scripts\local_postgres.ps1 start
uv run alembic upgrade heads
# 按第五周说明启动网关、MCP、API、Collector 与接收端。

# 无模型调用；早期缺少目录正文的来源，需要可用 MCP 来核对目录元数据。
uv run agentlens record --run 302c48a7-9420-4b60-9ee6-477f6da3e6f0 --project project-a

# 会调用模型。严格重跑不能容纳新的查询；本来源预期退出码 3。
uv run agentlens replay --id RECORDING_ID --project project-a --report reports/local/replay.json

uv run agentlens freeze-scenario --case pool-exhaustion-01 --source-run 302c48a7-9420-4b60-9ee6-477f6da3e6f0 --project project-a
uv run agentlens scenario-eval --id SCENARIO_ID --project project-a --report reports/local/frozen.json

# 只读取历史，不调用模型或工具。
uv run agentlens run-diff --baseline SOURCE_RUN_ID --candidate CANDIDATE_RUN_ID --project project-a --report reports/local/difference.json
```

CLI replay / scenario-eval 退出码：0=完成且关联规则通过（没有标签时只代表执行完成）；1=关联质量规则失败；2=执行异常；3=replay_mismatch。不会把 mismatch 自动改成冻结场景评测。

正式验收前先运行 `tests/test_week7_components.py`，它生成组件录制与冻结场景的前置 ID；再单独运行 `tests/test_week7_acceptance.py`。不要直接执行整个 tests 目录，以免重跑历史付费用例。临时服务与数据库在验证后关闭。

当前未实现多轮检查点录制、写操作/人工确认的副作用重放、通用分布式重放调度、快照自动清理或完整权限体系。OpenShell 缺口保留。交付文件哈希见 `reports/week7-manifest.json`。
