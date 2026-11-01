"""Demo API keys bind one identity to one project at each HTTP trust boundary."""

import hashlib
import hmac
import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from agentlens.config import Settings
from agentlens.db import AuditEvent, create_session


@dataclass(frozen=True)
class Identity:
    actor: str
    project: str
    key: str


identity: ContextVar[Identity | None] = ContextVar("identity", default=None)


def identities(settings):
    return json.loads(settings.identity_path.read_text(encoding="utf-8"))["identities"]


def authenticate(settings, authorization):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    key = authorization[7:]
    fingerprint = hashlib.sha256(key.encode()).hexdigest()
    for item in identities(settings):
        if hmac.compare_digest(fingerprint, item["sha256"]):
            return Identity(item["actor"], item["project"], key)
    return None


def mcp_headers(settings, project, run_id=None):
    current = identity.get()
    if current is None:
        # CLI is a trusted local operator; the HTTP MCP boundary still requires a key.
        credentials = json.loads(settings.identity_path.read_text(encoding="utf-8"))["local_cli"]
        current = Identity("local-cli", project, credentials[project])
    if current.project != project:
        raise ValueError("Identity cannot change its project")
    headers = {"authorization": f"Bearer {current.key}", "x-agentlens-project": project}
    if run_id:
        headers["x-agentlens-run"] = run_id
    return headers


def audit(
    settings,
    *,
    action,
    resource,
    decision="allow",
    result="ok",
    project=None,
    run_id=None,
    detail=None,
    actor=None,
):
    current = identity.get()
    with create_session(settings) as session:
        session.add(
            AuditEvent(
                id=str(uuid4()),
                project_id=project or (current.project if current else None),
                actor=actor or (current.actor if current else "local-cli"),
                action=action,
                resource=resource[:240],
                run_id=run_id,
                decision=decision,
                result=result,
                detail=detail or {},
                timestamp=datetime.now(UTC),
            )
        )
        session.commit()


class IdentityMiddleware:
    def __init__(self, app, *, mcp=False):
        self.app, self.mcp = app, mcp

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if not self.mcp and (path == "/health" or path.startswith("/workbench")):
            return await self.app(scope, receive, send)
        settings = Settings()
        headers = Headers(scope=scope)
        current = authenticate(settings, headers.get("authorization"))
        requested = headers.get("x-agentlens-project")
        status = (
            401 if current is None else 403 if requested and requested != current.project else 0
        )
        if status:
            audit(
                settings,
                action="http.authorization",
                resource=path,
                decision="deny",
                result=str(status),
                project=current.project if current else None,
                actor=current.actor if current else "anonymous",
            )
            return await JSONResponse(
                {"detail": "Invalid API key" if status == 401 else "Project is not authorized"},
                status,
            )(scope, receive, send)
        token = identity.set(current)
        # Establish the project for endpoints that require a project header.
        scope["headers"] = [
            (k, v) for k, v in scope["headers"] if k.lower() != b"x-agentlens-project"
        ]
        scope["headers"].append((b"x-agentlens-project", current.project.encode()))
        response_status = 500

        async def capture(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            if not self.mcp and path not in {
                "/metrics",
                "/operations",
                "/audit-events",
                "/identity",
            }:
                audit(
                    settings,
                    action=f"http.{scope['method'].lower()}",
                    resource=path,
                    result=str(response_status),
                    decision="deny" if response_status in {403, 404} else "allow",
                )
            identity.reset(token)
