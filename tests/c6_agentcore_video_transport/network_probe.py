#!/usr/bin/env python3
"""
C6 Stage 2 — Network probe for AgentCore + Video Connector.

AgentCore microVMs have no public IP — STUN-only paths fail by design.
Vonage TURN URLs are session-dynamic (SDK negotiation), not static FQDNs.

Authoritative Stage 2 gates:
  1. Native imports (Video Connector + Pipecat)
  2. HTTPS egress to Vonage APIs

Informational only:
  - Vonage media domain probe
  - STUN-only (expected fail)

Stage 3 echo test is the authoritative WebRTC join gate.
"""

from __future__ import annotations

import asyncio
import os
import socket
import struct
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vonage_turn import probe_vonage_turn_relay

DEFAULT_HTTPS_HOSTS = (
    "https://api.opentok.com/",
    "https://api.vonage.com/",
    "https://video.api.vonage.com/",
)

STUN_MAGIC_COOKIE = 0x2112A442
STUN_BINDING_REQUEST = 0x0001


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str
    latency_ms: float | None = None
    informational: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class NetworkProbeReport:
    stage: str = "network"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    probes: list[ProbeResult] = field(default_factory=list)
    imports_ok: bool = False
    https_vonage_ok: bool = False
    vonage_media_probe_ok: bool = False
    stun_only_ok: bool = False
    decision: str = "pending"
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        finished = self.finished_at or time.time()
        return {
            "stage": self.stage,
            "duration_ms": int((finished - self.started_at) * 1000),
            "imports_ok": self.imports_ok,
            "https_vonage_ok": self.https_vonage_ok,
            "vonage_media_probe_ok": self.vonage_media_probe_ok,
            "stun_only_ok": self.stun_only_ok,
            "decision": self.decision,
            "recommendation": self.recommendation,
            "probes": [asdict(p) for p in self.probes],
        }


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _ms(start: float) -> float:
    return round((time.time() - start) * 1000, 1)


def _build_stun_binding_request() -> bytes:
    header = struct.pack("!HHI", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE)
    return header + os.urandom(12)


def _is_stun_binding_response(data: bytes) -> bool:
    if len(data) < 20:
        return False
    msg_type, msg_len, cookie = struct.unpack("!HHI", data[:8])
    return cookie == STUN_MAGIC_COOKIE and msg_type == 0x0101 and msg_len <= len(data) - 20


async def probe_imports() -> ProbeResult:
    start = time.time()
    details: list[str] = []
    ok = True
    modules = (
        ("vonage", "vonage"),
        ("vonage_video", "vonage_video"),
        ("vonage_video_connector", "vonage_video_connector"),
        ("pipecat.transports.vonage.video_connector", "pipecat VonageVideoConnectorTransport"),
        ("pipecat.transports.vonage.client", "pipecat VonageClient"),
    )
    for module_name, label in modules:
        try:
            __import__(module_name)
            details.append(f"{label}: ok")
        except ImportError as exc:
            ok = False
            details.append(f"{label}: FAIL ({exc})")

    return ProbeResult("imports", ok, "; ".join(details), _ms(start))


async def probe_https(urls: tuple[str, ...], timeout: float) -> ProbeResult:
    start = time.time()
    successes: list[str] = []
    failures: list[str] = []

    def _fetch(url: str) -> tuple[str, str | None]:
        try:
            req = Request(url, method="GET", headers={"User-Agent": "c6-network-probe/5.0"})
            with urlopen(req, timeout=timeout) as resp:
                return url, f"HTTP {resp.status}"
        except HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 405, 422, 426}:
                return url, f"HTTP {exc.code}"
            return url, str(exc)
        except URLError as exc:
            return url, str(getattr(exc, "reason", exc))
        except Exception as exc:
            return url, str(exc)

    for url in urls:
        url, result = await asyncio.to_thread(_fetch, url)
        (successes if result and result.startswith("HTTP") else failures).append(f"{url} ({result})")

    ok = bool(successes)
    detail = f"ok={len(successes)} fail={len(failures)}"
    if successes:
        detail += f"; {successes[0]}"
    elif failures:
        detail += f"; {failures[0]}"
    return ProbeResult("https_vonage", ok, detail, _ms(start), meta={"successes": successes, "failures": failures})


