"""Read actual Prometheus targets/rules and provisioned Grafana; no model calls."""

import json

import httpx

from agentlens.config import ROOT


def main():
    password = (ROOT / ".tools/monitoring/grafana-admin.txt").read_text(encoding="utf-8")
    with httpx.Client(trust_env=False, timeout=20) as client:
        targets = client.get("http://127.0.0.1:9090/api/v1/targets").raise_for_status().json()
        active = targets["data"]["activeTargets"]
        rules = client.get("http://127.0.0.1:9090/api/v1/rules").raise_for_status().json()
        query = client.get(
            "http://127.0.0.1:9090/api/v1/query",
            params={"query": "sum(agentlens_model_cost_usd_total)"},
        )
        query.raise_for_status()
        health = client.get("http://127.0.0.1:3000/api/health").raise_for_status().json()
        dashboard = (
            client.get(
                "http://127.0.0.1:3000/api/dashboards/uid/agentlens-operations",
                auth=("admin", password),
            )
            .raise_for_status()
            .json()
        )
        datasource = (
            client.get(
                "http://127.0.0.1:3000/api/datasources/uid/agentlens-prometheus/health",
                auth=("admin", password),
            )
            .raise_for_status()
            .json()
        )
    alert_rules = [rule for group in rules["data"]["groups"] for rule in group["rules"]]
    checks = {
        "two_authenticated_targets_up": len(active) == 2
        and all(t["health"] == "up" for t in active),
        "two_production_rules_loaded": len(alert_rules) == 2,
        "known_cost_query_returns_data": bool(query.json()["data"]["result"]),
        "grafana_database_ok": health["database"] == "ok",
        "six_provisioned_panels": len(dashboard["dashboard"]["panels"]) == 6,
        "grafana_datasource_connected": datasource["status"] == "OK",
    }
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "grafana_version": health["version"],
        "prometheus_jobs": [t["labels"]["job"] for t in active],
        "rules": [{"name": r["name"], "state": r["state"]} for r in alert_rules],
        "known_cost_query": query.json()["data"]["result"],
        "provider_requests": 0,
        "remote_notifications_sent": False,
    }
    (ROOT / "reports/week9-monitoring.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    assert report["passed"]


if __name__ == "__main__":
    main()
