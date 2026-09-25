"""Acceptance tests for isolated authentication limits and credential-free bundles.

Contracts under test:
- demo abuse cannot block ordinary login or refresh;
- spoofed client-address headers never bypass limits;
- a gateway-signed address, or a trusted proxy's forwarded header, is the only
  way to receive a per-address budget;
- exports contain no credential material and export/import does not disconnect
  an existing connector, while a new workspace requires fresh connector setup.
"""
import json
import time
from types import SimpleNamespace

import pytest

from siftentry_app.backend import auth_limits
from siftentry_app.backend.client_ip import (
    CLIENT_IP_HEADER,
    CLIENT_SIGNATURE_HEADER,
    resolve_client_address,
    sign_client_ip,
)
from siftentry_app.backend.connector_secrets import token_matches
from tests.test_api import (
    _tally_profile_body,
    authorization,
    bootstrap,
    make_client,
    organization_id,
)
from tests.test_infra_settings import _production_settings

GATEWAY_SECRET = "gateway-shared-secret-for-tests-0123456789abcdef"


def _signed(ip: str, secret: str = GATEWAY_SECRET, timestamp=None) -> dict:
    return {
        CLIENT_IP_HEADER: ip,
        CLIENT_SIGNATURE_HEADER: sign_client_ip(secret, ip, timestamp),
    }


def _login(client, index: int, headers=None):
    return client.post(
        "/api/v1/auth/login",
        json={"email": f"nobody-{index}@example.com", "password": "not-the-password-123"},
        headers=headers or {},
    )


def test_demo_abuse_cannot_block_login_or_refresh(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "demo", (2, 3))
    with make_client(tmp_path) as client:
        bootstrap(client)
        statuses = [client.post("/api/v1/auth/demo").status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]
        # Demo is exhausted for this ingress. Ordinary authentication is untouched.
        owner = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        assert owner.status_code == 200
        refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": owner.json()["refresh_token"]})
        assert refreshed.status_code == 200
        assert _login(client, 1).status_code == 401  # wrong password, not throttled


def test_demo_has_a_global_ceiling_that_spares_login(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.GLOBAL_LIMITS, "demo", 2)
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        bootstrap(client)
        # Three distinct verified addresses: the third hits the global demo ceiling.
        statuses = [
            client.post("/api/v1/auth/demo", headers=_signed(f"203.0.113.{n}")).status_code
            for n in (1, 2, 3)
        ]
        assert statuses == [200, 200, 429]
        owner = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
            headers=_signed("203.0.113.3"),
        )
        assert owner.status_code == 200


def test_spoofed_headers_share_one_ingress_budget(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "login", (5, 3))
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        spoofed = [
            {"X-Forwarded-For": "198.51.100.1"},
            {"X-Forwarded-For": "198.51.100.2, 10.0.0.1", "X-Real-IP": "198.51.100.2"},
            {CLIENT_IP_HEADER: "198.51.100.3"},  # attested address without a signature
            _signed("198.51.100.4", secret="wrong-secret-wrong-secret-wrong-secret-1"),
            _signed("198.51.100.5", timestamp=1_000_000),  # stale signature
        ]
        statuses = [_login(client, index, headers).status_code for index, headers in enumerate(spoofed)]
        # Every spoof lands in the same shared bucket: 3 allowed, then 429.
        assert statuses == [401, 401, 401, 429, 429]


def test_gateway_signed_addresses_get_their_own_budget(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "login", (2, 3))
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        # Two verified addresses, two attempts each: none throttled.
        statuses = [
            _login(client, index, _signed(ip)).status_code
            for index, ip in enumerate(["203.0.113.10", "203.0.113.11", "203.0.113.10", "203.0.113.11"])
        ]
        assert statuses == [401, 401, 401, 401]
        # A third attempt from one address trips only that address.
        assert _login(client, 5, _signed("203.0.113.10")).status_code == 429
        assert _login(client, 6, _signed("203.0.113.11")).status_code == 429
        assert _login(client, 7, _signed("203.0.113.12")).status_code == 401
        # Unsigned traffic through the same ingress is unaffected by their budgets.
        assert _login(client, 8).status_code == 401
        with client.app.state.repository._connect() as connection:
            keys = [row["bucket_key"] for row in connection.execute("SELECT bucket_key FROM auth_rate_buckets").fetchall()]
        assert keys and all(len(key) == 64 and "203.0.113" not in key for key in keys)


def test_gateway_signature_is_ignored_without_a_configured_secret(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "login", (5, 2))
    with make_client(tmp_path) as client:
        statuses = [
            _login(client, index, _signed(f"203.0.113.{index}")).status_code for index in range(3)
        ]
        assert statuses == [401, 401, 429]


