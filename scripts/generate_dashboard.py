"""Generate the small provisioned dashboard from the metrics contract."""

import json

from agentlens.config import ROOT

PANELS = [
    (
        "工具错误率",
        'sum(rate(agentlens_tool_calls_total{job=~"$job",outcome="error"}[5m])) / '
        'sum(rate(agentlens_tool_calls_total{job=~"$job"}[5m]))',
        "percentunit",
    ),
    (
        "运行 P95 延迟",
        "histogram_quantile(0.95,sum by(le)("
        'rate(agentlens_run_duration_seconds_bucket{job=~"$job"}[5m])))',
        "s",
    ),
    (
        "模型 Token / 秒",
        'sum by(direction)(rate(agentlens_model_tokens_total{job=~"$job"}[5m]))',
        "short",
    ),
    (
        "已知费用累计（仅已定价部分）",
        'sum(agentlens_model_cost_usd_total{job=~"$job"})',
        "currencyUSD",
    ),
    ("费用未知的模型调用", 'sum(agentlens_cost_unknown_calls{job=~"$job"})', "short"),
    ("已触发告警", 'ALERTS{job=~"$job",alertstate="firing"}', "short"),
]


def main():
    panels = []
    for i, (title, expression, unit) in enumerate(PANELS):
        panels.append(
            {
                "id": i + 1,
                "title": title,
                "type": "timeseries" if i < 3 else "stat",
                "gridPos": {"x": (i % 2) * 12, "y": (i // 2) * 8, "w": 12, "h": 8},
                "datasource": {"type": "prometheus", "uid": "agentlens-prometheus"},
                "targets": [{"refId": "A", "expr": expression}],
                "fieldConfig": {"defaults": {"unit": unit}},
                "options": {"reduceOptions": {"calcs": ["lastNotNull"]}},
            }
        )
    dashboard = {
        "uid": "agentlens-operations",
        "title": "AgentLens · Quality & Cost",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "5s",
        "time": {"from": "now-15m", "to": "now"},
        "panels": panels,
        "templating": {
            "list": [
                {
                    "name": "job",
                    "type": "query",
                    "datasource": {"type": "prometheus", "uid": "agentlens-prometheus"},
                    "query": "label_values(agentlens_runs_total, job)",
                    "refresh": 1,
                    "includeAll": True,
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                }
            ]
        },
        "description": "Local platform-operator dashboard; unknown costs remain unknown.",
    }
    path = ROOT / "configs/observability/grafana/dashboards/agentlens.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
