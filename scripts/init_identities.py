"""Create local demo keys once; never print keys or overwrite existing identities."""

import hashlib
import json
import secrets

from agentlens.config import Settings

settings = Settings()
if settings.identity_path.exists():
    print("Existing identity file preserved")
else:
    keys = {project: secrets.token_urlsafe(32) for project in ("project-a", "project-b")}
    payload = {
        "identities": [
            {
                "actor": f"demo-{project}",
                "project": project,
                "sha256": hashlib.sha256(key.encode()).hexdigest(),
            }
            for project, key in keys.items()
        ],
        "local_cli": keys,
    }
    settings.identity_path.parent.mkdir(parents=True, exist_ok=True)
    settings.identity_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Created two project-bound demo identities in .tools/identities.json; keys not printed")
