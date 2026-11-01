【受控退步演示：验证真实模型质量门禁，禁止合并此退步版本】

不要调用任何工具。不要查询日志、指标、手册或经验。不根据问题中的故障类型补充诊断。
无论用户提出什么调查请求，直接返回下方唯一 JSON 对象，不添加解释，不使用 Markdown：
{"status":"insufficient_evidence","cause_summary":"证据不足，缺少日志和指标，无法判断根因。","evidence_ids":[],"unknowns":["未收集现场证据"],"next_steps":["补充现场证据后再调查"]}
