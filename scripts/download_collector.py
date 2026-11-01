"""Project-local official Windows collector binary with a pinned release SHA-256."""

import hashlib
import io
import tarfile

import httpx

from agentlens.config import ROOT

VERSION = "0.164.0"
SHA256 = "ff9a3d79687cca7863bfbea1198542ca0c1800841289541913211d75ab6fea38"


def main():
    url = (
        "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/"
        f"v{VERSION}/otelcol_{VERSION}_windows_amd64.tar.gz"
    )
    response = httpx.get(url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != SHA256:
        raise ValueError("Official Collector archive checksum mismatch")
    target = ROOT / ".tools/otelcol"
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        binary = archive.extractfile("otelcol.exe")
        (target / "otelcol.exe").write_bytes(binary.read())
    print(f"Collector {VERSION} verified and extracted to {target}")


if __name__ == "__main__":
    main()
