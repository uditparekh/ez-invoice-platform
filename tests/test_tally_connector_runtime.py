from __future__ import annotations

from ez_invoice_app import tally_connector_runtime as runtime
from ez_invoice_app.tally_connector_runtime import ConnectorConfig


def test_parse_tally_response_extracts_success_counts():
    parsed = runtime.parse_tally_response(
        """
        <RESPONSE>
          <CREATED>1</CREATED>
          <ALTERED>0</ALTERED>
          <ERRORS>0</ERRORS>
          <VCHNUMBER>42</VCHNUMBER>
        </RESPONSE>
        """
    )

    assert parsed["created"] == 1
    assert parsed["altered"] == 0
    assert parsed["errors"] == 0
    assert parsed["voucher_number"] == "42"


def test_post_xml_to_tally_rejects_invalid_xml():
    result = runtime.post_xml_to_tally(
        "http://localhost:9000",
        invoice_id="INV-1",
        xml="<ENVELOPE>",
    )

    assert result["success"] is False
    assert "Invalid XML" in result["message"]


def test_post_xml_to_tally_accepts_dry_run_without_requests():
    result = runtime.post_xml_to_tally(
        "http://localhost:9000",
        invoice_id="INV-1",
        xml="<ENVELOPE></ENVELOPE>",
        dry_run=True,
    )

    assert result["success"] is True
    assert result["message"] == "Dry run accepted"


def test_poll_once_does_not_claim_jobs_when_tally_is_offline(monkeypatch):
    claimed = {"called": False}

    def fake_tally_connection(tally_url: str):
        return {"success": False, "message": "TallyPrime is not running"}

    def fake_claim(config: ConnectorConfig):
        claimed["called"] = True
        return {"success": True, "jobs": []}

    monkeypatch.setattr(runtime, "test_tally_connection", fake_tally_connection)
    monkeypatch.setattr(runtime, "claim_cloud_jobs", fake_claim)

    result = runtime.poll_once(
        ConnectorConfig(
            cloud_url="https://app.siftentry.com",
            workspace_id="neel-prod",
            token="secret",
            tally_url="http://localhost:9000",
        )
    )

    assert result["success"] is False
    assert result["tally_detected"] is False
    assert result["claimed"] == 0
    assert claimed["called"] is False


def test_poll_once_posts_claimed_jobs_and_submits_results(monkeypatch):
    submitted = {"payload": None}

    def fake_tally_connection(tally_url: str):
        return {"success": True, "message": "TallyPrime Server is Running"}

    def fake_claim(config: ConnectorConfig):
        return {
            "success": True,
            "jobs": [
                {
                    "posting_id": "posting-1",
                    "invoice_id": "invoice-1",
                    "invoice_number": "INV-1",
                    "xml": "<ENVELOPE></ENVELOPE>",
                    "dry_run": True,
                }
            ],
        }

    def fake_submit(config: ConnectorConfig, results):
        submitted["payload"] = results
        return {"success": True, "accepted": len(results)}

    monkeypatch.setattr(runtime, "test_tally_connection", fake_tally_connection)
    monkeypatch.setattr(runtime, "claim_cloud_jobs", fake_claim)
    monkeypatch.setattr(runtime, "submit_cloud_results", fake_submit)

    result = runtime.poll_once(
        ConnectorConfig(
            cloud_url="https://app.siftentry.com",
            workspace_id="neel-prod",
            token="secret",
            tally_url="http://localhost:9000",
        )
    )

    assert result["success"] is True
    assert result["connected_to_siftentry"] is True
    assert result["tally_detected"] is True
    assert result["claimed"] == 1
    assert result["submitted"] == 1
    assert result["last_posted_invoice"] == "INV-1"
    assert submitted["payload"][0]["posting_id"] == "posting-1"
