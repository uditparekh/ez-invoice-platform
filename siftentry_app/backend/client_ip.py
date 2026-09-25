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
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

CLIENT_IP_HEADER = "x-siftentry-client-ip"
CLIENT_SIGNATURE_HEADER = "x-siftentry-client-signature"
SIGNATURE_MAX_AGE_SECONDS = 300
_SIGNATURE = re.compile(r"([1-9][0-9]{0,9})\.([0-9a-fA-F]{64})", re.ASCII)
MAX_IP_LENGTH = 45


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
    text = str(value or "").strip()
    # Scope identifiers belong to local interfaces, not public client identity.
    if not text or len(text) > MAX_IP_LENGTH or not text.isascii() or "%" in text:
        return None
    try:
        address = ipaddress.ip_address(text)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(address)
    except ValueError:
        return None


def parse_trusted_proxy_networks(values: Iterable[str]) -> tuple:
    """Reject invalid/overbroad trust configuration instead of skipping it."""
    networks = []
    for value in values or ():
        try:
            network = ipaddress.ip_network(str(value).strip(), strict=True)
            if network.prefixlen == 0:
                raise ValueError("unrestricted proxy trust")
            networks.append(network)
        except ValueError as exc:
            raise ValueError(
                "EZ_API_TRUSTED_PROXY_IPS must contain valid, explicit IP addresses "
                "or network CIDRs; wildcard ranges and host bits are not allowed"
            ) from exc
    return tuple(networks)


def _in_networks(ip: str, networks: Iterable) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def _gateway_address(headers: Mapping[str, str], secret: str, now: float) -> Optional[str]:
    if len(secret) < 32:
        return None
    raw_ip = str(headers.get(CLIENT_IP_HEADER, "") or "").strip()
    ip = _parse_ip(raw_ip)
    signature = str(headers.get(CLIENT_SIGNATURE_HEADER, "") or "").strip()
    # Bound and validate untrusted input before int() or compare_digest().
    if not ip or len(signature) > 75:
        return None
    match = _SIGNATURE.fullmatch(signature)
    if not match:
        return None
    seconds, digest = match.groups()
    if abs(now - int(seconds)) > SIGNATURE_MAX_AGE_SECONDS:
        return None
    # Authenticate the exact text signed by the gateway. Only the rate-limit
    # identity is normalized, so equivalent IPv6 spellings share one bucket.
    expected = sign_client_ip(secret, raw_ip, int(seconds)).partition(".")[2]
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
    try:
        proxies = parse_trusted_proxy_networks(getattr(settings, "trusted_proxy_ips", ()) or ())
    except ValueError:
        # Hosted startup rejects this configuration. Remain fail-closed for
        # directly constructed settings in tests/development too.
        return ClientAddress(peer, False, "peer")
    if proxies and _in_networks(peer, proxies):
        forwarded = str(headers.get("x-forwarded-for", "") or "").split(",")
        for candidate in reversed(forwarded):
            ip = _parse_ip(candidate)
            if not ip:
                # Never skip a malformed hop and trust an earlier supplied IP.
                return ClientAddress(peer, False, "peer")
            if not _in_networks(ip, proxies):
                return ClientAddress(ip, True, "trusted_proxy")
    return ClientAddress(peer, False, "peer")
