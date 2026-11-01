"""Generate synthetic telemetry and labels separately; tools only read telemetry."""

import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    {
        "id": "pool-exhaustion",
        "service": "order-api",
        "project": "project-a",
        "hour": 14,
        "log": (
            "HikariPool connection acquisition timed out after 30000ms; active=20, idle=0, max=20"
        ),
        "metrics": [
            ("db_pool_active", 20, "connections"),
            ("db_pool_max", 20, "connections"),
            ("db_pool_waiters", 48, "requests"),
            ("http_5xx_ratio", 0.38, "ratio"),
        ],
        "cause": "数据库连接池耗尽，等待连接引发请求超时与 5xx；连接长期占用的原因尚需调查。",
        "terms": [["连接池", "connection pool"], ["耗尽", "饱和", "exhaust"]],
    },
    {
        "id": "downstream-timeout",
        "service": "order-api",
        "project": "project-a",
        "hour": 15,
        "log": "HTTP request to payment-api timed out after 5000ms; upstream returned 504",
        "metrics": [("payment_api_p95_ms", 6200, "ms"), ("http_5xx_ratio", 0.27, "ratio")],
        "cause": "下游 payment-api 超时导致订单请求失败。",
        "terms": [["payment", "支付"], ["超时", "timeout"]],
    },
    {
        "id": "config-regression",
        "service": "payment-api",
        "project": "project-a",
        "hour": 16,
        "log": "After deploy v2.4.1: database host pg-paymnt.internal cannot be resolved; NXDOMAIN",
        "metrics": [("dns_failures", 190, "requests"), ("http_5xx_ratio", 0.91, "ratio")],
        "cause": "发布后的数据库地址配置错误，引发 DNS 解析失败。",
        "terms": [["配置", "地址"], ["DNS", "解析"]],
    },
    {
        "id": "memory-pressure",
        "service": "inventory-api",
        "project": "project-b",
        "hour": 14,
        "log": "Container terminated: OOMKilled, exitCode=137, memory limit=512MiB",
        "metrics": [
            ("memory_working_set_mb", 511, "MB"),
            ("memory_limit_mb", 512, "MB"),
            ("container_restarts", 4, "restarts"),
        ],
        "cause": "内存逼近限制导致 OOMKilled 和容器重启，内存增长原因尚未确认。",
        "terms": [["内存", "memory"], ["OOM", "重启"]],
    },
    {
        "id": "traffic-spike",
        "service": "inventory-api",
        "project": "project-b",
        "hour": 15,
        "log": "Worker queue full: pending=2400; requests rejected with HTTP 503",
        "metrics": [
            ("request_rate", 1900, "requests/s"),
            ("baseline_request_rate", 120, "requests/s"),
            ("worker_cpu_percent", 99, "percent"),
            ("queue_length", 2400, "requests"),
        ],
        "cause": "流量突增导致工作队列与处理能力饱和，产生 503。",
        "terms": [["流量", "请求量"], ["饱和", "队列", "过载"]],
    },
    {
        "id": "healthy",
        "service": "order-api",
        "project": "project-a",
        "hour": 17,
        "log": "Request completed successfully: status=200 duration_ms=42",
        "metrics": [("http_5xx_ratio", 0, "ratio"), ("p95_latency_ms", 72, "ms")],
        "cause": "当前窗口未发现异常，无法确认用户报告的故障。",
        "terms": [["未发现", "没有", "正常"], ["证据", "异常", "故障"]],
    },
    {
        "id": "insufficient",
        "service": "payment-api",
        "project": "project-b",
        "hour": 17,
        "log": None,
        "metrics": [],
        "cause": "缺少日志和指标，证据不足。",
        "terms": [["证据", "数据"], ["不足", "缺少", "缺失"]],
    },
]


def main():
    logs, metrics, cases = [], [], []
    for scenario in SCENARIOS:
        sid = scenario["id"]
        start = datetime.fromisoformat(f"2026-10-30T{scenario['hour']:02}:00:00+08:00")
        end = start + timedelta(minutes=15)
        common = {"project_id": scenario["project"], "service": scenario["service"]}
        if scenario["log"]:
            logs.extend(
                [
                    {
                        "id": f"{sid}-outside",
                        **common,
                        "timestamp": (start - timedelta(minutes=1)).isoformat(),
                        "level": "INFO",
                        "message": "Pre-window observation; not evidence for this interval",
                    },
                    {
                        "id": f"{sid}-log-1",
                        **common,
                        "timestamp": (start + timedelta(minutes=2)).isoformat(),
                        "level": "INFO" if sid == "healthy" else "ERROR",
                        "message": scenario["log"],
                    },
                ]
            )
        for index, (name, value, unit) in enumerate(scenario["metrics"], start=1):
            metrics.append(
                {
                    "id": f"{sid}-metric-{index}",
                    **common,
                    "timestamp": (start + timedelta(minutes=3)).isoformat(),
                    "name": name,
                    "value": value,
                    "unit": unit,
                }
            )
        window = f"{start.isoformat()} 至 {end.isoformat()}（结束时间不包含）"
        cases.append(
            {
                "case_id": f"{sid}-01",
                "scenario_id": sid,
                **common,
                "input": (
                    f"请调查 {scenario['service']} 在 {window} 的服务异常，"
                    "结合日志和指标给出结论与证据。"
                ),
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "expected_status": "insufficient_evidence"
                if sid in {"healthy", "insufficient"}
                else "diagnosed",
                "expected_cause": scenario["cause"],
                "cause_terms": scenario["terms"],
                "required_tools": ["search_logs", "query_metrics"],
                "required_evidence": [f"{sid}-log-1", f"{sid}-metric-1"]
                if scenario["log"] and sid != "healthy"
                else [],
            }
        )
    # Same-scenario variants stay in the development set, not a future holdout set.
    for case in cases[:3]:
        cases.append(
            {
                **case,
                "case_id": case["case_id"].replace("-01", "-02"),
                "input": case["input"] + "请特别说明哪些更深层原因仍未证实。",
            }
        )
    target = ROOT / "datasets"
    target.mkdir(exist_ok=True)
    (target / "telemetry.json").write_text(
        json.dumps(
            {"synthetic": True, "logs": logs, "metrics": metrics}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (target / "dev.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8"
    )
    print(f"Generated {len(logs)} logs, {len(metrics)} metrics, {len(cases)} cases")


if __name__ == "__main__":
    main()
