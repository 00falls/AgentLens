"""Load local provider credentials before starting the LiteLLM CLI."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
# Price-map fetching is unnecessary for token accounting.
# No monetary cost is inferred from this bundled map.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
if not os.environ.get("DEEPSEEK_API_KEY"):
    raise SystemExit("Set DEEPSEEK_API_KEY in .env before starting the real-model gateway")
executable = Path(sys.executable).with_name("litellm.exe" if os.name == "nt" else "litellm")
raise SystemExit(
    subprocess.call(
        [
            str(executable),
            "--config",
            str(ROOT / "configs/gateway/litellm.yaml"),
            "--host",
            "127.0.0.1",
            "--port",
            "4000",
        ],
        cwd=ROOT,
    )
)
