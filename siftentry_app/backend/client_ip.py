"""Explicit client-address trust for authentication budgets.

The API never trusts a client-supplied address header on its own. A request's
address comes from exactly one of these sources, in order:

1. Gateway attestation. The SiftEntry web tier signs the browser address it
   observed with the secret in ``EZ_API_GATEWAY_SHARED_SECRET`` (HMAC-SHA256
   over ``"<unix seconds>|<ip>"``), sent as ``X-Siftentry-Client-Ip`` and
   ``X-Siftentry-Client-Signature: <seconds>.<hex digest>``. This is the only
   mechanism that survives Vercel -> Railway, where the TCP peer is never the
   browser and forwarded headers cross hops the API does not control.
2. Trusted proxy. When the TCP peer is listed in ``EZ_API_TRUSTED_PROXY_IPS``
   (addresses or CIDR ranges), the client is the rightmost ``X-Forwarded-For``
   entry that is not itself a trusted proxy.
3. The TCP peer. Every client-supplied header is ignored, so a direct request
   cannot claim another address to escape its budget.

Only sources 1 and 2 produce a verified address. Verified addresses receive
per-address budgets; unverified ones share the budget of the hop they arrive
through. Enabling uvicorn forwarded headers alone is deliberately not enough.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

CLIENT_IP_HEADER = "x-siftentry-client-ip"
CLIENT_SIGNATURE_HEADER = "x-siftentry-client-signature"
SIGNATURE_MAX_AGE_SECONDS = 300


@dataclass(frozen=True)
class ClientAddress:
    ip: str
    verified: bool
    source: str  # gateway | trusted_proxy | peer


def sign_client_ip(secret: str, ip: str, timestamp: Optional[int] = None) -> str:
    """The signature the web gateway sends beside the observed client address."""
    seconds = int(time.time() if timestamp is None else timestamp)
    digest = hmac.new(
        secret.encode("utf-8"), f"{seconds}|{ip}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{seconds}.{digest}"


def _parse_ip(value: Any) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return None


def _networks(values: Iterable[str]) -> list:
    networks = []
    for value in values or ():
        try:
            networks.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError:
            continue
    return networks


def _in_networks(ip: str, networks: list) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def _gateway_address(headers: Mapping[str, str], secret: str, now: float) -> Optional[str]:
    if len(secret) < 32:
        return None
    ip = _parse_ip(headers.get(CLIENT_IP_HEADER, ""))
    signature = str(headers.get(CLIENT_SIGNATURE_HEADER, "") or "").strip()
    seconds, _, digest = signature.partition(".")
    if not ip or not seconds.isdigit() or not digest:
        return None
    if abs(now - int(seconds)) > SIGNATURE_MAX_AGE_SECONDS:
        return None
    expected = sign_client_ip(secret, ip, int(seconds)).partition(".")[2]
    if not hmac.compare_digest(expected, digest.lower()):
        return None
    return ip


def resolve_client_address(
    request: Any, settings: Any = None, now: Optional[float] = None
) -> ClientAddress:
    peer = str(getattr(getattr(request, "client", None), "host", "") or "unknown")
    headers = getattr(request, "headers", None) or {}
    current = time.time() if now is None else now
    secret = str(getattr(settings, "gateway_shared_secret", "") or "")
    attested = _gateway_address(headers, secret, current)
    if attested:
        return ClientAddress(attested, True, "gateway")
    proxies = _networks(getattr(settings, "trusted_proxy_ips", ()) or ())
    if proxies and _in_networks(peer, proxies):
        forwarded = str(headers.get("x-forwarded-for", "") or "").split(",")
        for candidate in reversed(forwarded):
            ip = _parse_ip(candidate)
            if ip and not _in_networks(ip, proxies):
                return ClientAddress(ip, True, "trusted_proxy")
    return ClientAddress(peer, False, "peer")
