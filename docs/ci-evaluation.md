# 固定 10 条真实评测与远端门禁

本轮固定使用 DeepSeek Flash、`configs/evaluation/ci-cases.json` 中的 10 条开发案例，覆盖 8 个开发故障家族。不运行其余 50 条，不使用 Pro 或 Judge，不报告 60 条全量通过率。

## 本地冻结基线

2026-11-01，独立 `agentlens_eval` 数据库初始化合成日志、指标和 18 份手册 / 36 个片段，没有导入历史经验；每例新建会话。10 条全部完成：9 条通过、1 条质量失败、0 条执行异常、0 条未执行，通过率 **90%**。35 次模型调用，已知模型费用 **$0.011233566**。

- [原始报告及全部运行步骤](../reports/ci/local-baseline.json)
- [逐例结果、故障家族和分类汇总](../reports/ci/local-baseline.md)
- [冻结前门禁自检](../reports/ci/local-baseline-gate.json)

已知失败 `w6-insufficient-01`：状态正确为 `insufficient_evidence`，日志和指标工具均返回空，引用与工具参数规则通过。回答写明“未返回任何现场证据”“既无法确认存在异常，也无法定位根因”，但 `cause_summary` 未包含既定关键词“缺少 / 缺失 / 不足”，因此 `cause_terms` 失败。记录为 **根因规则不满足**，不能据此判定生成幻觉。选例、关键词和评分规则保持原样；基线保留这条失败。

基线生成时仓库尚无首个提交，因此报告 `git_commit` 为 null；数据、Prompt、工具、评估器、运行代码均有哈希。远端候选报告必须记录实际 HEAD SHA，使用对应提交中的 Prompt。

## 复现

安装 Python 3.12、uv、PostgreSQL 17 + pgvector 0.8.7，配置 `.env` 的 DeepSeek 密钥，准备官方 Collector。锁文件固定 CPU PyTorch，本地与 CI 使用同一 embedding 修订与合成数据。

```powershell
uv sync --frozen
$env:AGENTLENS_DATABASE_URL='postgresql+psycopg://agentlens:agentlens-local@127.0.0.1:5432/agentlens_eval'
uv run python scripts/prepare_ci_database.py
uv run python scripts/run_ci_services.py --report reports/local/my-dev10.json --baseline reports/ci/local-baseline.json
```

数据库必须没有历史业务运行；初始化脚本不会删除已有运行。如果已有评测记录，请自行保留报告并准备新的空验收数据库环境，不能在原应用数据库执行。每轮使用新报告路径，防止覆盖已有证据。

只检查已有报告，不调用模型：

```powershell
uv run python scripts/run_ci_eval.py --gate-only reports/local/my-dev10.json --baseline reports/ci/local-baseline.json --report reports/local/my-gate.json
uv run pytest tests/test_ci_evaluation.py tests/test_week6_contracts.py tests/test_week7_contracts.py -q
```

每轮停止线 $0.20；首次本地及远端三轮共安排 $0.80，另留 $0.20 应对在途调用及必要复核。调用前按完整输入字节量和最大输出保守预留，调用后按实际缓存用量计费。未知计价、未知用量或预算停止时不继续调用，保存已完成与未执行列表，门禁不能判绿。这是应用侧控制，不能保证提供商账单硬封顶。价格快照仅在已核实的 2026-11-01 UTC 时间窗有效；后续运行前须核实官方价格并更新快照，不能直接延长未知费率。

## 门禁

独立策略 `configs/evaluation/ci-gate.json` 保留历史单例策略不变：关键例 `pool-exhaustion-01` 必须通过，基线通过的 9 条均不得退步，总通过率不得低于基线。缺例、执行异常、预算中断、数据 / embedding / 工具 / 评估契约变化均失败。Judge 不参与。

GitHub Actions 使用候选 HEAD 的源码和 Prompt，从可信 base 提取基线，校验选例与门禁策略没有变更。失败仍上传 `real-dev10-evidence`，包括 JSON / Markdown、逐例原始运行及服务日志。每例结束立即落盘，无模型自动重试。

同仓库 PR 自动执行真实评测；fork PR 只执行无需密钥的契约测试与前端构建。涉及模型行为的 fork PR 需要维护者转到同仓库分支后才能满足质量检查；不使用 `pull_request_target` 运行贡献者代码。仅文档 / 报告改动跳过付费调用，仍检查软件构建与契约。

远端演示记录将在实际三轮完成后补入；未完成前不宣称 CI 闭环成功。

## 求职表述边界

目前可以表述：“构建运维排障 Agent 的逐例评测与回归门禁，在覆盖 8 类故障的固定 10 条开发集子集上完成真实 Flash 评测，通过率 90%，保留关键词规则失败与逐步骤证据。”不能扩写为 60 条全量、独立保留集或生产质量结论。
