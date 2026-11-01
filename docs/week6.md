# 第六周交付记录

日期：2026-11-01。评测集、轨迹检查、Judge、逐例工作台和门禁代码已交付。本地单条真实业务用例通过；GitHub Actions 工作流已配置但未在远端运行。按用户要求，校准参考标签由助手编写，明确标记为 assistant，不计作人工标注。

## 数据与运行范围

`scripts/generate_week6.py` 生成 60 条合成用例：40 条开发集、20 条保留集，分为 12 个故障家族，每个家族包含 5 个时间窗或数据变体。同一故障家族的全部变体只在一个集合中。开发集包含既有故障与锁等待；保留集为 CPU 限流、磁盘满、证书过期和队列积压。

划分清单与哈希在 `datasets/week6/manifest.json`。唯一真实验收使用开发集 pool-exhaustion-01，其问题与现场证据沿用第三周冻结案例，以便直接对照上次失败记录。其余 59 条仅生成并检查结构、窗口、证据与项目归属，没有运行模型。保留集未用于本次 Prompt 调整，也没有宣称具备全量质量结果。

工具只读取 `telemetry.json` 导入的日志与指标，不读取案例标准答案、相关片段标签或 Judge 参考分数。数据和手册仍是合成演示材料，部分既有证据 ID 含有场景语义，不能据此宣称真实业务泛化能力。

## 确定性评估

- 使用 AgentEvals 0.0.9 的 superset 轨迹匹配检查必要工具；使用 unordered 匹配与参数键约束检查调用参数，不要求日志与指标必须互相排序。
- 禁止工具按调用事实检查；手册查询需在日志和指标调用之后。业务要求的先后关系独立于完整调用轨迹，不强制唯一工具路径。
- 检索、根因、引用、轨迹和任务完成各自输出结果字段；不以 Agent 自称完成作为成功标签。
- 保留项目、时间窗口、必需证据、引用真实性和用量等规则。根因的确定性字段使用状态与术语约束，并不能充分证明因果正确；Judge 提供额外的语义评价。
- 数据集、评估器源码、AgentEvals 版本、运行自身版本和 Judge 配置进入实验记录。对比要求相同数据集、相同选择的案例和相同评估器契约；不兼容时明确拒绝比较。

评测与 Judge 结果保存为 JSON / Markdown；执行异常、评分异常分别记录，实验不完整时 pass_rate 为 null。没有用默认分数覆盖失败。

## 本次业务修复与验收

上次失败运行 `302c48a7-9420-4b60-9ee6-477f6da3e6f0` 在取得现场证据后，仍使用泛化查询，没有检索和引用标注相关手册。本周仅调整业务 Prompt：先取得日志和指标，再使用实际组件、错误或指标术语检索；无关结果需要改用更具体的现场术语。不在业务提示词或工具中写入案例标签、标准答案或相关片段 ID。

```powershell
uv run pytest tests/test_week6_acceptance.py -q
```

实际结果：`1 passed in 30.85s`。这是测试总耗时，包含基线重新评分和候选 Judge；业务运行本身约 18.52 秒，不是性能提升或 P95 结论。

| 字段 | 实际结果 |
|---|---|
| 新业务运行 | 7535debc-676f-4ce7-8ae3-dc31de32d0cf |
| 业务案例 | pool-exhaustion-01，仅一个 |
| 模型 / 工具调用 | 3 / 4 |
| 输入 / 输出 Token | 9014 / 1099 |
| 确定性检查 | 16 项通过 |
| 改善的规则 | runbook_retrieved、runbook_cited |
| 候选检索 | 使用 HikariPool 原始错误与池指标，返回并引用相关手册 |

初次验收与当时 Judge 记录保存在 `reports/week6-initial`，原始测试报告为 `reports/week6-acceptance.json`。后续 Judge 协议调整后，只对相同的已保存运行重新评分，没有再次执行业务 Agent。最终实验在 `reports/experiments/week6-baseline.json`、`week6-candidate.json`；当前评估器、最终门禁和唯一新增运行核对见 `reports/week6-final-verification.json`。

数据库在本轮业务执行前已有 42 条运行，结束后为 43 条。重新评分、校准、界面查看和门禁演示均未增加业务运行。

## Judge 与参考标注

Judge 接收问题、答案、实际工具证据与可用证据 ID 清单，不接收标准根因、案例相关片段标签或参考评分。四个维度为 root_cause、citations、task_completion、grounded_actions，各 0～2 分，保存理由、支持证据、请求模型、rubric 哈希、代码哈希、用量和输入哈希。

用户要求由助手标注，因此 `datasets/judge/week6-labels.json` 的 12 条参考样本明确标记 `label_origin=assistant`。它们是同一真实答案的受控变体，不是 12 次业务执行。参考标签保存逐维理由与证据；原候选 Judge 结果曾对助手可见，因此也不是独立盲审。

评分过程确实发现了协议问题：

1. rubric v1 在第 3 个样本中引用了待评答案的虚假 ID，校验器拒绝结果；前两个有效结果保留。
2. rubric v2 澄清假 ID 只能出现在理由中，但第 9 个样本仍引用了被移除的指标；前八个有效结果保留。
3. 最终 rubric 显式提供实际可用 ID 清单；所有 12 条评分均完成并通过引用校验。无效评分不会被过滤成看似正常的分数；每条评分错误均可记录为错误结果。

