# 第四周交付记录

日期：2026-10-31。第四周会话、检查点、确认经验主流程已验收；第三周 pgvector 和 OpenShell 环境缺口继续保留。

第五周补充：新增 platform 迁移分支和 OTel，当前代码使用 `alembic upgrade platform@head`、先启动观测接收端与 Collector。下文为第四周当时的验收记录，当前启动方式以 README 与第五周记录为准。

## 已交付

- 官方 `langgraph-checkpoint-postgres==3.2.0`、`AsyncPostgresSaver`，通过官方 `setup()` 初始化检查点表。
- 项目所属的 threads；每次调用、确认恢复、失败重试分别创建 run，保存 thread_id、checkpoint_id、source_run_id。
- 相同 thread_id 的多轮消息、已查询证据与遥测证据 ID 保存在检查点中。追问可以引用此前返回的证据，新的会话不继承这些短期状态。
- 显式 `interrupt()` / `Command(resume=...)`：请求附带经验适用范围时，在诊断后展示完整待确认对象，暂停等待客户端确认；拒绝则结束。
- 确认后写入 `knowledge_documents(kind=incident_experience)`，包含来源运行、服务、故障时间、适用条件、诊断和未知事项。未确认或拒绝的内容不进入经验查询。
- 来源运行唯一约束与冲突去重，覆盖归档提交成功但图检查点尚未落盘时的节点重入。
- `search_experiences` MCP 工具与按服务查询的 API，按项目过滤、精确服务名匹配。历史经验必须与新故障的现场证据区分。
- 新接口在读取检查点前检查项目所属关系。会话运行持有 PostgreSQL 会话级 advisory lock，重叠请求返回 409，连接关闭或进程退出释放锁。
- 失败节点可使用最新 checkpoint_id 显式重试；不自动在后台接管任务。过期确认、重复确认及待处理工作期间追加消息返回 409。
- 通用单次评测 CLI 将 interrupted 计为实验未完成，pass_rate 为 null；第四周完整工作流由专用单条验收验证。

## 数据库迁移决策

原数据库在第三周结束时停留于 `0001_week1`，原 `0002_knowledge` 尚未执行。为避免会话与经验文档被向量扩展阻塞，本次将未应用的迁移拆为：

| 迁移 | 内容 | 本机状态 |
|---|---|---|
| 0002_knowledge | 知识文档基础元数据 | 已执行 |
| 0003_sessions | threads、运行关联、经验元数据 | 已执行 |
| 0004_vectors | vector 扩展与 knowledge_chunks | 未执行，缺少服务器扩展文件 |

原 PostgreSQL 17.11 及其数据目录保留，没有安装 PostgreSQL 16、编译工具或系统服务。Checkpoint 是真正的 PostgreSQL 持久化，经验使用知识文档表；向量存储没有替代实现。

当前跨会话经验检索是结构化服务查询，尚未把经验嵌入向量片段。语义经验检索、手册向量入库和第三周效果比较仍需 pgvector 环境补验，不计入本周的向量检索成果。

## 唯一真实业务验收

```powershell
uv run pytest tests/test_week4_acceptance.py -q
```

结果：`1 passed in 50.78s`。只使用 `pool-exhaustion-01` 一个合成故障场景，未运行整个 tests 目录。

该案例包含三个真实模型驱动的对话回合和一次不调用模型的确认恢复：

| 步骤 | 运行 ID | 结果 | 输入 / 输出 Token |
|---|---|---|---:|
| 日志、指标诊断后暂停 | 40452d3e-6892-46e4-839d-a3ba9246c409 | interrupted，诊断检查通过 | 7644 / 993 |
| 重启 API 后确认归档 | a0cc9303-77cb-496a-b70a-c346ba223b0d | diagnosed，归档一条经验 | 0 / 0 |
| 同会话追问 | a40a11b8-c251-44c9-848c-97acc5165ba2 | 沿用此前消息与证据 | 2795 / 524 |
| 新会话查询经验 | c127d916-a012-461b-ba1e-15ddcb309b1d | MCP 查到经验并引用；不认定发生新故障 | 3524 / 681 |

共七次模型调用，合计输入 13963、输出 2198 Token。确认恢复不重新调用模型或现场工具。费用未计算；单条流程耗时不代表性能分位数。

真实 API 服务进程由 PID 29744 更换为 51824；重启后从原 PostgreSQL 检查点恢复。跨会话读取到的经验 ID 为 `experience-40452d3e-6892-46e4-839d-a3ba9246c409`。

确认动作由验收客户端对合成诊断发送，验证的是人工确认机制，不声称经过真实生产运维人员审核。

