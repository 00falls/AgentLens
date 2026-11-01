# Flash 固定 10 条开发集评测记录

本地 9/10；远端完整三轮为 8/10 → 0/10 → 9/10。原定绿→红→绿未达成；受控退步被阻断，完全相同 Prompt 的恢复轮通过。

| 批次 | 已保存 / 计划 | 通过 | 质量失败 | 异常 | 完整通过率 | 门禁 | 提交 |
|---|---:|---:|---:|---:|---:|---|---|
| [initial_interrupted](https://github.com/00falls/AgentLens/actions/runs/41297327366) | 9/10 | 7 | 1 | 1 | 不完整，不报告 | 拒绝 | `1c94aae` |
| [normal](https://github.com/00falls/AgentLens/actions/runs/41298033467) | 10/10 | 8 | 2 | 0 | 80% | 拒绝 | `d3d94c0` |
| [controlled_regression](https://github.com/00falls/AgentLens/actions/runs/41298426106) | 10/10 | 0 | 10 | 0 | 0% | 拒绝 | `4f6f082` |
| [restored](https://github.com/00falls/AgentLens/actions/runs/41298677005) | 10/10 | 9 | 1 | 0 | 90% | 通过 | `f651719` |

已知模型费用 $0.043245360；中断轮剩余预留 $0.189800918；保守预算占用 $0.233046278，低于已授权 $1。存在未观测在途用量，不能将已知费用冒充最终账单。

共完整保存 49 次独立业务运行，另 1 次可能已开始。覆盖始终是同一组 10 条开发案例，不是 49 个不同案例。

各轮 JSON 含完整轨迹、逐例评分、故障家族、可重叠失败分类和版本哈希；workflow.json / artifacts.json 记录对应 Actions 与产物。Actions 产物有有效期，关键 JSON / Markdown 已入仓库保留。
