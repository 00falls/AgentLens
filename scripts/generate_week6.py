"""60 synthetic cases; fault families, including all variants, stay in one split."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from generate_fixtures import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
EXTRA = [
    {
        "id": "db-lock-wait",
        "service": "order-api",
        "project": "project-a",
        "log": "PostgreSQL statement blocked; wait_event_type=Lock; blocking_pid=214",
        "metrics": [("db_lock_waiters", 18, "connections"), ("sql_p95_ms", 6200, "ms")],
        "cause": "数据库锁等待导致 SQL 延迟，阻塞事务仍需检查。",
        "terms": [["锁", "Lock"], ["等待", "阻塞"]],
    },
    {
        "id": "cpu-throttling",
        "service": "inventory-api",
        "project": "project-b",
        "log": "Cgroup CPU quota exceeded; throttled_periods rising; request latency high",
        "metrics": [("cpu_throttled_ratio", 0.73, "ratio"), ("p95_latency_ms", 2200, "ms")],
        "cause": "CPU 配额限流导致处理延迟，需核对资源限制。",
        "terms": [["CPU"], ["限流", "配额", "throttl"]],
    },
    {
        "id": "disk-full",
        "service": "inventory-api",
        "project": "project-b",
        "log": "write failed: ENOSPC no space left on device /var/log/inventory",
        "metrics": [("disk_used_ratio", 0.999, "ratio"), ("disk_write_errors", 120, "errors")],
        "cause": "磁盘空间耗尽导致写入失败，需检查占用来源。",
        "terms": [["磁盘", "disk"], ["空间", "满", "耗尽"]],
    },
    {
        "id": "tls-expired",
        "service": "order-api",
        "project": "project-a",
        "log": "TLS handshake failed: certificate has expired for payment-api.internal",
        "metrics": [("tls_handshake_failures", 140, "errors"), ("http_5xx_ratio", 0.6, "ratio")],
        "cause": "下游 TLS 证书过期导致握手失败。",
        "terms": [["TLS", "证书"], ["过期", "expired"]],
    },
    {
        "id": "queue-backlog",
        "service": "inventory-api",
        "project": "project-b",
        "log": "Consumer lag increasing; pending=18000; processing_rate below arrival_rate",
        "metrics": [("consumer_lag", 18000, "messages"), ("oldest_message_age_s", 900, "s")],
        "cause": "消费处理能力低于到达速率导致消息队列积压。",
        "terms": [["积压", "lag"], ["消费", "处理"]],
    },
]


def main():
    target = ROOT / "datasets/week6"
    target.mkdir(parents=True, exist_ok=True)
    anchor = json.loads((ROOT / "datasets/week3.jsonl").read_text(encoding="utf-8"))
    cases, logs, metrics = [], [], []
    groups = SCENARIOS + EXTRA
    for group_index, spec in enumerate(groups):
        sid = spec["id"]
        split = "dev" if group_index < 8 else "holdout"
        for variant in range(5):
            start = datetime.fromisoformat("2026-11-02T08:00:00+08:00") + timedelta(
                days=group_index, hours=variant
            )
            end = start + timedelta(minutes=15)
            prefix = f"w6-{sid}-{variant + 1:02}"
            common = {"project_id": spec["project"], "service": spec["service"]}
            log_id, metric_id = f"{prefix}-log-1", f"{prefix}-metric-1"
            if spec["log"]:
                logs.append(
                    {
                        "id": log_id,
                        **common,
                        "timestamp": (start + timedelta(minutes=2)).isoformat(),
                        "level": "INFO" if sid == "healthy" else "ERROR",
                        "message": f"instance=replica-{variant + 1}; {spec['log']}",
                    }
                )
                # A distractor just outside the left-closed/right-open window.
                logs.append(
                    {
                        "id": f"{prefix}-outside",
                        **common,
                        "timestamp": end.isoformat(),
                        "level": "ERROR",
                        "message": "Unrelated incident outside requested window",
                    }
                )
            for i, (name, value, unit) in enumerate(spec["metrics"], 1):
                adjusted = value if value == 0 or unit == "ratio" else value * (1 + variant / 20)
                metrics.append(
                    {
                        "id": f"{prefix}-metric-{i}",
                        **common,
                        "timestamp": (start + timedelta(minutes=3)).isoformat(),
                        "name": name,
                        "value": adjusted,
                        "unit": unit,
                    }
                )
            case = {
                "case_id": prefix,
                "scenario_id": sid,
                "scenario_group": sid,
                "split": split,
                "synthetic": True,
                "critical": False,
                **common,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "input": f"请调查 {spec['service']} 在 {start.isoformat()} 至 {end.isoformat()}"
                "（结束时间不包含）的异常，结合日志与指标，检索并引用支持建议的手册。"
                + [
                    "",
                    "说明尚未证实的信息。",
                    "区分现场事实与建议。",
                    "请保留证据 ID。",
                    "不要声称已执行修复。",
                ][variant],
                "expected_status": "insufficient_evidence"
                if sid in {"healthy", "insufficient"}
                else "diagnosed",
                "expected_cause": spec["cause"],
                "cause_terms": spec["terms"],
                "required_tools": ["search_logs", "query_metrics"],
                "forbidden_tools": ["execute_shell", "read_secret", "restart_service"],
                "required_evidence": [log_id, metric_id]
                if spec["log"] and sid != "healthy"
                else [],
                "relevant_chunk_ids": [],
                "tool_parameters": {},
                "tool_order": [],
            }
            if sid not in {"healthy", "insufficient"}:
                case["required_tools"].append("search_runbooks")
                case["relevant_chunk_ids"] = [f"{sid}--s01", f"{sid}--s02"]
                case["tool_order"] = [
                    ["search_logs", "search_runbooks"],
                    ["query_metrics", "search_runbooks"],
                ]
            if sid == "pool-exhaustion" and variant == 0:
                case.update(anchor)
                case["critical"] = True
            scope = {k: case[k] for k in ["service", "start_time", "end_time"]}
            case["tool_parameters"] = {name: scope for name in ["search_logs", "query_metrics"]}
            cases.append(case)
    # The anchor reuses frozen week-3 telemetry; tools never read any case labels.
    original = json.loads((ROOT / "datasets/telemetry.json").read_text(encoding="utf-8"))
    original_logs = [r for r in original["logs"] if r["id"].startswith("pool-exhaustion-")]
    original_metrics = [r for r in original["metrics"] if r["id"].startswith("pool-exhaustion-")]
    logs.extend(original_logs)
    metrics.extend(original_metrics)
    # Remove the unused generated anchor window rather than silently evaluating empty fixtures.
    logs = [r for r in logs if not r["id"].startswith("w6-pool-exhaustion-01-")]
    metrics = [r for r in metrics if not r["id"].startswith("w6-pool-exhaustion-01-")]
    for split in ["dev", "holdout"]:
        (target / f"{split}.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases if c["split"] == split),
            encoding="utf-8",
        )
    (target / "telemetry.json").write_text(
        json.dumps(
            {"synthetic": True, "logs": logs, "metrics": metrics}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "synthetic": True,
        "cases": 60,
        "dev": 40,
        "holdout": 20,
        "split_unit": "fault_family_including_all_data_variants",
        "groups": {
            s: sorted({c["scenario_group"] for c in cases if c["split"] == s})
            for s in ["dev", "holdout"]
        },
        "sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(target.glob("*.jsonl"))
        },
        "telemetry_sha256": hashlib.sha256((target / "telemetry.json").read_bytes()).hexdigest(),
        "holdout_usage": (
            "Generated and schema-checked only; not used for prompt tuning or model acceptance"
        ),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "logs": len(logs), "metrics": len(metrics)}))


if __name__ == "__main__":
    main()
