"""Fetch pinned official Windows monitoring binaries and verify published checksums."""

import hashlib
import json
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic

import httpx

from agentlens.config import ROOT

PACKAGES = [
    (
        "prometheus",
        "https://github.com/prometheus/prometheus/releases/download/v3.15.1/"
        "prometheus-3.15.1.windows-amd64.zip",
        "ba25b5e590520cb9fb028edef99bdc8523244d2d489b8c629e0d453d94fb030b",
    ),
    (
        "grafana",
        "https://dl.grafana.com/grafana/release/13.3.0/"
        "grafana_13.3.0_40412481033_windows_amd64.tar.gz",
        "748358c29405b50b28c67792f264b5a49c07faf4c2c353b652db3ab751bb874d",
    ),
]


def download(package):
    name, url, checksum = package
    directory = ROOT / ".tools/monitoring" / name
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / ("verified.tar.gz" if name == "grafana" else url.rsplit("/", 1)[-1])
    if name == "grafana" and not archive.exists():
        # The official CDN throttles a single stream on this network. Resume bounded ranges.
        with httpx.Client(trust_env=False, timeout=30) as client:
            response = client.head(url)
            response.raise_for_status()
            size = int(response.headers["content-length"])
        parts = directory / "parts"
        parts.mkdir(exist_ok=True)
        chunk = 4 * 1024 * 1024

        def part(index):
            start, end = index * chunk, min(size, (index + 1) * chunk) - 1
            path = parts / str(index)
            if path.exists() and path.stat().st_size == end - start + 1:
                return
            with transfer.stream(
                "GET",
                url,
                headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
            ) as response:
                expected = f"bytes {start}-{end}/{size}"
                if response.status_code != 206 or response.headers.get("content-range") != expected:
                    raise RuntimeError("Official CDN did not honor the requested range")
                began = monotonic()
                with path.open("wb") as stream:
                    for data in response.iter_raw():
                        stream.write(data)
                        if monotonic() - began > 240:
                            raise TimeoutError(
                                "Range transfer exceeded four minutes; rerun to resume"
                            )
            if path.stat().st_size != end - start + 1:
                raise RuntimeError("Incomplete download range")

        with (
            httpx.Client(
                trust_env=False,
                timeout=45,
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
            ) as transfer,
            ThreadPoolExecutor(max_workers=16) as workers,
        ):
            for future in as_completed(
                workers.submit(part, i) for i in range((size + chunk - 1) // chunk)
            ):
                future.result()
        with archive.open("wb") as stream:
            for index in range((size + chunk - 1) // chunk):
                stream.write((parts / str(index)).read_bytes())
    if not archive.exists():
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with archive.open("wb") as stream:
                for chunk in response.iter_bytes():
                    stream.write(chunk)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != checksum:
        raise RuntimeError(f"Checksum mismatch: {name}; remove incomplete archive before retry")
    if name == "prometheus":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(directory)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(directory, filter="data")
    print(f"{name}: official archive checksum verified", flush=True)
    return {"name": name, "source": url, "sha256": checksum}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(download, PACKAGES))
    (ROOT / "reports/week9-monitoring-binaries.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
