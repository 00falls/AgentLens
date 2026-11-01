import os
import subprocess

from agentlens.config import ROOT, Settings

if __name__ == "__main__":
    env = {**os.environ, "AGENTLENS_OTLP_INGEST_KEY": Settings().otlp_ingest_key.get_secret_value()}
    raise SystemExit(
        subprocess.call(
            [
                str(ROOT / ".tools/otelcol/otelcol.exe"),
                "--config",
                str(ROOT / "configs/observability/collector.yaml"),
            ],
            cwd=ROOT,
            env=env,
        )
    )