def test_malformed_attestations_never_crash_login_or_escape_limits(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "login", (5, 3))
    seconds = str(int(time.time())).encode("ascii")
    signatures = [seconds + b".\xff", b"9" * 4500 + b".bad", seconds + b".bad", b"invalid"]
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        statuses = [
            _login(client, index, [
                (CLIENT_IP_HEADER.encode(), b"203.0.113.1"),
                (CLIENT_SIGNATURE_HEADER.encode(), signature),
            ]).status_code
            for index, signature in enumerate(signatures)
        ]
        assert statuses == [401, 401, 401, 429]


@pytest.mark.parametrize("ip, expected", [
    ("2001:db8::1", "2001:db8::1"),
    ("2001:0db8:0:0:0:0:0:1", "2001:db8::1"),
    ("2001:DB8::1", "2001:db8::1"),
    ("::ffff:203.0.113.1", "203.0.113.1"),
])
def test_gateway_verifies_original_ip_text_then_normalizes_identity(ip, expected):
    settings = SimpleNamespace(gateway_shared_secret=GATEWAY_SECRET, trusted_proxy_ips=())
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"), headers=_signed(ip))
    address = resolve_client_address(request, settings)
    assert (address.ip, address.verified, address.source) == (expected, True, "gateway")


def test_equivalent_ipv6_addresses_cannot_multiply_login_budgets(tmp_path, monkeypatch):
    monkeypatch.setitem(auth_limits.ADDRESS_LIMITS, "login", (2, 20))
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        statuses = [
            _login(client, index, _signed(ip)).status_code
            for index, ip in enumerate(["2001:db8::1", "2001:0db8:0:0:0:0:0:1", "2001:DB8::1"])
        ]
        assert statuses == [401, 401, 429]


@pytest.mark.parametrize("ip, age", [
    ("203.0.113.1", -301), ("203.0.113.1", 301),
    ("fe80::1%eth0", 0), ("not-an-ip", 0),
])
def test_invalid_or_expired_gateway_identity_falls_back_to_peer(ip, age):
    now = 1_800_000_000
    settings = SimpleNamespace(gateway_shared_secret=GATEWAY_SECRET, trusted_proxy_ips=())
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"), headers=_signed(ip, timestamp=now + age))
    address = resolve_client_address(request, settings, now=now)
    assert (address.ip, address.verified, address.source) == ("10.0.0.5", False, "peer")


@pytest.mark.parametrize(
    "peer, forwarded, expected",
    [
        ("10.0.0.5", "203.0.113.7, 10.0.0.9", ("203.0.113.7", True, "trusted_proxy")),
        ("10.0.0.5", "198.51.100.1, 203.0.113.7", ("203.0.113.7", True, "trusted_proxy")),
        ("10.0.0.5", "not-an-ip", ("10.0.0.5", False, "peer")),
        ("10.0.0.5", "203.0.113.7, not-an-ip", ("10.0.0.5", False, "peer")),
        ("192.0.2.44", "203.0.113.7", ("192.0.2.44", False, "peer")),  # peer is not a trusted proxy
    ],
)
def test_forwarded_headers_are_honoured_only_from_trusted_proxies(peer, forwarded, expected):
    settings = SimpleNamespace(gateway_shared_secret="", trusted_proxy_ips=("10.0.0.0/8",))
    request = SimpleNamespace(client=SimpleNamespace(host=peer), headers={"x-forwarded-for": forwarded})
    address = resolve_client_address(request, settings)
    assert (address.ip, address.verified, address.source) == expected


def test_gateway_attestation_outranks_forwarded_headers_and_requires_a_strong_secret():
    settings = SimpleNamespace(gateway_shared_secret=GATEWAY_SECRET, trusted_proxy_ips=("10.0.0.0/8",))
    headers = {"x-forwarded-for": "198.51.100.1", **_signed("203.0.113.7")}
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"), headers=headers)
    assert resolve_client_address(request, settings).source == "gateway"
    weak = SimpleNamespace(gateway_shared_secret="short", trusted_proxy_ips=())
    weak_headers = _signed("203.0.113.7", secret="short")
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.1"), headers=weak_headers)
    assert resolve_client_address(request, weak).source == "peer"


def test_hosted_modes_require_verified_client_addresses(tmp_path):
    def address_problems(**overrides):
        return [
            problem
            for problem in _production_settings(tmp_path, **overrides).production_readiness_problems()
            if "client address" in problem
        ]

    assert address_problems(gateway_shared_secret="")
    assert address_problems(gateway_shared_secret="short")
    assert not address_problems(gateway_shared_secret="", trusted_proxy_ips=("10.0.0.0/8",))
    assert not address_problems()
    with pytest.raises(RuntimeError, match="GATEWAY_SHARED_SECRET"):
        _production_settings(tmp_path, gateway_shared_secret="").validate_startup()


