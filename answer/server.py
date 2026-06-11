#!/usr/bin/env python3
"""
App Runner / orchestration API — starts the AgentCore video agent for a Vonage session.

POST /start-agent  { "session_id": "...", "token": "..." }  → invoke AgentCore join (nova_sonic)
GET  /status       → poll AgentCore pipeline status (same runtimeSessionId)
POST /leave        → stop AgentCore pipeline

Requires AGENTCORE_RUNTIME_ARN (or C6_AGENTCORE_RUNTIME_ARN) and Vonage creds in env.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
if (REPO_ROOT / ".env").exists():
    load_dotenv(REPO_ROOT / ".env")

app = FastAPI(title="Vonage Video Agent Orchestrator", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# Stable session id per orchestration client — required for join/status/leave affinity
_runtime_session_id: str | None = None


class StartAgentRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    token: str = Field(default="", description="Vonage publisher token; generated if empty")
    mode: str = Field(default="nova_sonic", description="nova_sonic | echo")


def _runtime_arn() -> str:
    arn = (
        os.getenv("AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("C6_AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("AGENTCORE_AGENT_ARN", "").strip()
    )
    if not arn:
        raise HTTPException(
            status_code=500,
            detail="AGENTCORE_RUNTIME_ARN not set — deploy runtime/ first",
        )
    return arn


def _agentcore_client():
    region = (
        os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "us-east-1").strip()
    )
    config = Config(
        retries={"max_attempts": 4, "mode": "standard"},
        connect_timeout=10,
        read_timeout=120,
    )
    # App Runner: instance role via default chain. Local dev: optional AWS_PROFILE.
    profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    on_apprunner = bool(os.getenv("AWS_APP_RUNNER_SERVICE_ID"))
    if profile and not on_apprunner:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)
    return session.client("bedrock-agentcore", config=config)


def _vonage_private_key() -> str:
    """PEM string for Vonage Auth — env (App Runner) or file (local dev)."""
    pem = os.getenv("VONAGE_PRIVATE_KEY_PEM", "").strip()
    if pem:
        return pem.replace("\\n", "\n")

    b64 = os.getenv("VONAGE_PRIVATE_KEY_B64", "").strip()
    if b64:
        return base64.b64decode(b64).decode("utf-8")

    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    private_key_file = Path(private_key_path)
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    if not private_key_file.exists():
        raise HTTPException(status_code=500, detail="Vonage private key not configured")
    return private_key_file.read_text(encoding="utf-8")


def _generate_token(session_id: str) -> str:
    from vonage import Auth, Vonage
    from vonage_video import TokenOptions

    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    if not application_id:
        raise HTTPException(status_code=500, detail="VONAGE_APPLICATION_ID not set")

    client = Vonage(
        Auth(application_id=application_id, private_key=_vonage_private_key())
    )
    token = client.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)


def _invoke(payload: dict[str, Any], *, runtime_session_id: str | None = None) -> Any:
    client = _agentcore_client()
    kwargs: dict[str, Any] = {
        "agentRuntimeArn": _runtime_arn(),
        "contentType": "application/json",
        "accept": "application/json",
        "payload": json.dumps(payload).encode("utf-8"),
    }
    if runtime_session_id:
        kwargs["runtimeSessionId"] = runtime_session_id
    try:
        response = client.invoke_agent_runtime(**kwargs)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise HTTPException(
            status_code=502,
            detail=f"AgentCore invoke failed: {err.get('Code', 'ClientError')}: {err.get('Message', exc)}",
        ) from exc
    except BotoCoreError as exc:
        raise HTTPException(status_code=502, detail=f"AgentCore client error: {exc}") from exc
    body = response.get("payload") or response.get("response")
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body}
    return body


@app.get("/")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "build": os.getenv("BUILD_VERSION", "local"),
        "runtime_arn_set": bool(
            os.getenv("AGENTCORE_RUNTIME_ARN", "").strip()
            or os.getenv("C6_AGENTCORE_RUNTIME_ARN", "").strip()
            or os.getenv("AGENTCORE_AGENT_ARN", "").strip()
        ),
        "vonage_app_id_set": bool(os.getenv("VONAGE_APPLICATION_ID", "").strip()),
        "vonage_key_set": bool(
            os.getenv("VONAGE_PRIVATE_KEY_B64", "").strip()
            or os.getenv("VONAGE_PRIVATE_KEY_PEM", "").strip()
            or os.getenv("VONAGE_PRIVATE_KEY", "").strip()
        ),
    }


@app.post("/start-agent")
async def start_agent(body: StartAgentRequest = Body(...)) -> dict[str, Any]:
    global _runtime_session_id

    session_id = body.session_id.strip()
    try:
        token = body.token.strip() or _generate_token(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vonage token error: {exc}") from exc
    mode = body.mode.strip().lower()
    if mode not in {"nova_sonic", "echo"}:
        raise HTTPException(status_code=400, detail=f"unsupported mode: {mode}")

    _runtime_session_id = str(uuid.uuid4())
    result = _invoke(
        {
            "action": "join",
            "session_id": session_id,
            "token": token,
            "mode": mode,
        },
        runtime_session_id=_runtime_session_id,
    )
    return {
        "orchestrator": "started",
        "runtime_session_id": _runtime_session_id,
        "session_id": session_id,
        "mode": mode,
        "agentcore": result,
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    if not _runtime_session_id:
        return {"running": False, "runtime_session_id": None, "agentcore": None}
    result = _invoke({"action": "status"}, runtime_session_id=_runtime_session_id)
    return {"runtime_session_id": _runtime_session_id, "agentcore": result}


@app.post("/leave")
async def leave() -> dict[str, Any]:
    global _runtime_session_id
    if not _runtime_session_id:
        raise HTTPException(status_code=404, detail="No active AgentCore session")
    result = _invoke({"action": "leave"}, runtime_session_id=_runtime_session_id)
    sid = _runtime_session_id
    _runtime_session_id = None
    return {"runtime_session_id": sid, "agentcore": result}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ANSWER_PORT") or os.getenv("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
