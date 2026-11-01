"""Bounded startup readiness for the explicit CI integration experiment."""

import socket
import time

ports = [8001, 4318, 4000, 8010, 8000]
deadline = time.monotonic() + 90
while True:
    pending = []
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)):
                pending.append(port)
    if not pending:
        print("All five local services are listening")
        break
    if time.monotonic() >= deadline:
        raise SystemExit(f"Service startup timed out: {pending}; inspect CI logs")
    time.sleep(0.5)
