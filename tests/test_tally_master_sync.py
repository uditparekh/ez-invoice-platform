"""Read-only connector exports: no Windows/Tally installation required."""

from xml.etree import ElementTree as ET

import pytest

from siftentry_app import tally_master_sync as sync
from siftentry_app import tally_connector_runtime as rt


def xml(kind, name="Example", guid="company-guid"):
    tag = sync.COLLECTIONS[kind][1]
    return f'<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION><{tag} NAME="{name}"><GUID>{guid}</GUID><PARENT>Primary</PARENT></{tag}></COLLECTION></DATA></BODY></ENVELOPE>'.encode()


@pytest.mark.parametrize("kind", sync.COLLECTIONS)
def test_only_whitelisted_export_requests(kind):
    request = sync.export_request(kind, "A & B <Company>")
    root = ET.fromstring(request)
    assert root.findtext("./HEADER/TALLYREQUEST") == "Export"
    assert root.findtext(".//SVCURRENTCOMPANY") == "A & B <Company>"
    assert b"IMPORT" not in request.upper() and b"BALANCE" not in request.upper()
    assert sync.parse_export(xml(kind), kind)[0]["name"] == "Example"


@pytest.mark.parametrize(
    "body",
    [
        b"garbage",
        b"<html>OK</html>",
        b"<ENVELOPE/>",
        b'<!DOCTYPE test [<!ENTITY x "bad">]><ENVELOPE/>',
        xml("ledgers").replace(b"<STATUS>1", b"<STATUS>0"),
        xml("units"),
        xml("ledgers").replace(b"</DATA>", b"<LINEERROR>denied</LINEERROR></DATA>"),
        xml("ledgers").replace(
            b"</COLLECTION>", b'<LEDGER NAME="Example"/></COLLECTION>'
        ),
    ],
)
def test_invalid_or_partial_exports_fail_closed(body):
    with pytest.raises(sync.MasterSyncError):
        sync.parse_export(body, "ledgers")


def test_empty_collection_is_valid_only_with_success_header():
    content = b"<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION/></DATA></BODY></ENVELOPE>"
    assert sync.parse_export(content, "godowns") == []
    with pytest.raises(sync.MasterSyncError):
        sync.parse_export(content.replace(b"<STATUS>1</STATUS>", b""), "godowns")


def test_identity_checked_before_and_after_and_never_falls_back(monkeypatch):
    calls = []

    def read(url, kind, company=""):
        calls.append((kind, company))
        return [{"name": "NEEL", "guid": "stable"}] if kind == "companies" else []

    monkeypatch.setattr(sync, "read_collection", read)
    snapshot = sync.read_snapshot("http://localhost:9000", "NEEL")
    assert snapshot["company"] == {"name": "NEEL", "guid": "stable"}
    assert calls == [("companies", "")] + [
        (kind, "NEEL") for kind in sync.COLLECTIONS if kind != "companies"
    ] + [("companies", "")]
    with pytest.raises(sync.MasterSyncError):
        sync.read_snapshot("http://localhost:9000", "OTHER")


def test_company_switch_and_failed_collection_never_upload(monkeypatch):
    count = 0

    def read(url, kind, company=""):
        nonlocal count
        if kind == "companies":
            count += 1
            return [{"name": "NEEL", "guid": str(count)}]
        return []

    monkeypatch.setattr(sync, "read_collection", read)
    with pytest.raises(sync.MasterSyncError, match="identity changed"):
        sync.read_snapshot("http://localhost:9000", "NEEL")


def test_sync_never_touches_outbox_claims_or_posts(tmp_path, monkeypatch):
    cfg = rt.ConnectorConfig(
        cloud_url="https://app.siftentry.com",
        workspace_id="test",
        token="test-token",
        config_path=str(tmp_path / "config.json"),
    )
    outbox = rt.default_outbox_path(cfg.config_path)
    outbox.write_text("corrupt evidence", encoding="utf-8")
    calls = []

    def cloud(config, path, payload):
        calls.append(path)
        assert "jobs" not in path and "heartbeat" not in path
        if path.endswith("begin"):
            return {"success": True, "ticket": "x" * 64, "company_name": "NEEL"}
        assert payload["company"]["name"] == "NEEL"
        return {"success": True, "message": "saved"}

    monkeypatch.setattr(rt, "cloud_request", cloud)
    monkeypatch.setattr(
        rt,
        "read_snapshot",
        lambda *a: {"company": {"name": "NEEL", "guid": "stable"}, "masters": {}},
    )
    assert rt.sync_masters(cfg)["success"]
    assert len(calls) == 2 and outbox.read_text() == "corrupt evidence"

    def fail(*args):
        raise sync.MasterSyncError("Incomplete export")

    monkeypatch.setattr(rt, "read_snapshot", fail)
    calls.clear()
    assert not rt.sync_masters(cfg)["success"] and len(calls) == 1


def test_stream_size_limit_redirects_and_credentials(monkeypatch):
    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def iter_content(self, size):
            yield b"x" * (sync.MAX_XML_BYTES + 1)

    def post(url, **kwargs):
        assert kwargs["stream"] and kwargs["allow_redirects"] is False
        assert "Authorization" not in kwargs["headers"]
        return Response()

    monkeypatch.setattr(sync.requests, "post", post)
    with pytest.raises(sync.MasterSyncError, match="size limit"):
        sync.read_collection("http://localhost:9000", "ledgers", "NEEL")
