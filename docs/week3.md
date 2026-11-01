# 第三周交付记录

第六周补充：同一真实案例已检索并引用相关手册，业务验收通过。见 [第六周交付记录](week6.md)；以下仍保留早期缺口和失败记录。

2026-11-01 补充：已在原有 PostgreSQL 17.11 上安装 pgvector 0.8.7，完成迁移、36 个向量入库和真实检索。业务用例已执行，但模型使用泛化查询词，未检索和引用相关手册，因此业务验收未通过。详见 [配置与补验](pgvector-windows.md)。以下保留第三周当时的记录与报告。

日期：2026-10-31。状态：代码与可执行组件检查已交付；pgvector 检索实验和真实端到端验收待补验，第三周尚未完整验收。

第四周补充：原 0002 尚未应用，现已将知识元数据和向量表分别放入 0002_knowledge 与 0004_vectors，0003_sessions 支撑会话及确认经验。本机已升级到 0003_sessions，原记录的 0001 是第三周结束时的状态；向量补验结论不变。

第五周补充：平台与向量迁移现为独立分支；完整环境执行 `alembic upgrade heads`，无 pgvector 的平台环境执行 `alembic upgrade platform@head`。下文当时的 `upgrade head` 命令按此更新。

用户确认保留现有 PostgreSQL 17 环境，记录 pgvector 缺口。不安装编译工具、不另建 PostgreSQL 16、不修改原数据库数据目录。OpenShell 缺口继续保留。

## 本次实现

- 18 份合成排障手册、两个项目、36 个按 H2 小节切分的片段。涵盖五类原有故障，以及锁等待、认证、HTTP 连接池、TLS、磁盘、限流等相似干扰主题。
- 来源、项目、文档 ID、片段 ID、文档内容 SHA-256、整库与切分哈希。手册明确属于合成演示数据。
- `0002_knowledge` 迁移，使用真正的 `vector(512)` 列；服务器没有扩展文件时直接失败，不替换存储或生成假检索结果。
- 本地 CPU embedding：`BAAI/bge-small-zh-v1.5`，固定提交 `7999e1d3359715c523056ef9478215996d62a620`，512 维、归一化、最大 512 Token、固定查询前缀。文档不加查询前缀。下载文件及其哈希位于忽略目录 `.tools/models`。
- `knowledge-import`：先校验小节长度并生成向量，再在事务内替换手册；不覆盖其他 kind 的知识。
- 按项目过滤后的 pgvector 精确余弦检索。当前只有 36 个片段，暂不增加 HNSW/IVFFlat 近似索引。
- MCP `search_runbooks(query, top_k)`，模型不能传项目 ID；返回片段内容、来源、版本和可引用 ID。Agent 保存检索清单与工具结果。
- Prompt 区分现场遥测与手册建议；输出仍只能引用本次实际返回的证据 ID。
- 评估器分别处理有时间窗的遥测与手册，增加相关片段召回、相关片段引用和知识项目范围检查。
- 新增一条第三周业务用例及同场景的检索查询。原 `datasets/dev.jsonl` 保留，不把新验收契约混入历史基线。
- `retrieval-eval` 比较向量基线和关键词 RRF 候选，固定切分、embedding、候选池 10、Top-K=3、RRF offset=60；记录逐条结果、Hit@3、Recall@3、差值与 improved/regressed/unchanged/mixed。

业务 MCP 默认仍使用向量基线。融合只作为待验证的候选；没有证据就不宣称效果提升。

## 实际验证与未验证内容

`scripts/check_week3.py` 使用真实本地 BGE、真实 MCP HTTP 与原 PostgreSQL。包含手册与标签完整性、真实向量输出、SQL 编译、参数边界、引用评分和真实关键词 SQL 检查。评估器测试使用历史运行的显式变异副本，这些副本不作为 Agent 运行或质量实验保存。

模型实际输出为有限、归一化的 512 维向量；36 个小节最大 132 Token，没有被截断。检查详情见 `reports/week3-checks.json`。

关键词 SQL 初次探针发现：`simple` 分词将中文标点邻接的英文词拼接，例如 `HikariPool。connection`，使独立技术词匹配失败。现对文档先用 PostgreSQL `regexp_replace` 分隔非 ASCII 技术词字符，再运行全文检索。检索只融合英文服务名、错误码和指标名；不声称实现了中文关键词分词。

静态检查 `ruff check`、Python 编译和 Alembic 离线 SQL 生成通过。这些检查不等于在服务器执行了新迁移或向量查询。

唯一业务验收入口：

```powershell
uv run pytest tests/test_week3_acceptance.py -q -rs
```

实际结果：`1 skipped in 1.08s`，因为原 PostgreSQL 17.11 没有 vector 扩展。没有发起新业务运行，没有调用 DeepSeek，没有生成故障诊断结果。

`reports/week3-retrieval.json` 是明确的环境阻塞记录，指标与逐例排名为 null，不能拿来当质量对比结果。未执行的内容包括新表迁移、向量入库、实际项目过滤后的向量检索、完整融合排名和带手册引用的真实 Agent 运行。原数据库版本仍为 `0001_week1`。

## 环境补齐后的顺序

在具有 pgvector 扩展文件的 PostgreSQL 上配置 `AGENTLENS_DATABASE_URL`。本机 Python 依赖与本地模型已经准备好，迁移仍需要服务器侧扩展。

```powershell
uv sync --frozen
uv run python scripts/generate_runbooks.py
uv run python scripts/generate_week3_case.py
uv run python scripts/download_embedding.py
uv run alembic upgrade head
uv run agentlens seed
uv run agentlens knowledge-import
```

按 README 启动网关、MCP 与 API，然后执行：

```powershell
# 同一条查询，只比较检索策略，不调用聊天模型。
uv run agentlens retrieval-eval --case pool-exhaustion-retrieval-01 --report reports/week3-retrieval.json

# 唯一真实业务用例，通过 SSE → MCP → pgvector 与遥测库。
uv run pytest tests/test_week3_acceptance.py -q -rs
```

真实验收要求日志、指标和手册三类工具均被调用，诊断符合遥测证据，最终至少引用一个已标注相关片段，且片段属于当前项目。不会运行整个 tests 目录。

若要用评测 CLI 复核该运行，不再次调用模型：

```powershell
uv run agentlens eval --dataset datasets/week3.jsonl --case pool-exhaustion-01 --recorded-run RUN_ID --name week3-rag --report reports/week3-evaluation.json
```

源文件修改入口：手册改 `datasets/runbooks/catalog.json` 后重新生成 Markdown；业务遥测改 `scripts/generate_fixtures.py`；第三周用例改 `scripts/generate_week3_case.py`。导入和实验中不将相关标签或标准答案传给模型工具。

## 参考与边界

- [pgvector](https://github.com/pgvector/pgvector)：向量列与精确余弦查询。Windows 官方构建路径需要 Visual Studio C++；本机未配置。
- [BGE 官方模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)：固定模型、查询前缀与归一化方式，模型采用 MIT 许可。
- [PostgreSQL 全文检索](https://www.postgresql.org/docs/17/textsearch-controls.html)：`to_tsvector`、`websearch_to_tsquery` 和排名。

本次不增加检索框架、自动降级、通用 embedding 供应商接口或新增配置策略。缺少 pgvector 时按实际错误处理；API 与 MCP 项目范围仍不是用户身份认证。第四周工作不改变第三周尚待补验的事实。