async def probe_stun_only_informational(timeout: float) -> ProbeResult:
    start = time.time()
    host = os.getenv("C6_STUN_HOST", "stun.l.google.com").strip()
    port = int(os.getenv("C6_STUN_PORT", "19302"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.sock_sendto(sock, _build_stun_binding_request(), (host, port)),
            timeout=timeout,
        )
        data = await asyncio.wait_for(loop.sock_recv(sock, 2048), timeout=timeout)
        ok = _is_stun_binding_response(data)
        detail = (
            f"STUN-only responded from {host}:{port} (unexpected in AgentCore)"
            if ok
            else f"STUN-only no response from {host}:{port} (expected — AgentCore has no public IP)"
        )
        return ProbeResult("stun_only_informational", ok, detail, _ms(start), informational=True)
    except Exception as exc:
        return ProbeResult(
            "stun_only_informational",
            False,
            f"STUN-only failed {host}:{port}: {exc} (expected in AgentCore)",
            _ms(start),
            informational=True,
        )
    finally:
        sock.close()


async def probe_vonage_media_informational(timeout: float) -> ProbeResult:
    start = time.time()
    relay = await probe_vonage_turn_relay(timeout=timeout)
    return ProbeResult(
        name="vonage_media_informational",
        ok=bool(relay.get("vonage_turn_relay_ok")),
        detail=relay.get("detail", ""),
        latency_ms=_ms(start),
        informational=True,
        meta=relay,
    )


def _evaluate_decision(report: NetworkProbeReport) -> None:
    if not report.imports_ok:
        report.decision = "fail_imports"
        report.recommendation = (
            "Video Connector native binary or Pipecat deps failed to load. "
            "Fix Dockerfile (Python 3.13, ARM64, libpulse/libssl, vonage-video-connector)."
        )
        return

    if not report.https_vonage_ok:
        report.decision = "fail_https"
        report.recommendation = (
            "HTTPS egress failed. Vonage REST and/or AWS API calls will not work from runtime."
        )
        return

    report.decision = "pass_vonage_sdk"
    media_note = (
        " Vonage media domain reachable."
        if report.vonage_media_probe_ok
        else " TURN is session-dynamic via SDK (static hostname probes are not authoritative)."
    )
    report.recommendation = (
        f"Imports and HTTPS egress OK.{media_note} "
        "Proceed to Stage 3 echo test — authoritative WebRTC join gate."
    )


async def run_network_probe() -> dict[str, Any]:
    timeout = _env_float("C6_PROBE_TIMEOUT_SECONDS", 5.0)
    https_hosts = tuple(
        h.strip()
        for h in os.getenv("C6_HTTPS_HOSTS", ",".join(DEFAULT_HTTPS_HOSTS)).split(",")
        if h.strip()
    )

    report = NetworkProbeReport()
    vonage_probe = await probe_vonage_media_informational(timeout)

    ordered_probes = [
        await probe_imports(),
        await probe_https(https_hosts, timeout),
        vonage_probe,
        await probe_stun_only_informational(timeout),
    ]
    report.probes.extend(ordered_probes)

    report.imports_ok = ordered_probes[0].ok
    report.https_vonage_ok = ordered_probes[1].ok
    report.vonage_media_probe_ok = vonage_probe.ok
    report.stun_only_ok = ordered_probes[3].ok

    _evaluate_decision(report)
    report.finished_at = time.time()
    return report.to_dict()


def main() -> None:
    import json

    result = asyncio.run(run_network_probe())
    print(json.dumps(result, indent=2))

    if result["decision"] in {"fail_imports", "fail_https"}:
        print(f"\nC6 Stage 2 STOP — {result['recommendation']}")
        raise SystemExit(1)

    if str(result["decision"]).startswith("pass"):
        print(f"\nC6 Stage 2 PASS — {result['recommendation']}")
        raise SystemExit(0)

    print(f"\nC6 Stage 2 PARTIAL — {result.get('recommendation', '')}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
