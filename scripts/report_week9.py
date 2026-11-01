"""Compare the same case and snapshot; one observation per model is not a benchmark distribution."""

import json
from datetime import datetime
from decimal import Decimal

from agentlens.config import ROOT


def main():
    source = json.loads((ROOT / "reports/week89-acceptance.json").read_text(encoding="utf-8"))
    budget = json.loads((ROOT / "configs/observability/budgets.json").read_text(encoding="utf-8"))
    rows = []
    for result in source["results"]:
        run = result["run"]
        elapsed = (
            datetime.fromisoformat(run["finished_at"]) - datetime.fromisoformat(run["started_at"])
        ).total_seconds()
        cache = sum(
            s["output"]["usage"].get("input_token_details", {}).get("cache_read", 0)
            for s in run["steps"]
            if s["kind"] == "model" and s["output"].get("usage")
        )
        cost = result["billing"]["total"]
        rows.append(
            {
                "alias": result["model_alias"],
                "run_id": run["run_id"],
                "quality_passed": result["quality"]["passed"],
                "quality_checks": result["quality"]["checks"],
                "duration_seconds": elapsed,
                "usage": run["usage"],
                "observed_cache_read_tokens": cache,
                "cost_usd": cost,
                "latency_budget": elapsed <= budget["max_duration_seconds"],
                "cost_budget": None
                if cost is None
                else Decimal(cost) <= Decimal(budget["max_cost_usd"]),
                "pricing_model_sources": sorted(
                    {
                        s["output"]["billing"]["model_source"]
                        for s in run["steps"]
                        if s["kind"] == "model"
                    }
                ),
            }
        )
    report = {
        "case_id": source["case_id"],
        "scenario_id": source["scenario_id"],
        "samples_per_configuration": 1,
        "judge_requests": 0,
        "configurations": rows,
        "budget": budget,
        "limitations": [
            "One synthetic case, one observation each; no stable latency or quality ranking.",
            "Provider-observed cache hits; no controlled cold/warm A/B or speedup claim.",
            "Price estimate from cache usage and local gateway mapping, not provider invoice.",
        ],
    }
    path = ROOT / "reports/week9-model-comparison.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 第九周：同一冻结场景的模型配置比较",
        "",
        "一条合成故障用例，每个配置仅一次观测；不代表稳定性能或普遍质量。",
        "",
        "| 配置 | 质量 | 秒 | 输入/输出 Token | 观察到的缓存输入 | 估算 USD |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        u = r["usage"]
        lines.append(
            f"| {r['alias']} | {'通过' if r['quality_passed'] else '失败'} | "
            f"{r['duration_seconds']:.3f} | {u['input_tokens']}/{u['output_tokens']} | "
            f"{r['observed_cache_read_tokens']} | {r['cost_usd'] or '未知'} |"
        )
    lines += [
        "",
        "费用依据提供商用量和本轮核对的网关别名映射；保留原始未计价报告与补算审计。",
        "缓存命中不等于受控缓存加速实验。30 秒 / $0.01 仅为此案例的建议预算，不是生产 SLO。",
        "",
        "计价来源：https://api-docs.deepseek.com/quick_start/pricing/",
    ]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "configurations": len(rows),
                "samples_each": 1,
                "passed": all(r["quality_passed"] for r in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