def test_deployment_health_reports_client_address_trust(tmp_path):
    with make_client(tmp_path, gateway_shared_secret=GATEWAY_SECRET) as client:
        checks = client.get("/health/deployment").json()["checks"]
        assert checks["client_address_trust"] == "gateway"
        assert checks["auth_limits_per_verified_address"] is True
    with make_client(tmp_path / "peer") as client:
        checks = client.get("/health/deployment").json()["checks"]
        assert checks["client_address_trust"] == "peer_only"


@pytest.mark.parametrize("proxies", [
    ("invalid-proxy",), ("10.0.0.0/8", "invalid-proxy"),
    ("0.0.0.0/0",), ("::/0",), ("10.0.0.5/8",),
])
@pytest.mark.parametrize("secret", ["", GATEWAY_SECRET])
def test_invalid_proxy_configuration_cannot_pass_hosted_readiness(tmp_path, proxies, secret):
    settings = _production_settings(tmp_path, gateway_shared_secret=secret, trusted_proxy_ips=proxies)
    assert settings.has_verified_client_addresses is False
    assert settings.client_address_trust == "peer_only"
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_IPS"):
        settings.validate_startup()


@pytest.mark.parametrize("proxy", ["10.0.0.5", "10.0.0.0/8", "2001:db8::/32"])
def test_valid_proxy_configuration_passes_hosted_startup(tmp_path, proxy):
    settings = _production_settings(
        tmp_path, gateway_shared_secret="", trusted_proxy_ips=(proxy,),
        storage_backend="supabase", supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-only", supabase_storage_bucket="test-only",
    )
    settings.validate_startup()
    assert settings.client_address_trust == "trusted_proxy"


def _diagnostics(client, token: str):
    return client.post(
        "/api/v1/connectors/tally/diagnostics",
        json={"workspace_id": "neel-prod"},
        headers={"Authorization": "Bearer " + token},
    )


def test_exports_carry_no_credentials_and_import_preserves_connectors(tmp_path):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        org, headers = organization_id(owner), authorization(owner)
        body = _tally_profile_body("Neel Tally", True)
        plaintext = body["settings"]["connection_settings"]["connector_token"]
        created = client.post(f"/api/v1/organizations/{org}/client-profiles", headers=headers, json=body)
        assert created.status_code == 201
        profile_id = created.json()["id"]
        repo = client.app.state.repository
        stored = repo.get_client_profile(profile_id).settings.connection_settings["connector_token"]
        assert token_matches(plaintext, stored)

        exported = client.get(f"/api/v1/organizations/{org}/learning/export", headers=headers)
        assert exported.status_code == 200
        bundle = exported.json()
        assert plaintext not in exported.text and stored not in exported.text
        assert "connector_token" not in exported.text
        connection = bundle["client_profiles"][0]["settings"]["connection_settings"]
        assert connection["workspace_id"] == "neel-prod" and connection["connector_enabled"] is True

        # Restoring into the same workspace keeps the running connector connected.
        restored = client.post(f"/api/v1/organizations/{org}/learning/import", headers=headers, json=bundle)
        assert restored.status_code == 200
        assert restored.json()["profiles_updated"] == 1
        assert any("preserved" in note for note in restored.json()["notes"])
        assert repo.get_client_profile(profile_id).settings.connection_settings["connector_token"] == stored
        assert _diagnostics(client, plaintext).status_code == 200

        # A bundle that somehow carries a credential cannot plant it on import.
        tampered = json.loads(json.dumps(bundle))
        tampered["client_profiles"][0]["settings"]["connection_settings"]["connector_token"] = "attacker-supplied-token-0123456789abcdef"
        assert client.post(f"/api/v1/organizations/{org}/learning/import", headers=headers, json=tampered).status_code == 200
        assert repo.get_client_profile(profile_id).settings.connection_settings["connector_token"] == stored
        assert _diagnostics(client, "attacker-supplied-token-0123456789abcdef").status_code == 401

        # Restoring into a new workspace requires fresh connector setup.
        second = client.post(
            "/api/v1/organizations",
            json={"name": "Second Practice", "legal_names": [], "default_currency": "INR"},
            headers=headers,
        )
        assert second.status_code in (200, 201)
        second_id = second.json()["id"]
        imported = client.post(f"/api/v1/organizations/{second_id}/learning/import", headers=headers, json=tampered)
        assert imported.status_code == 200 and imported.json()["profiles_created"] == 1
        assert any("fresh connector setup" in note for note in imported.json()["notes"])
        new_profile = repo.list_client_profiles(second_id)[0]
        new_connection = new_profile.settings.connection_settings
        assert not new_connection.get("connector_token")
        assert new_connection["connector_enabled"] is False
        assert new_connection["workspace_id"] == "neel-prod"
