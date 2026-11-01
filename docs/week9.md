# 第九周交付记录

日期：2026-11-01。Prometheus 指标、Grafana、用量与审计工作台、版本化计价、实际缓存用量、两模型配置比较、两条告警规则和固定 API / 工具性能测量已交付。Prometheus / Grafana 实际启动后 6 项集成检查通过，真实 Grafana 浏览器页面通过；结果见 `reports/week9-monitoring.json`、`reports/week9-grafana-ui.json`。

## 指标与账本

认证后的 `/metrics` 按当前身份项目导出：

| 指标 | 含义与有限标签 |
|---|---|
| agentlens_runs_total | 已结束业务账本执行，status 折叠到固定集合 |
| agentlens_run_duration_seconds | 已结束运行的墙钟耗时直方图 |
| agentlens_tool_calls_total | 业务 RunStep 工具尝试，固定 tool 与 ok/error |
| agentlens_model_tokens_total | 模型步骤实际 input/output 用量 |
| agentlens_model_cost_usd_total | 可完整计价调用的已知费用小计 |
| agentlens_cost_unknown_calls | 缺少完整计价依据的模型调用数 |

业务数据库是唯一计量来源；不从父子 Span 或网关重复累加。重启采集进程不清零，重复抓取不增加计数。指标不使用 project_id、run_id、trace_id 或自由模型名作标签；两个固定抓取 job 分别使用两个项目的 Key。录制 mismatch 也保留状态，但持续故障告警排除这种预期边界停止。现场直接 MCP 协议探针与吞吐请求进入审计，不伪造成业务 RunStep。

账本当前包含先前明确标注的受控软件探针；仪表盘是存量执行观察，不是线上成功率。当前数据量很小，收集器直接读取项目账本，尚未实现增量聚合或大规模指标存储；没有吞吐瓶颈证据就不先引入缓存与新数据库。

## 费用与 Prompt 缓存

`configs/observability/pricing.json` 保存币种、版本、来源、核对日期、有效窗口与每百万 Token 价格。此快照只覆盖已核对的 2026-11-01 周日非高峰时段；超出窗口、模型不明或缺少缓存拆分时费用为 null，不默认成零。后续日期必须重新核对价格和时段后更新快照。

每个模型步骤保存提供商 usage（含 input_token_details.cache_read）、response_model 与 billing。成本使用 Decimal 按实际缓存命中/未命中及输出累计。网关返回模型别名时，只对本机已核对的网关配置映射计价，保存网关配置哈希并明确 model_source；没有把别名称作提供商原始模型版本。

本次首次执行的 billing 因别名未知而保留为 null；补齐映射后只对本轮两个 Run 显式补算，保留 billing_at_execution、原始验收报告、补算时间与审计事件，没有新增模型调用。这是有依据的费用估算，不是提供商账单核对。历史执行不批量套用今日价格，项目总费用仍为未知，另展示已知部分。

计价依据：[DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)。记录的是提供商实际报告的缓存 Token；没有进行独立冷/热缓存 A/B，不能声称缓存单独带来某个延迟或费用提升。

## 同一案例的两个配置

唯一案例：pool-exhaustion-01；同一个新建冻结场景 `a0fd28db-8206-4c88-bcb2-bbf15460da52`。由认证后的 API 发起，每个配置一次，Judge 为零。

| 配置 | 网关配置上游 | 质量 | 秒 | 输入 / 输出 Token | 缓存输入 | 估算 USD |
|---|---|---|---:|---:|---:|---:|
| agentlens-agent | openai/deepseek-flash | 16 项规则通过 | 15.233 | 9535 / 1096 | 5120 | 0.001335210 |
| agentlens-candidate | openai/deepseek-v4-pro | 16 项规则通过 | 11.463 | 16939 / 1019 | 9856 | 0.006909232 |

Run ID：Flash `3928c20b-ddda-4a74-b8ee-91642f953870`，Pro `7ce0a761-70b1-4218-8c7b-85ace73466d0`。共 7 次业务模型请求，输入 26474、输出 2115 Token，已知估算总额 $0.008244442。没有执行其他 59 条案例，没有为获得更好结果重复取样。

两配置都通过本例，不能据此判断全面质量；Pro 在本次更快且更贵，也不能据此判断稳定延迟。以这次观测建立 30 秒 / $0.01 的单例建议预算，保存依据和版本；它不是生产 SLO、不作为硬门禁，费用未知不能算通过预算。既有第六周质量门禁保持独立。

