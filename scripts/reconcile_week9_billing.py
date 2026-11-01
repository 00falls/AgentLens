"""Enrich only this session's two runs with verified gateway alias pricing, preserving originals."""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from agentlens.agent import read_run
from agentlens.config import ROOT, Settings
from agentlens.db import Run, RunStep, create_session
from agentlens.finops import cost_summary, gateway_model, price_call
from agentlens.security import audit


def main():
    path = ROOT / "reports/week89-acceptance.json"
    original = ROOT / "reports/week89-initial-acceptance.json"
    if not original.exists():
        original.write_bytes(path.read_bytes())
    report = json.loads(path.read_text(encoding="utf-8"))
    for result in report["results"]:
        run_id = result["run"]["run_id"]
        settings = Settings().model_copy(update={"model": result["model_alias"]})
        configured = gateway_model(settings)
        with create_session(settings) as session:
            run = session.get(Run, run_id)
            steps = session.scalars(select(RunStep).where(RunStep.run_id == run_id)).all()
            for step in steps:
                if (
                    step.kind != "model"
                    or (step.output.get("billing") or {}).get("cost") is not None
                ):
                    continue
                price = price_call(
                    step.output["usage"], step.output["response_model"], run.started_at, configured
                )
                price["reconciled_at"] = datetime.now(UTC).isoformat()
                price["reconciliation_reason"] = (
                    "Observed cache counts; local gateway alias mapping verified this session."
                )
                step.output = {
                    **step.output,
                    "billing_at_execution": step.output["billing"],
                    "billing": price,
                }
            session.commit()
            result["billing"] = cost_summary(steps)
            result["run"] = read_run(session, run_id, "project-a")
        audit(
            settings,
            action="billing.reconcile",
            resource=configured["config_sha256"],
            project="project-a",
            run_id=run_id,
            detail={
                "pricing_source": "configured_gateway_mapping",
                "original_report": original.name,
            },
        )
    report["billing_reconciliation"] = {
        "original_report": original.name,
        "provider_calls_added": 0,
        "note": "Observed cache usage + verified local gateway mapping; not a billing invoice. "
        "Original model response alias preserved.",
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            [{"alias": r["model_alias"], "billing": r["billing"]} for r in report["results"]]
        )
    )


if __name__ == "__main__":
    main()