前两次报告为 `week6-calibration-v1.json`、`week6-calibration-v2.json`，旧 rubric 为 `prompts/judge-v1.md`、`judge-v2.md`；最终 rubric 为 `prompts/judge.md`。最终一致性报告为 `reports/week6-calibration.json`。

最终 48 项评分中 32 项一致、16 项分歧，一致比例 66.7%。这只是 Judge 与 AI 参考标签的一致性，不是人工准确率。分歧集中在无依据归因、虚假引用和任务完成度上，Judge 往往给出部分支持分数，而参考标签更严格。单个故障的受控变体也不能代表所有任务。

业务 Agent 与 Judge 当前使用同一模型网关别名，不是独立模型的交叉评估。基线虽然没命中案例要求的相关手册，Judge 仍可给出较高语义评分；确定性标签和语义评价反映不同要求。Judge 分数继续作为解释材料，不覆盖规则失败，也不用于硬门禁。独立人工校准仍是后续可信度提升事项。

本轮 Judge 共尝试 28 次评分请求，26 次评分通过校验、2 次因无效证据引用被拒绝。已验证响应累计输入 119128、输出 16612 Token；被拒绝响应未取得解析后的用量，明确记为未知，因此该用量为下界。Agent 用量单独记账，不把 Judge 用量混入业务运行，也未推算货币费用。见 `reports/week6-usage.json`。

## 门禁与逐例工作台

`configs/evaluation/gate.json` 冻结当前唯一关键案例，要求通过确定性规则、评分响应完整，并禁止可比案例发生退步。Judge 分数尚不参与门禁。没有根据一次实验设置整体 5% 或成功率阈值。

```powershell
uv run agentlens gate --baseline reports/experiments/week6-baseline.json --candidate reports/experiments/week6-candidate.json --report reports/local/week6-gate.json
uv run python scripts/check_week6_gate.py
```

门禁退出码演示：在明确标注的记录副本中增加一个未返回的引用，退出码为 1；恢复原副本后为 0。没有修改真实 Agent、数据库答案或 Prompt 来制造退步。演示记录均标记 controlled，位于 `reports/week6-gate-demonstration`；总结为 `week6-gate-demo.json`。

工作台新增“评测对比”：选择基线与候选、逐例变化、候选失败过滤、规则与独立维度、诊断差异、Token 差值、Judge 理由和证据，以及打开原始运行。只读接口为 `/evaluations`、`/evaluations/{id}`、`/evaluation-comparison`。本机实验目录 `reports/experiments` 只放实验报告，其他附件保存在目录外。

所有读取按当前项目范围过滤，切换项目清空旧详情，不把文件名当成授权；当前项目头仍是开发范围，不是完整身份认证。10 项 Edge / Playwright 检查全部通过，包含失败过滤、原始运行跳转、项目隔离、手机无整页横向溢出、无浏览器异常。见 `reports/week6-ui.json` 和桌面、手机截图。

## CI 与复现

`.github/workflows/quality.yml` 配置两个任务：

- PR / main push / 手动触发运行确定性测试和前端构建，不请求模型。
- 只有手动触发且 run_real=true 时，运行一个真实业务案例及两次 Judge。使用 PostgreSQL 17 + pgvector 服务、固定 embedding 与 Collector，上传 JSON、Markdown、JUnit 和日志附件。

真实任务需要仓库 Secret `DEEPSEEK_API_KEY`。本次只写入工作流并检查 YAML；没有推送仓库、配置远端 Secret 或执行 GitHub Actions，因此不声称远端 CI 已通过。

本地常用命令：

```powershell
uv sync --frozen
.\scripts\local_postgres.ps1 start
uv run alembic upgrade heads
uv run agentlens seed --dataset datasets/week6/telemetry.json
uv run agentlens knowledge-import
uv run pytest tests/test_week6_contracts.py -q

# 先按第五周说明启动网关、MCP、API 和观测服务；只选一条案例。
uv run agentlens eval --dataset datasets/week6/dev.jsonl --case pool-exhaustion-01 --judge --name candidate --report reports/experiments/candidate.json

# 评分已有运行，不执行新的业务；--judge 仍会请求评分模型。
uv run agentlens eval --dataset datasets/week6/dev.jsonl --case pool-exhaustion-01 --recorded-run RUN_ID --judge --name candidate-scored --report reports/experiments/candidate-scored.json

# 生成待标注材料，再由明确的评审者填写 reference、reviewer、label_origin。
uv run agentlens calibration-pack --source reports/experiments/week6-candidate.json --output reports/local/reference-pack.json
uv run agentlens calibrate --labels datasets/judge/week6-labels.json --report reports/local/calibration.json
```

CLI 默认的旧开发集仍保留兼容早期命令；第六周请显式指定 `--dataset datasets/week6/dev.jsonl`。`--all` 仍须显式选择，不会因新增 60 条资料自动执行全量实验。

本次 Python ruff、compileall、15 项确定性契约、TypeScript、Vite 构建均通过。交付哈希见 `reports/week6-manifest.json`。本次临时业务服务和数据库在验证后关闭；OpenShell 的既有环境缺口不属于本周完成范围。

参考：[AgentEvals](https://github.com/langchain-ai/agentevals)、[Actions 触发方式](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。
