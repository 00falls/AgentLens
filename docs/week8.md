# 第八周交付记录

日期：2026-11-01。项目身份、API / MCP 授权、执行审计、工作台登录和 OpenShell 分析工具代码已接入。权限与无运行时路径已实际验证；本机仍没有 Linux / Docker / OpenShell，真实沙盒隔离验收未完成，M8 不记为完整验收通过。

## 身份与权限

`scripts/init_identities.py` 创建两个演示身份，各绑定 project-a 或 project-b。API Key 随机生成，认证按 SHA256 摘要匹配；供本地 CLI 使用的原始密钥保存在被 Git 忽略的 `.tools/identities.json`。重复运行保留已有配置，不改 `.env`，不输出密钥。

```powershell
uv run python scripts/init_identities.py
uv run alembic upgrade heads
```

这是单机演示接入，不是企业 SSO 或独立秘密管理服务。只有信任的本机开发用户应读取该文件；部署时应提供受管凭证文件，并按操作系统权限保护它。没有内置的默认通用 API Key，也不提供关闭认证的开关。

API 和 MCP 的 HTTP 边界都要求 `Authorization: Bearer API_KEY`。身份决定项目；可省略项目头，显式传入不一致的 `X-AgentLens-Project` 返回 403。最初的 invoke / stream 接口还核对请求体 project_id，不能用旧入口绕过授权。会话、Checkpoint 恢复、运行、Trace、评测报告、录制、冻结场景、审计与指标继续使用同一项目范围查询。

只有 `/health` 和工作台静态资源不要求身份。工作台先通过 `/identity` 验证 Key，再请求数据；Key 只保留在页面内存，不写 URL、localStorage、sessionStorage 或报告。刷新或退出后重新登录。项目选择只显示当前身份绑定的项目；切换身份先退出，旧工作区随组件卸载清空。

MCP 另行验证 Key，并核对内部 run 头是否属于授权项目，然后进入已有项目过滤的查询。Agent 只从可信上下文发送这些头，模型工具参数没有项目、运行 ID、凭证或 schema。CLI 是受信任的本地运维入口，可显式选项目；MCP 仍须验证它使用的项目 Key。CLI 自身不作为远程多用户接口。

## analyze_logs 与执行约束

模型传入 `evidence_ids` 和 `python_code`。服务从当前授权 Run 已保存的 search_logs 结果取得行；任何未检索、跨运行或跨项目的 ID 都拒绝，模型不能直接提交一包任意日志来冒充授权数据。最多 100 个 ID、6000 字符代码及 128000 字节任务输入。

Python 中提供 `logs` 列表，代码打印一个 JSON 结果。返回 analyses 列表，包含新证据 ID、来源 ID、代码哈希、结果和运行时。只有用户要求统计分析时才建议使用此工具；普通故障诊断不强制执行代码。新工具也已纳入第七周参数规范化与录制契约。

宿主进程只调用 OpenShell CLI，绝不对模型代码执行 eval / exec / 本地 Python 回退。OpenShell 缺失时明确返回 ToolMessage error；MCP 的预期错误通过 SDK ToolError 显示，未知异常仍保留为服务端故障。

Linux 端准备：

```bash
# 在符合官方前置条件的 Linux / Docker 或 Podman 网关环境执行。
docker build -f configs/sandbox/Dockerfile -t agentlens-analysis:week8 .
openshell gateway add http://127.0.0.1:18080 --local --name local
openshell gateway select local
python scripts/check_sandbox.py
```

网关必须已部署；`gateway add` 只是注册，不能替代网关安装。项目的控制进程也需要已安装且能连接网关的 OpenShell CLI。以官方 CLI 文档为对照：使用独立临时 sandbox、显式镜像和 policy、1 CPU / 512Mi、`--no-auto-providers`；通过 stdin 传任务，不传宿主环境和模型 API Key。exec 禁用登录启动脚本并限时，finally 请求删除整个 sandbox，避免只停止本地 CLI 却留下远程进程。删除请求完成不等于已核实远端资源消失，补验时还需检查生命周期。

策略只允许运行库、只读 `/app` 和写入 `/sandbox`、`/tmp` 等必要路径；网络规则为空，Landlock 使用 hard_requirement。镜像使用非 root analyst 用户；worker 子进程另设 3 秒 CPU、8 秒墙钟、256MiB 地址空间、64KiB 文件输出和进程数上限；父 worker 读取有界文件并返回 JSON。容器总内存上限必须由支持该能力的 Docker / Podman / Kubernetes 驱动落实，不能用不落实内存限制的运行时冒充通过。

这些是实现与配置约束，本机未实测 Linux 内核、驱动、策略、镜像启动或资源隔离。补验脚本包含合法统计、读取镜像中可读但策略禁止的 `/opt/agentlens/denied.txt`、外部网络、墙钟超时、内存与输出限制；不会用宿主普通 subprocess 的结果代替隔离证据。

官方依据：[沙盒管理](https://docs.nvidia.com/openshell/latest/how-it-works/sandboxes/overview)、[CLI](https://github.com/NVIDIA/OpenShell/blob/main/skills/openshell-cli/SKILL.md)、[策略示例](https://github.com/NVIDIA/OpenShell/blob/main/examples/sandbox-policy-quickstart/policy.yaml)。实际部署先核对所安装 CLI 的 --help；本机没有可报告的已验证 OpenShell 版本。

## 审计与结果

0007_audit 迁移增加 audit_events，保存 actor、project、action、resource、run_id、decision、result、timestamp 和必要元数据。覆盖 HTTP 拒绝、项目数据请求、MCP 工具结果、运行开始与结束、确认后保存经验及费用补算。确认拒绝通过恢复运行的 finish 元数据记录。审计中不保存 Authorization、API Key、原始请求体或模型隐藏推理。

`GET /audit-events` 只查询当前项目，最多 200 条；工作台“用量与审计”展示最近事件。未认证事件项目为空，由受信本地数据库运维查看。该表没有应用修改接口，但数据库管理员仍能修改；没有宣称防篡改存储、外部 SIEM 或完整 IAM。

本轮通过：

- 9 项真实 PostgreSQL / API / 指标费用组件检查（与第九周共用）；包括无 Key、无效 Key、请求体与请求头跨项目、外项目 Run / Thread / Trace / Resume、双身份、审计范围、分析来源、无运行时禁止宿主执行。
- 7 项真实 MCP HTTP 检查：无 Key、伪造项目、发现 analyze_logs、合法日志查询、未检索输入拒绝、OpenShell 不可用的明确错误、外项目 Run 拒绝；没有调用提供商。
- 15 项浏览器检查：双身份、Key 不持久化、费用未知、审计、历史/评测/重跑请求携带身份、手机无整页溢出、手机退出及不新增模型运行。

证据：`reports/week8-mcp.json`、`reports/week8-sandbox.json`、`reports/week89-ui.json`、`reports/local/week89-components.xml`。真实模型只验收一条既有故障案例的两个配置，见[第九周](week9.md)；这不算合法沙盒统计已通过。

当前缺口：真实 OpenShell 隔离、网关生命周期与资源限制补验；完整身份与密钥轮换、数据库角色分权、审计外部持久化均未实现。保持本机回环启动，不把此演示暴露为生产服务。
