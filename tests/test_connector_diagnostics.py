"""35A Windows-compatible runtime checks; no real credentials or Tally required."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from siftentry_app import tally_connector_runtime as rt


def config(tmp_path):
    return rt.ConnectorConfig(cloud_url="https://app.siftentry.com", workspace_id="test",
                              token="test-token", config_path=str(tmp_path / "connector_config.json"))


@pytest.mark.parametrize("code", [301, 302, 307, 401, 403, 404, 422, 429, 500, 502])
def test_http_failures_are_visible_and_do_not_echo_secrets(tmp_path, monkeypatch, code):
    def request(*args, **kwargs):
        assert kwargs["allow_redirects"] is False
        return SimpleNamespace(status_code=code, text="sensitive upstream text")
    monkeypatch.setattr(rt.requests, "post", request)
    result = rt.claim_cloud_jobs(config(tmp_path))
    assert not result["success"] and result["jobs"] == []
    assert f"HTTP {code}" in result["message"]
    assert "sensitive" not in result["message"] and "test-token" not in result["message"]


@pytest.mark.parametrize("token", ["bad—token", "bad\ntoken", "bad token", "", "x" * 513])
def test_bad_token_never_reaches_network(tmp_path, monkeypatch, token):
    monkeypatch.setattr(rt.requests, "post", lambda *a, **k: pytest.fail("must not send malformed credentials"))
    result = rt.claim_cloud_jobs(replace(config(tmp_path), token=token))
    assert not result["success"]
    assert "ASCII" in result["message"]


@pytest.mark.parametrize("url", ["https://app.siftentry.com/app", "http://example.com", "https://user:secret@example.com", "https://example.com?token=x"])
def test_invalid_base_url_is_not_silently_rewritten(tmp_path, url):
    assert rt.connection_config_error(replace(config(tmp_path), cloud_url=url))


def test_diagnostics_is_read_only_and_does_not_touch_outbox(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    outbox = rt.default_outbox_path(cfg.config_path)
    outbox.write_text("corrupt evidence must survive", encoding="utf-8")
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        if url.startswith(cfg.cloud_url):
            assert url.endswith("/diagnostics")
            return SimpleNamespace(status_code=200, json=lambda: {"success": True, "company_name": "NEEL"})
        assert "Authorization" not in kwargs["headers"]
        assert b"<TALLYREQUEST>Export</TALLYREQUEST>" in kwargs["data"]
        return SimpleNamespace(status_code=200, content=b'<ENVELOPE><BODY><DATA><COLLECTION><COMPANY NAME="NEEL"/></COLLECTION></DATA></BODY></ENVELOPE>')
    monkeypatch.setattr(rt.requests, "post", request)
    result = rt.test_connection(cfg)
    assert result["success"] and result["connected_to_siftentry"]
    assert result["checks"]["company"]["state"] == "passed"
    assert result["checks"]["masters"]["state"] == "not_verified"
    assert result["claimed"] == 0 and len(calls) == 2
    assert outbox.read_text() == "corrupt evidence must survive"


def test_wrong_company_is_not_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "cloud_request", lambda *a: {"success": True, "company_name": "NEEL"})
    monkeypatch.setattr(rt, "read_tally_companies", lambda *a: {"success": True, "companies": ["OTHER"], "message": "OK"})
    result = rt.test_connection(config(tmp_path))
    assert not result["success"] and result["connected_to_siftentry"]
    assert result["checks"]["company"]["state"] == "failed"


@pytest.mark.parametrize("body", [b"<html>OK</html>", b"not xml", b"<ENVELOPE><STATUS>0</STATUS></ENVELOPE>"])
def test_non_tally_http_200_is_not_success(monkeypatch, body):
    monkeypatch.setattr(rt.requests, "post", lambda *a, **k: SimpleNamespace(status_code=200, content=body))
    assert not rt.read_tally_companies("http://localhost:9000")["success"]


def test_network_exception_does_not_expose_header(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise ValueError("invalid Authorization: Bearer test-token")
    monkeypatch.setattr(rt.requests, "post", fail)
    assert "test-token" not in json.dumps(rt.claim_cloud_jobs(config(tmp_path)))


def test_uncertain_tally_result_is_never_acknowledged_as_failure_or_reposted(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "prepare_execution", lambda *_: {})
    cfg = config(tmp_path)
    monkeypatch.setattr(rt, "test_tally_connection", lambda _: {"success": True})
    monkeypatch.setattr(rt, "claim_cloud_jobs", lambda _: {"success": True, "jobs": [
        {"invoice_id": "i1", "posting_id": "p1", "xml": "<ENVELOPE/>"}]})
    monkeypatch.setattr(rt, "post_xml_to_tally", lambda *a, **k: {
        "invoice_id": "i1", "success": False, "outcome_uncertain": True})
    monkeypatch.setattr(rt, "submit_cloud_results", lambda *a: pytest.fail("uncertain is not a terminal failure"))
    assert "uncertain" in rt.poll_once(cfg)["message"]
    monkeypatch.setattr(rt, "claim_cloud_jobs", lambda _: pytest.fail("must block new claims"))
    monkeypatch.setattr(rt, "send_cloud_heartbeat", lambda *a, **k: {"success": True})
    assert "uncertain" in rt.poll_once(cfg)["message"]
    assert rt.read_outbox(rt.default_outbox_path(cfg.config_path))[0]["outcome_uncertain"]


def test_tally_timeout_reports_uncertain(monkeypatch):
    def fail(*a, **k):
        raise TimeoutError("response lost")
    monkeypatch.setattr(rt.requests, "post", fail)
    assert rt.post_xml_to_tally("http://localhost:9000", "i1", "<ENVELOPE/>")["outcome_uncertain"]


def test_pending_results_block_changing_saved_identity(tmp_path):
    cfg = config(tmp_path)
    rt.save_config(cfg)
    rt.append_outbox(rt.default_outbox_path(cfg.config_path), [{
        "posting_id": "p1", "success": True, "connector_cloud_url": cfg.cloud_url,
        "connector_workspace_id": cfg.workspace_id}])
    with pytest.raises(rt.OutboxUnreadable):
        rt.save_config(replace(cfg, cloud_url="https://different.example"))
    assert rt.load_config(rt.Path(cfg.config_path)).cloud_url == cfg.cloud_url


def test_partial_tally_creation_with_error_is_uncertain(monkeypatch):
    monkeypatch.setattr(rt.requests, "post", lambda *a, **k: SimpleNamespace(status_code=200,
        text="<RESPONSE><CREATED>1</CREATED><ERRORS>1</ERRORS><LINEERROR>partial</LINEERROR></RESPONSE>"))
    result = rt.post_xml_to_tally("http://localhost:9000", "i1", "<ENVELOPE/>")
    assert not result["success"] and result["outcome_uncertain"]
