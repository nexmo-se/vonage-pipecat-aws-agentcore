#!/usr/bin/env python3
"""
App Runner / orchestration API — starts the AgentCore video agent for a Vonage session.

POST /start-agent  { "session_id": "...", "token": "..." }  → invoke AgentCore join (nova_sonic)
GET  /status       → poll AgentCore pipeline status (same runtimeSessionId)
POST /leave        → stop AgentCore pipeline

Requires AGENTCORE_RUNTIME_ARN (or C6_AGENTCORE_RUNTIME_ARN) and Vonage creds in env.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

app = FastAPI(title="Vonage Video Agent Orchestrator", version="0.1.0")

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
    region = os.getenv("AWS_REGION", "us-east-1").strip()
    profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    config = Config(
        retries={"max_attempts": 4, "mode": "standard"},
        connect_timeout=10,
        read_timeout=120,
    )
    session = boto3.Session(profile_name=profile or None, region_name=region)
    return session.client("bedrock-agentcore", config=config)


def _generate_token(session_id: str) -> str:
    from vonage import Auth, Vonage
    from vonage_video import TokenOptions

    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    private_key_file = Path(private_key_path)
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    if not application_id or not private_key_file.exists():
        raise HTTPException(status_code=500, detail="Vonage credentials not configured")

    client = Vonage(Auth(application_id=application_id, private_key=str(private_key_file)))
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
    response = client.invoke_agent_runtime(**kwargs)
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
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/start-agent")
async def start_agent(body: StartAgentRequest = Body(...)) -> dict[str, Any]:
    global _runtime_session_id

    session_id = body.session_id.strip()
    token = body.token.strip() or _generate_token(session_id)
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

    port = int(os.getenv("ANSWER_PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
