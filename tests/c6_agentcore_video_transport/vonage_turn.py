#!/usr/bin/env python3
"""
Vonage Video API media / TURN helpers for C6.

Vonage TURN is session-dynamic — pod hostnames returned via SDK negotiation,
not static FQDNs. Stage 2 probes media domain reachability and optional ICE API.

Docs:
  https://tokbox.com/developer/guides/configurable-turn-servers/
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STUN_MAGIC_COOKIE = 0x2112A442
STUN_BINDING_REQUEST = 0x0001

DEFAULT_VONAGE_TURN_HOSTS = ()  # legacy static hostnames — not used (see probe note)
DEFAULT_VONAGE_MEDIA_PROBE_HOST = "media.prod.tokbox.com"
DEFAULT_TURN_TLS_PORT = 443
DEFAULT_TURN_UDP_PORT = 3478


@dataclass
class VonageTurnProbeResult:
    vonage_turn_relay_ok: bool = False
    vonage_turn_tls_ok: bool = False
    vonage_turn_udp_ok: bool = False
    vonage_ice_api_ok: bool = False
    hosts_probed: list[str] = field(default_factory=list)
    relay_successes: list[str] = field(default_factory=list)
    relay_failures: list[str] = field(default_factory=list)
    detail: str = ""
    duration_ms: int = 0
    ice_server_count: int = 0


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def vonage_turn_hosts() -> tuple[str, ...]:
    """Legacy static probe hosts — informational only; real TURN is session-dynamic."""
    raw = _env("C6_VONAGE_TURN_HOSTS")
    if raw:
        return tuple(h.strip() for h in raw.split(",") if h.strip())
    return DEFAULT_VONAGE_TURN_HOSTS


def _build_stun_binding_request() -> bytes:
    header = struct.pack("!HHI", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE)
    return header + os.urandom(12)


async def _tcp_probe(host: str, port: int, timeout: float, use_tls: bool) -> tuple[bool, str]:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=use_tls),
            timeout=timeout,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        proto = "TLS" if use_tls else "TCP"
        return True, f"{proto} ok {host}:{port}"
    except Exception as exc:
        return False, f"{host}:{port} failed: {exc}"


async def _udp_binding_probe(host: str, port: int, timeout: float) -> tuple[bool, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.sock_sendto(sock, _build_stun_binding_request(), (host, port)),
            timeout=timeout,
        )
        data = await asyncio.wait_for(loop.sock_recv(sock, 2048), timeout=timeout)
        if len(data) >= 20:
            msg_type, _, cookie = struct.unpack("!HHI", data[:8])
            if cookie == STUN_MAGIC_COOKIE and msg_type == 0x0101:
                return True, f"STUN/TURN binding response {host}:{port}"
        return False, f"unexpected UDP payload from {host}:{port}"
    except Exception as exc:
        return False, f"{host}:{port} udp failed: {exc}"
    finally:
        sock.close()


def _resolve_private_key(private_key_path: str) -> str:
    from vonage_env import resolve_private_key_path

    return str(resolve_private_key_path(private_key_path))


def fetch_vonage_session_ice_servers(
    *,
    application_id: str | None = None,
    session_id: str | None = None,
    private_key_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch session ICE servers from Vonage Video REST API (optional Stage 2 check).

    GET /v2/project/{applicationId}/session/{sessionId}/ice
    """
    application_id = (application_id or _env("VONAGE_APPLICATION_ID")).strip()
    session_id = (session_id or _env("VONAGE_SESSION_ID")).strip()
    private_key_path = private_key_path or _env("VONAGE_PRIVATE_KEY", "private.key")

    if not application_id or not session_id:
        raise ValueError("VONAGE_APPLICATION_ID and session_id required for Vonage ICE API")

    from vonage import Auth, Vonage

    client = Vonage(Auth(application_id=application_id, private_key=_resolve_private_key(private_key_path)))
    jwt_token = client.auth.generate_application_jwt({"exp": int(time.time()) + 300})

    url = f"https://video.api.vonage.com/v2/project/{application_id}/session/{session_id}/ice"
    req = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/json",
            "User-Agent": "c6-vonage-turn-probe/1.0",
        },
    )

    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"Vonage ICE API HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Vonage ICE API request failed: {exc}") from exc

    servers = payload.get("iceServers") or payload.get("ice_servers") or payload
    if isinstance(servers, dict):
        servers = servers.get("iceServers") or servers.get("ice_servers") or []
    if not isinstance(servers, list):
        raise RuntimeError(f"Unexpected Vonage ICE API response shape: {type(servers)}")
    return servers


