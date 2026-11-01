# 第六周验收摘要

日期：2026-11-01。仅新增一条真实业务运行，pool-exhaustion-01；不是 60 条用例全部通过。

| 项目 | 结果 |
|---|---|
| 数据准备 | 40 条开发、20 条保留；故障家族不跨集合 |
| 确定性契约 | 15 passed |
| 唯一真实业务验收 | 1 passed in 30.85s；业务本身约 18.52 秒 |
| 候选运行 | 7535debc-676f-4ce7-8ae3-dc31de32d0cf |
| 候选业务用量 | 9014 输入 / 1099 输出 Token |
| 当前规则 | 16 项通过 |
| 相对失败基线改善 | 相关手册召回与引用两项 |
| 受控退步门禁 | 虚假引用退出码 1；恢复副本退出码 0 |
| 工作台 | 10 项检查通过 |
| Judge 一致性 | 12 条 AI 参考样本；32/48 项一致，16 项分歧 |
| Judge 门禁 | 分数不参与硬门禁；要求评分响应完整 |
| 远端 CI | 工作流已配置、YAML 已检查，尚未运行 Actions |

最终实验使用最终评估器和 rubric 重新评分已有运行，未新增业务执行。最初真实测试的报告与版本也完整保留。

- [最终复核](week6-final-verification.json)
- [基线实验](experiments/week6-baseline.json)、[候选实验](experiments/week6-candidate.json)
- [Judge 一致性报告](week6-calibration.json)、[用量账本](week6-usage.json)
- [门禁演示](week6-gate-demo.json)、[界面检查](week6-ui.json)
- [完整交付记录](../docs/week6.md)

Judge 参考标签由助手按用户要求编写，不是独立人工标注；同一故障的受控答案变体不代表整体业务质量。OpenShell 既有缺口保留。
