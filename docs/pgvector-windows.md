# Windows pgvector 配置与补验

后续状态：第六周已修复本文记录的泛化手册查询问题，同一案例完成真实业务验收。本文保留首次补验的失败事实，后续证据见 [第六周记录](week6.md)。

日期：2026-11-01。在原有便携 PostgreSQL 17.11 x64 上编译安装 pgvector 0.8.7，没有新建数据库或修改模型密钥。

## 环境配置

用户安装的 Visual Studio Build Tools 位于 `D:\Microsoft_visual_studio\BuildTools2026`，本次使用其 x64 C++ 工具。

从 EDB 官方 PostgreSQL 17.11 Windows x64 binaries 压缩包中，仅提取 `pgsql/include` 到项目 `.tools/pgsql/include`。原有 bin、lib、share 和数据目录继续使用。从 pgvector 官方仓库下载 v0.8.7 源码到 `.tools/pgvector-0.8.7`。

启动原有数据库后，在 x64 Native Tools Command Prompt 中编译：

```bat
set "PGROOT=L:\.tools\pgsql"
cd /d L:\.tools\pgvector-0.8.7
nmake /F Makefile.win
nmake /F Makefile.win install
```

`L:` 是 `scripts/local_postgres.ps1 start` 为本项目建立的映射。使用其他盘符时，同步替换上述路径。编译与安装退出码均为 0；生成的 DLL、control、SQL 文件已安装到项目 PostgreSQL 目录，没有注册系统服务。

压缩包来源、实际下载文件 SHA-256、生成 DLL 的 SHA-256 和数据库验证结果见 `reports/pgvector-setup.json`。这些哈希用于记录本次实际文件，不表示已独立验证上游签名。

## 迁移与知识导入

在项目 PowerShell 中执行：

```powershell
.\scripts\local_postgres.ps1 start
uv run alembic upgrade heads
uv run agentlens knowledge-import
```

现已应用 `0004_vectors` 和 `0005_observability` 两个分支。知识库为 18 份合成手册、36 个片段，实际 `vector_dims(embedding)` 为 512；使用已有的固定 BGE 本地模型。

迁移前已用 pg_dump 创建备份 `reports/local/pgvector-setup/before-pgvector.dump`。导入后原有 40 条运行、82 个步骤、22 个会话、115 个 Span 数量未变，原有 1 条确认经验保留；知识文档新增 18 份手册。后续验收会另外新增运行。

## 检索验证

```powershell
uv run agentlens retrieval-eval --case pool-exhaustion-retrieval-01 --report reports/pgvector-retrieval.json
```

本次使用真实 PostgreSQL 向量查询与本地 embedding，不调用聊天模型。向量与混合检索的 Hit@3 均为 1，Recall@3 均为 0.5；结果 unchanged。只有一条合成开发样本，不据此声称整体检索质量或混合检索提升。

## 单条真实业务补验

临时启动原有网关、MCP、API、Collector 和接收端，运行 `tests/test_week3_acceptance.py` 中的同一条 pool-exhaustion-01，没有扩展到其他用例。

首次尝试因网关 DNS getaddrinfo 失败而中断，输入输出 Token 均为 0；运行记录为 `3ee0392d-1e50-4a8f-ae8c-f030f0440e69`，保留于 `reports/pgvector-first-attempt.json`。相同 aiohttp 网络栈访问 DeepSeek 模型列表恢复 200 后，再次运行同一用例。

第二次模型与 MCP 正常完成，结果为 `1 failed in 17.92s`，不是跳过。运行记录为 `302c48a7-9420-4b60-9ee6-477f6da3e6f0`，输入 / 输出 Token 为 11812 / 1362。12 项业务检查中 10 项通过，失败项为 runbook_retrieved、runbook_cited。

真实 search_runbooks 调用成功，但模型使用了“order-api 服务异常 错误日志 排查”这样的泛化查询，未结合已获取的组件与错误信息；返回了其他主题手册，未覆盖标注相关片段。日志和指标诊断本身通过，pgvector 安装与 MCP 查询链路也已验证。该失败属于 Agent 查询与引用质量问题，不能计作第三周业务验收通过；本次环境配置任务没有更换数据标签、放宽检查或加入自动重试来获得通过结果。

完整轨迹与逐项检查见 `reports/pgvector-acceptance.json`，环境与业务结果的分开结论见 `reports/pgvector-verification.json`。后续质量优化应在已观测错误的基础上处理证据驱动查询，再复测同一验收条件。

原第三周、第五周报告保留当时的环境缺口结论；本次补验另存为 `reports/pgvector-*`。本次临时业务服务已关闭。OpenShell 的 Linux/容器环境缺口仍然保留，经验查询仍按服务匹配，不因本次安装自动获得语义记忆。

参考：[pgvector 官方 Windows 构建说明](https://github.com/pgvector/pgvector#windows)、[EDB 官方 binaries](https://www.enterprisedb.com/download-postgresql-binaries)。
