"""Start pinned local Prometheus and Grafana; no Windows services or global config."""

import json
import os
import secrets
import subprocess
import time

import yaml

from agentlens.config import ROOT, Settings


def prepare():
    directory = ROOT / ".tools/monitoring"
    for name in ("grafana-data", "grafana-logs"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    keys = json.loads(Settings().identity_path.read_text(encoding="utf-8"))["local_cli"]
    jobs = []
    for project, key in keys.items():
        credential = directory / f"{project}.key"
        credential.write_text(key, encoding="utf-8")
        jobs.append(
            {
                "job_name": f"agentlens-{project[-1]}",
                "metrics_path": "/metrics",
                "authorization": {"credentials_file": credential.as_posix()},
                "static_configs": [{"targets": ["127.0.0.1:8000"]}],
            }
        )
    config = {
        "global": {"scrape_interval": "5s", "evaluation_interval": "5s"},
        "rule_files": [(ROOT / "configs/observability/alerts.yaml").as_posix()],
        "scrape_configs": jobs,
    }
    path = directory / "prometheus.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    password = directory / "grafana-admin.txt"
    if not password.exists():
        password.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return directory, path, password


def main():
    directory, config, password = prepare()
    prometheus = next((directory / "prometheus").rglob("prometheus.exe"))
    grafana = next((directory / "grafana").rglob("grafana.exe"))
    environment = {
        **os.environ,
        "GF_SERVER_HTTP_ADDR": "127.0.0.1",
        "GF_PATHS_DATA": str(directory / "grafana-data"),
        "GF_PATHS_LOGS": str(directory / "grafana-logs"),
        "GF_PATHS_PROVISIONING": str(ROOT / "configs/observability/grafana/provisioning"),
        "AGENTLENS_DASHBOARDS": str(ROOT / "configs/observability/grafana/dashboards"),
        "GF_SECURITY_ADMIN_PASSWORD": password.read_text(encoding="utf-8"),
        "GF_ANALYTICS_REPORTING_ENABLED": "false",
        "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
    }
    handles, processes = [], []
    try:
        for name, args in [
            (
                "prometheus",
                [
                    str(prometheus),
                    f"--config.file={config}",
                    f"--storage.tsdb.path={directory / 'prometheus-data'}",
                    "--web.listen-address=127.0.0.1:9090",
                ],
            ),
            ("grafana", [str(grafana), "server", "--homepath", str(grafana.parent.parent)]),
        ]:
            log = (directory / f"{name}.log").open("wb")
            handles.append(log)
            processes.append(
                subprocess.Popen(args, env=environment, stdout=log, stderr=subprocess.STDOUT)
            )
        print("Monitoring started on loopback ports 9090 and 3000; Ctrl+C stops both", flush=True)
        while True:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("Monitoring process exited; inspect .tools/monitoring/*.log")
            time.sleep(0.5)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        for log in handles:
            log.close()


if __name__ == "__main__":
    main()