初次诊断曾两次调用 search_runbooks，均因知识片段表尚不可用而失败；错误原样保留，诊断依据仍为实际日志和指标，没有引用虚构手册。此次通过不代表第三周向量能力已通过。

启动预检曾因本机代理和 Windows 连接超时失败两次，均发生在模型请求之前；已将本地验收连接设为回环直连，并处理测试服务启动等待。Windows 虚拟环境启动器会产生子进程，验收按自己创建的进程树关闭服务，确保重启真实发生。

报告：`reports/week4-acceptance.json`、`reports/week4-acceptance.md`。

## 软件行为与失败路径

`scripts/check_week4.py` 的 19 项检查通过，使用真实 PostgreSQL、检查点和 MCP，只有外部模型使用固定响应或受控异常。覆盖暂停内容、未确认不可检索、新 Python 进程恢复、归档重入去重、拒绝、多轮继承、显式失败重试、超时、步数耗尽、并发冲突、取消、锁释放及跨项目 404。

固定模型生成的经验在探针结束时清理，不能进入后续业务检索。探针运行仍保留并明确标为软件行为证据，不计入真实模型质量样本。

已有 HTTP 生命周期回归的五项检查通过，包括真实 socket 断开后的取消落库与非流式 502。报告保存为 `reports/week4-lifecycle-checks.json`，第二周历史报告保留。

使用 CLI 复核已暂停的原始运行，得到 errors=1、complete=false、pass_rate=null；不会因为已有诊断就把待确认工作流当成完成。后续确认产生另一条关联运行，不改写原始暂停记录。见 `reports/week4-pending-evaluation.json`。

取消探针观察到 psycopg 的 `connection not in pipeline mode` 清理警告；未抑制该警告。运行已记录 cancelled，连接关闭后可重新获取线程锁，两项行为均通过检查。暂未声称覆盖任意时刻断电或数据库故障恢复。

## 启动与使用

保留当前无 pgvector 环境时：

```powershell
uv sync --frozen
.\scripts\local_postgres.ps1 start
uv run alembic upgrade 0003_sessions
uv run agentlens checkpoint-setup
uv run agentlens seed
```

按 README 启动网关与 MCP，API 使用 `uv run python scripts/run_api.py`。Windows 的 psycopg 异步连接需要 Selector 事件循环；API 启动脚本和 CLI 已明确选用该循环。

会话、运行读取和经验接口使用 `X-AgentLens-Project` 请求头。这是开发阶段的项目范围上下文，仍未实现身份认证、SSO 或用户级授权；不要把可由请求方填写的头当成身份凭证。

```powershell
$headers = @{ 'X-AgentLens-Project' = 'project-a' }
$thread = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/threads -Headers $headers
$threadId = $thread.thread_id
```

`POST /threads/{thread_id}/runs` 请求示例：

```json
{
  "prompt": "请调查 order-api 在 2026-10-30T14:00:00+08:00 至 2026-10-30T14:15:00+08:00 的故障，结合日志和指标。",
  "experience": {
    "service": "order-api",
    "start_time": "2026-10-30T14:00:00+08:00",
    "end_time": "2026-10-30T14:15:00+08:00",
    "applicability": "连接池饱和的合成演示；深层原因需继续调查。"
  }
}
```

不请求保存经验时省略 experience；追问使用同一个 thread_id。流式模式附加 `?stream=true`，暂停的终止事件为 run_interrupted，含 checkpoint_id 和待确认对象。insufficient_evidence 诊断不触发经验保存。

`POST /threads/{thread_id}/resume` 使用服务器返回的最新检查点：

```json
{"checkpoint_id":"服务器返回的ID","approved":true}
```

approved=false 表示拒绝。失败节点的显式重试只传 checkpoint_id，不传 approved。客户端可先 GET /threads/{thread_id} 获取最新检查点；服务不会自动重试失败调用。进程意外退出时，运行表可能仍保留上一次 running 状态，检查点和线程锁决定能否显式恢复，不承诺后台状态接管。

GET /experiences?service=order-api 查询确认经验；GET /runs/{run_id} 查询某次运行。两个项目范围不同的请求不能读取同一会话或其经验。旧 /agent/invoke 与 /agent/stream 每次新建会话并返回 thread_id。

## 实现取舍与参考

只增加本次真实失败路径需要的状态校验、并发锁和唯一键，没有建设队列、自动降级、多后端适配或通用策略框架。

- [LangGraph PostgreSQL 记忆与官方 setup](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph interrupt / resume 与节点重入](https://docs.langchain.com/oss/python/langgraph/interrupts)

下一周可继续 OTel 与执行详情；第三周缺口保持独立追踪。