async def probe_vonage_turn_relay(timeout: float = 5.0) -> dict[str, Any]:
    """
    Vonage TURN reachability check for Stage 2.

    Vonage does NOT use static FQDNs like turn.tokbox.com — TURN URLs are
    session-specific pod hostnames returned during SDK negotiation (GSI /
    iceServers). This probe validates:
      1. DNS/HTTPS to *.tokbox.com media domain (wildcard whitelisting pattern)
      2. Optional Vonage ICE REST API when VONAGE_SESSION_ID is set

    Static turn.tokbox.com / turn.opentok.com probes are skipped — those names
    are not real resolvable endpoints.
    """
    started = time.time()
    media_host = _env("C6_VONAGE_MEDIA_PROBE_HOST", DEFAULT_VONAGE_MEDIA_PROBE_HOST)
    result: dict[str, Any] = {
        "vonage_turn_relay_ok": False,
        "vonage_turn_tls_ok": False,
        "vonage_turn_udp_ok": False,
        "vonage_ice_api_ok": False,
        "vonage_turn_hosts": [media_host],
        "static_turn_probe_skipped": True,
        "static_turn_note": (
            "turn.tokbox.com/turn.opentok.com are not real FQDNs — "
            "TURN URLs are dynamic per session via SDK negotiation"
        ),
        "ice_server_count": 0,
        "relay_successes": [],
        "relay_failures": [],
        "detail": "",
        "duration_ms": 0,
    }

    # Probe wildcard media domain pattern (firewall whitelisting reference)
    tls_ok, tls_detail = await _tcp_probe(media_host, DEFAULT_TURN_TLS_PORT, timeout, use_tls=True)
    udp_ok, udp_detail = await _udp_binding_probe(media_host, DEFAULT_TURN_UDP_PORT, timeout)
    result["vonage_turn_tls_ok"] = tls_ok
    result["vonage_turn_udp_ok"] = udp_ok
    if tls_ok:
        result["relay_successes"].append(f"{media_host}: {tls_detail}")
    else:
        result["relay_failures"].append(f"{media_host}: {tls_detail}")
    if udp_ok:
        result["relay_successes"].append(f"{media_host}: {udp_detail}")
    else:
        result["relay_failures"].append(f"{media_host}: {udp_detail}")

    session_id = _env("VONAGE_SESSION_ID")
    application_id = _env("VONAGE_APPLICATION_ID")
    if session_id and application_id:
        try:
            servers = await asyncio.to_thread(fetch_vonage_session_ice_servers)
            result["vonage_ice_api_ok"] = bool(servers)
            result["ice_server_count"] = len(servers)
            if servers:
                result["relay_successes"].append(
                    f"Vonage ICE API returned {len(servers)} server(s) for session"
                )
        except Exception as exc:
            result["relay_failures"].append(f"Vonage ICE API: {exc}")

    # Authoritative for Stage 2: media domain OR ICE API — SDK handles dynamic TURN
    result["vonage_turn_relay_ok"] = tls_ok or udp_ok or result["vonage_ice_api_ok"]
    result["duration_ms"] = int((time.time() - started) * 1000)

    if result["vonage_ice_api_ok"]:
        result["detail"] = (
            f"Vonage session ICE servers available ({result['ice_server_count']} entries) — "
            "SDK will use dynamic TURN URLs on join"
        )
    elif result["vonage_turn_relay_ok"]:
        result["detail"] = (
            f"Vonage media domain reachable ({media_host}) — "
            "proceed to Stage 3; SDK negotiates dynamic TURN per session"
        )
    else:
        result["detail"] = (
            f"Vonage media domain probe inconclusive ({media_host}) — "
            "not a blocker; Stage 3 echo test is authoritative for WebRTC join"
        )

    return result
