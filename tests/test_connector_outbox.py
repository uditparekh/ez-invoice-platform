"""pkg34: the connector's durable acknowledgement outbox.

Reproduces the QA finding: Tally posting succeeds, the acknowledgement to
SiftEntry fails, and a later poll must retry ONLY the acknowledgement — never
re-post the voucher — even across a process restart.
"""
from pathlib import Path

from siftentry_app import tally_connector_runtime as rt


def _config(tmp_path: Path) -> rt.ConnectorConfig:
    return rt.ConnectorConfig(
        cloud_url="https://app.siftentry.com",
        workspace_id="neel-prod",
        token="connector-secret",
        tally_url="http://localhost:9000",
        dry_run=False,
        config_path=str(tmp_path / "connector_config.json"),
    )


def test_tally_success_with_failed_ack_is_retried_without_reposting(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    calls = {"tally_posts": 0, "submits": 0, "claims": 0}
    ack_should_fail = {"value": True}

    monkeypatch.setattr(rt, "test_tally_connection", lambda url: {"success": True, "message": "ok"})
    monkeypatch.setattr(rt, "send_cloud_heartbeat", lambda config, tally_detected=True: {"success": True})

    def fake_claim(config):
        calls["claims"] += 1
        if calls["claims"] == 1:
            return {"success": True, "jobs": [{"posting_id": "p1", "invoice_id": "inv1", "xml": "<ENVELOPE/>"}]}
        return {"success": True, "jobs": []}

    def fake_post(tally_url, invoice_id, xml, dry_run=False):
        calls["tally_posts"] += 1
        return {"invoice_id": invoice_id, "success": True, "message": "Posted to Tally"}

    def fake_submit(config, results):
        calls["submits"] += 1
        if ack_should_fail["value"]:
            return {"success": False, "message": "Cloud result submit failed: network"}
        return {"success": True, "accepted": len(results)}

    monkeypatch.setattr(rt, "claim_cloud_jobs", fake_claim)
    monkeypatch.setattr(rt, "post_xml_to_tally", fake_post)
    monkeypatch.setattr(rt, "submit_cloud_results", fake_submit)

    # Poll 1: Tally succeeds, ack fails. Result must be on disk and reported honestly.
    first = rt.poll_once(config)
    assert calls["tally_posts"] == 1
    assert first["submitted"] == 0
    assert first["awaiting_ack"] == 1
    assert "not confirmed" in first["message"]
    outbox = rt.default_outbox_path(config.config_path)
    assert rt.read_outbox(outbox) and rt.read_outbox(outbox)[0]["posting_id"] == "p1"

    # "Restart": a fresh config object, same on-disk state. Ack still failing.
    second = rt.poll_once(_config(tmp_path))
    assert calls["submits"] == 2          # acknowledgement retried
    assert calls["tally_posts"] == 1      # voucher NOT re-posted
    assert second["awaiting_ack"] == 1
    assert second["claimed"] == 0         # no new work while unacknowledged

    # Network back: the outbox drains and normal polling resumes.
    ack_should_fail["value"] = False
    third = rt.poll_once(_config(tmp_path))
    assert calls["submits"] == 3
    assert calls["tally_posts"] == 1
    assert rt.read_outbox(outbox) == []
    assert third["awaiting_ack"] == 0
    assert third["success"] is True


def test_outbox_dedupes_by_posting_id(tmp_path: Path):
    path = tmp_path / "results_outbox.json"
    rt.append_outbox(path, [{"posting_id": "p1", "success": True}])
    rt.append_outbox(path, [{"posting_id": "p1", "success": True}, {"posting_id": "p2", "success": False}])
    ids = [item["posting_id"] for item in rt.read_outbox(path)]
    assert ids == ["p1", "p2"]


# --- Regression cases from the pkg34 shipping verification (10 Sep) ---------

def _stub_cloud(monkeypatch, rt, claims, submit_ok=True, tally_ok=True, counters=None):
    counters = counters if counters is not None else {}
    counters.setdefault("submits", 0)
    counters.setdefault("tally_posts", 0)
    monkeypatch.setattr(rt, "test_tally_connection",
                        lambda url: {"success": tally_ok, "message": "ok" if tally_ok else "down"})
    monkeypatch.setattr(rt, "send_cloud_heartbeat", lambda config, tally_detected=None: {"success": True})
    it = iter(claims)
    monkeypatch.setattr(rt, "claim_cloud_jobs",
                        lambda config: next(it, {"success": True, "jobs": []}))

    def submit(config, results):
        counters["submits"] += 1
        return {"success": True, "accepted": len(results)} if submit_ok else {"success": False, "message": "net"}
    monkeypatch.setattr(rt, "submit_cloud_results", submit)
    return counters


def test_interrupted_batch_keeps_earlier_results_on_disk(tmp_path: Path, monkeypatch):
    """Job 1 posts to Tally; the process dies during job 2. Job 1's result must survive."""
    config = _config(tmp_path)
    counters = _stub_cloud(monkeypatch, rt, claims=[{
        "success": True,
        "jobs": [
            {"posting_id": "p1", "invoice_id": "inv1", "xml": "<ENVELOPE/>"},
            {"posting_id": "p2", "invoice_id": "inv2", "xml": "<ENVELOPE/>"},
        ],
    }])

    def post(tally_url, invoice_id, xml, dry_run=False):
        counters["tally_posts"] += 1
        if invoice_id == "inv2":
            raise KeyboardInterrupt("process killed mid-batch")
        return {"invoice_id": invoice_id, "success": True, "message": "Posted to Tally"}
    monkeypatch.setattr(rt, "post_xml_to_tally", post)

    try:
        rt.poll_once(config)
    except KeyboardInterrupt:
        pass

    outbox = rt.read_outbox(rt.default_outbox_path(config.config_path))
    assert [item["posting_id"] for item in outbox] == ["p1"]
    assert counters["submits"] == 0  # never reached the ack step; that's fine — it's on disk

    # Restart with the cloud working: job 1 is acknowledged, not re-posted.
    counters["tally_posts"] = 0
    monkeypatch.setattr(rt, "post_xml_to_tally",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not re-post")))
    rt.poll_once(_config(tmp_path))
    assert counters["submits"] == 1
    assert rt.read_outbox(rt.default_outbox_path(config.config_path)) == []


def test_pending_ack_is_sent_even_when_tally_is_closed(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    path = rt.default_outbox_path(config.config_path)
    rt.append_outbox(path, [{"posting_id": "p1", "invoice_id": "inv1", "success": True}])
    counters = _stub_cloud(monkeypatch, rt, claims=[], tally_ok=False)

    status = rt.poll_once(config)
    assert counters["submits"] == 1          # acknowledged despite Tally being down
    assert rt.read_outbox(path) == []
    assert status["tally_detected"] is False  # and the Tally problem is still reported


def test_unreadable_outbox_blocks_new_claims_visibly(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    path = rt.default_outbox_path(config.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    counters = _stub_cloud(monkeypatch, rt, claims=[{"success": True, "jobs": [
        {"posting_id": "p9", "invoice_id": "inv9", "xml": "<ENVELOPE/>"}]}])
    monkeypatch.setattr(rt, "post_xml_to_tally",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not claim")))

    status = rt.poll_once(config)
    assert status["success"] is False
    assert "unreadable" in status["message"]
    assert status["claimed"] == 0
    assert counters["submits"] == 0
    assert path.read_text(encoding="utf-8") == "{not json"  # evidence preserved