报告：`reports/week89-acceptance.json`、`week89-initial-acceptance.json`、`week9-model-comparison.json/.md`。复核报告不调用模型；`pytest tests/test_week89_acceptance.py -q` 会重新发起本案例两种配置的真实模型执行。

## 固定 API 与工具性能

脚本 `scripts/benchmark_week9.py`，Windows 11，AMD64 Family 25 Model 97 Stepping 2、32 逻辑核；48 个测量请求、并发 4。API 先预热 4 次；MCP 四个连接各预热一次，吞吐总墙钟包含连接与预热，延迟分位数仅统计测量请求。

| 对象 | 吞吐 req/s | P50 ms | P95 ms | 错误 |
|---|---:|---:|---:|---:|
| GET /runs?limit=8 | 171.76 | 22.217 | 28.538 | 0 |
| MCP search_logs | 67.15 | 28.734 | 37.068 | 0 |

这是含身份、HTTP、数据库与审计写入的本机短探针，未查找最大承载能力；不与上面的真实模型耗时混报。数据规模为 47 个历史 Run、127 个步骤、120 条日志、148 个指标点、36 个知识片段，均是合成演示数据与测试执行。

同一日志查询的 EXPLAIN (ANALYZE, BUFFERS) 执行 0.039ms，完整计划保留在 `reports/week9-performance.json`；目前没有查询瓶颈证据，本周没有增加索引或缓存。此数据规模不能外推生产容量。

## 告警与 Grafana

规则在 `configs/observability/alerts.yaml`：

- 工具错误率：最近 5 分钟至少 5 次业务工具尝试，错误率超过 20%，持续 1 分钟。
- 持续运行失败：最近 5 分钟至少 3 次 diagnosed / insufficient_evidence / failed，failed 占比超过 50%，持续 2 分钟。

阈值是可解释的演示告警条件，不宣称来自充足生产基线。官方 promtool 已对生产规则执行触发和恢复测试：工具在 3m 触发、12m 恢复；运行在 4m 触发、13m 恢复。输入为明确标注的合成时序，没有制造付费失败运行，也没有向外发送告警通知。没有部署 Alertmanager 或外部通知渠道。

Grafana 提供工具错误率、运行 P95、Token 速率、已知费用小计、费用未知调用数和 firing 告警六个面板。源文件为 `scripts/generate_dashboard.py`，修改后重新生成 JSON。Grafana 是本机平台运维视角，项目 job 选择不是用户授权；使用独立随机管理员密码，不能直接给普通项目用户开放这个跨项目面板。

实测两个带身份的抓取目标均 up，两条规则均已加载且 inactive，Grafana 数据库与 Prometheus 数据源健康，费用查询为 $0.008244442，与业务步骤账本一致。截图见 `reports/week9-grafana-desktop.png`。没有新业务执行的观察窗口中，错误率与延迟 rate 分母没有增长，图表可能为空；没有伪造持续流量填充曲线。

```powershell
uv run python scripts/init_identities.py
uv run python scripts/download_monitoring.py
uv run python scripts/generate_dashboard.py
# API、数据库已启动后，另开终端：
uv run python scripts/run_monitoring.py
```

Prometheus 绑定 127.0.0.1:9090，Grafana 绑定 127.0.0.1:3000。抓取凭证、Grafana 密码、数据和日志均放被忽略的 `.tools/monitoring`；管理员用户名 admin，密码查看本机 grafana-admin.txt，不在聊天或报告展示。Ctrl+C 关闭两者，不注册系统服务。

便携包按官方 SHA256 校验：Prometheus 3.15.1、Grafana OSS 13.3.0。来源：[Prometheus 下载](https://prometheus.io/download/)、[Grafana OSS Windows 下载](https://grafana.com/grafana/download?edition=oss&platform=windows)。

## 复验与限制

无模型检查：`pytest tests/test_week89_components.py -q`、`python scripts/check_week8_mcp.py`、`python scripts/benchmark_week9.py`、promtool 规则测试。新数据库先迁移、导入合成数据和向量，初始化 Checkpoint，并运行 `scripts/prepare_week7_reference.py` 导入注明来源的历史参考，不能把它记为新的模型质量样本。

CI 的付费任务已更新为同一案例两种配置，仍需手动 run_real=true。本次未推送或运行远端 Actions。真实 OpenShell 隔离尚待第八周补验；保留集没有全跑，未做长期压力、容量或独立人工 Judge 校准。

交付时停止本轮临时服务与本地 PostgreSQL；便携监控包、数据与配置保留，按上述命令可重新启动。文件内容哈希见 `reports/week89-manifest.json`。
