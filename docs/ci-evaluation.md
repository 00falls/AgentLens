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
uv run pytest tests/test_ci_evaluation.py tests/test_ci_preparation.py tests/test_week6_contracts.py tests/test_week7_contracts.py -q
```

每轮停止线 $0.20；首次本地及远端三轮共安排 $0.80，另留 $0.20 应对在途调用及必要复核。调用前按完整输入字节量和最大输出保守预留，调用后按实际缓存用量计费。未知计价、未知用量或预算停止时不继续调用，保存已完成与未执行列表，门禁不能判绿。这是应用侧控制，不能保证提供商账单硬封顶。价格快照仅在已核实的 2026-11-01 UTC 时间窗有效；后续运行前须核实官方价格并更新快照，不能直接延长未知费率。

## 门禁

独立策略 `configs/evaluation/ci-gate.json` 保留历史单例策略不变：关键例 `pool-exhaustion-01` 必须通过，基线通过的 9 条均不得退步，总通过率不得低于基线。缺例、执行异常、预算中断、数据 / embedding / 工具 / 评估契约变化均失败。Judge 不参与。

公开仓库 `00falls/AgentLens` 的 `main` 已启用严格分支保护，要求 **Agent quality gate**，包含管理员；[实际配置](../reports/ci/branch-protection.json)。报告和文档发布也通过 PR 检查，不绕过该要求。

GitHub Actions 使用候选 HEAD 的源码和 Prompt，从可信 base 提取基线，校验选例与门禁策略没有变更。失败仍上传 `real-dev10-evidence`，包括 JSON / Markdown、逐例原始运行及服务日志。每例结束立即落盘，无模型自动重试。

同仓库 PR 自动执行真实评测；fork PR 只执行无需密钥的契约测试与前端构建。涉及模型行为的 fork PR 需要维护者转到同仓库分支后才能满足质量检查；不使用 `pull_request_target` 运行贡献者代码。仅文档 / 报告改动跳过付费调用，仍检查软件构建与契约。

## 远端实际结果

同一 [演示 PR](https://github.com/00falls/AgentLens/pull/1) 保留退步与恢复提交。正常与恢复 Prompt SHA 完全相同，三轮数据、工具与评估器契约一致。

| 轮次 | 真实通过率 | 执行异常 | 门禁 | 提交 | Actions / 逐例报告 |
|---|---:|---:|---|---|---|
| 正常复核 | 8/10，80% | 0 | 拒绝 | `d3d94c0` | [运行](https://github.com/00falls/AgentLens/actions/runs/41298033467) / [报告](../reports/ci/remote-normal/ci/candidate.md) |
| 受控退步 | 0/10，0% | 0 | 拒绝 | `4f6f082` | [运行](https://github.com/00falls/AgentLens/actions/runs/41298426106) / [报告](../reports/ci/remote-regression/ci/candidate.md) |
| 恢复 | 9/10，90% | 0 | 通过 | `f651719` | [运行](https://github.com/00falls/AgentLens/actions/runs/41298677005) / [报告](../reports/ci/remote-restored/ci/candidate.md) |

**原定“正常通过→退步失败→恢复通过”未完整达成，实际为红→红→绿。** 正常复核轮的健康案例写“未观察到异常”，没有命中既定关键词“未发现 / 没有 / 正常”，因此 `cause_terms` 失败；证据不足案例也未命中原规则关键词。门禁按 90% 基线如实拒绝 80% 结果。恢复轮健康案例通过，证据不足案例仍失败；没有调整关键词或基线。相同 Prompt 下观测到了词面变化，这说明这组严格规则存在词面敏感性，不能据此推断真实生产质量或认定模型幻觉。

受控退步轮 10 条均直接返回证据不足，实际工具步骤数为 0，所有案例因缺少必需工具而失败；另有引用、根因与手册规则失败，分类计数可能重叠。恢复轮保留真实失败但满足原门禁。

三轮均通过 **44 项无需模型的契约测试和前端构建**；恢复提交虽然与 PR base 的文件内容相同，仍根据本次提交与前一 head 的差异自动跑完 10 条，没有用跳过任务冒充绿色。[正常版本失败截图](../reports/ci/actions-normal.png) 与原始 Actions 可核验状态。

[机器可读总账](../reports/ci/campaign.json) 和 [汇总](../reports/ci/campaign.md) 包含完整 SHA、版本、产物地址、逐例运行及重叠分类。Actions 产物有到期时间，关键 JSON / Markdown 同时保存在仓库；临时服务日志仅放 Actions 产物和被忽略的本地目录。

已知模型费用合计 **$0.043245360**，不含取消时未完整观测的在途用量。取消轮按整轮 $0.20 保守预留，合计预算占用 **$0.233046278**，低于授权 $1；这是预算占用而非最终账单或账单硬上限。完整保存 49 次业务运行，另 1 次可能开始；它们始终复用同一组 10 条开发案例，不是 49 个不同案例。没有自动重试或追加刷绿。

### 首轮中断记录

[首次远端运行](https://github.com/00falls/AgentLens/actions/runs/41297327366) 在修复恢复提交触发逻辑时被取消。服务状态查询存在延迟，取消时已经保存 9 条结果：7 通过、1 质量失败、1 执行异常，另 1 条未完整保存，可能存在在途调用。不能报告这轮完整通过率。原始产物保留于 `reports/ci/initial-setup-evidence/` 和该 Actions 运行。

该目录的 `candidate-gate.json` 是取消后用保存报告进行的离线复核，不是取消任务未完成的原始门禁输出；没有额外调用模型。

质量失败为下游超时案例额外查询了 `payment-api`，违反当前限定目标服务的参数契约；执行异常为证据不足案例在 JSON 前输出说明文字。基于实际失败补充 Prompt 的范围与输出约束，未改变案例或评估器。新增执行中标记，并以真实 Git 提交测试恢复 Prompt 后仍触发评测。用户已明确允许一次必要复核：业务运行总量从预计最多 40 次增加至最多约 50 次，总预算仍为 $1，禁止自动重试和反复刷绿。取消轮未完整观测的计费保守预留整轮 $0.20，不当作已知零费用。

## 求职表述边界

可表述：“构建运维排障 Agent 的逐例评测与 GitHub Actions 回归门禁，在覆盖 8 个场景家族的固定 10 条开发集子集上完成真实 Flash 评测，本地基线 90%，远端正常 / 恢复轮为 80% / 90%；实测跳过工具的受控退步版本为 0% 并被门禁阻断，恢复相同 Prompt 后通过，保留完整轨迹和失败分类。”不能声称三轮绿→红→绿、60 条全量通过、独立保留集或生产质量结论。
