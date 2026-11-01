# 第四周单条业务验收

结果：passed；案例：pool-exhaustion-01。

一条合成故障，三个真实模型驱动回合及一次无模型确认恢复。

| 运行 | 状态 | 输入 Token | 输出 Token |
|---|---|---:|---:|
| 40452d3e-6892-46e4-839d-a3ba9246c409 | interrupted | 7644 | 993 |
| a0cc9303-77cb-496a-b70a-c346ba223b0d | diagnosed | 0 | 0 |
| a40a11b8-c251-44c9-848c-97acc5165ba2 | diagnosed | 2795 | 524 |
| c127d916-a012-461b-ba1e-15ddcb309b1d | insufficient_evidence | 3524 | 681 |

合计：输入 13963、输出 2198 Token。

实际 API 进程：29744 → 51824。

经验 ID：experience-40452d3e-6892-46e4-839d-a3ba9246c409。

诊断检查：project_scope、status、required_tools、query_scope、cause_terms、required_evidence、valid_citations、outside_window_excluded、token_usage_recorded。

pgvector 未验证；初次诊断的两次手册检索因环境缺口失败，错误保留在 JSON。跨会话经验检索按服务查询。

确认由测试客户端对合成场景发送，不声称经过生产运维人工审核。
