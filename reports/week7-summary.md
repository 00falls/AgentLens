# 第七周验收摘要

日期：2026-11-01。录制重跑、冻结场景、执行差异和失败步骤定位已完成。

仅选择 `pool-exhaustion-01`，分别进行两种真实模型执行：

| 模式 | 结果 | 模型请求 | 输入 / 输出 Token |
|---|---|---:|---:|
| 严格录制重跑 | 新手册查询参数未录制，正确停止并保存 replay_mismatch | 2 | 3597 / 387 |
| 冻结场景评测 | diagnosed，16 项质量规则通过 | 3 | 9001 / 1102 |

录制重跑复用了历史日志与指标结果，没有连接 MCP 或回退现场；冻结场景使用真实 PostgreSQL / pgvector 副本，允许新查询。两者均关联原始失败运行 `302c48a7-9420-4b60-9ee6-477f6da3e6f0`。提前停止不算成功诊断，也不作为性能提升。

27 项确定性契约、4 项真实组件测试和 15 项浏览器检查通过；ruff、compileall、TypeScript 与 Vite 构建通过。组件测试只控制外部模型，提供商请求为零；界面检查未新增业务 Run。Judge 请求为零。

临时服务与本地 PostgreSQL 已关闭。未推送仓库或运行远端 Actions。项目范围头尚不是身份授权；OpenShell、正式权限和审计仍留待后续阶段。

完整记录见 [docs/week7.md](../docs/week7.md)，真实验收见 [week7-acceptance.json](week7-acceptance.json)，用量见 [week7-usage.json](week7-usage.json)，交付文件哈希见 [week7-manifest.json](week7-manifest.json)。
