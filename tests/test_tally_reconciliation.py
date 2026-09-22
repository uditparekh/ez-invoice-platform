"""Recovery never imports, even for empty, partial or conflicting lookups."""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest
from siftentry_app import tally_reconciliation as rec
from siftentry_app import tally_connector_runtime as rt

REFERENCE = "11111111-2222-5333-8444-555555555555"
COMPANY = {"name": "NEEL & CO", "guid": "company-guid"}


def plan_and_voucher():
    voucher = ET.fromstring(
        f"""<VOUCHER REMOTEID="{REFERENCE}">
      <DATE>20260921</DATE><VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
      <PARTYLEDGERNAME>Supplier</PARTYLEDGERNAME><REFERENCE>INV-1</REFERENCE>
      <NARRATION>Purchase [SiftEntry:{REFERENCE}]</NARRATION>
      <ALLLEDGERENTRIES.LIST><LEDGERNAME>Supplier</LEDGERNAME><AMOUNT>100.00</AMOUNT></ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST><LEDGERNAME>Purchases</LEDGERNAME><AMOUNT>-100.00</AMOUNT></ALLLEDGERENTRIES.LIST>
    </VOUCHER>"""
    )
    plan = {
        "company": COMPANY["name"],
        "posting_reference": REFERENCE,
        "xml": "<ENVELOPE>" + ET.tostring(voucher, encoding="unicode") + "</ENVELOPE>",
    }
    for tag, value in (
        ("MASTERID", "42"),
        ("ISCANCELLED", "No"),
        ("ISOPTIONAL", "No"),
        ("VOUCHERNUMBER", "1"),
    ):
        ET.SubElement(voucher, tag).text = value
    return plan, voucher


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def iter_content(self, _):
        yield self.data


def fake_lookup(monkeypatch, vouchers):
    monkeypatch.setattr(rec, "company_identity", lambda *_: deepcopy(COMPANY))
    content = b"<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>"
    content += b"".join(ET.tostring(v) for v in vouchers)
    content += b"</COLLECTION></DATA></BODY></ENVELOPE>"

    def post(url, **kwargs):
        root = ET.fromstring(kwargs["data"])
        assert root.findtext("./HEADER/TALLYREQUEST") == "Export"
        assert root.findtext(".//SVCURRENTCOMPANY") == COMPANY["name"]
        assert kwargs["allow_redirects"] is False
        return Response(content)

    monkeypatch.setattr(rec.requests, "post", post)


def test_unique_exact_voucher_matches_without_import(monkeypatch):
    plan, voucher = plan_and_voucher()
    fake_lookup(monkeypatch, [voucher])
    proof = rec.lookup_voucher("http://localhost:9000", plan, COMPANY)
    assert proof["external_id"] == "42"
    assert (
        rec.verify_voucher(plan, proof["voucher_xml"])["voucher_sha256"]
        == proof["voucher_sha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "amount",
        "ledger",
        "reference",
        "marker",
        "date",
        "cancelled",
        "optional",
        "missing_state",
        "extra_entry",
        "duplicate_field",
    ],
)
def test_modified_or_ambiguous_voucher_is_held(mutation):
    plan, voucher = plan_and_voucher()
    if mutation == "amount":
        voucher.find(".//AMOUNT").text = "101"
    if mutation == "ledger":
        voucher.find(".//LEDGERNAME").text = "Another supplier"
    if mutation == "reference":
        voucher.set("REMOTEID", "other")
    if mutation == "marker":
        voucher.find("NARRATION").text = "Missing marker"
    if mutation == "date":
        voucher.find("DATE").text = "20260922"
    if mutation == "cancelled":
        voucher.find("ISCANCELLED").text = "Yes"
    if mutation == "optional":
        voucher.find("ISOPTIONAL").text = "Yes"
    if mutation == "missing_state":
        voucher.remove(voucher.find("ISCANCELLED"))
    if mutation == "extra_entry":
        voucher.append(deepcopy(voucher.find("ALLLEDGERENTRIES.LIST")))
    if mutation == "duplicate_field":
        ET.SubElement(voucher, "DATE").text = "20260921"
    with pytest.raises(rec.ReconciliationError):
        rec.verify_voucher(plan, ET.tostring(voucher, encoding="unicode"))


@pytest.mark.parametrize("count", [0, 2])
def test_absent_or_multiple_matches_never_authorize_retry(monkeypatch, count):
    plan, voucher = plan_and_voucher()
    fake_lookup(monkeypatch, [voucher] * count)
    with pytest.raises(rec.ReconciliationError, match="NOT permission to retry"):
        rec.lookup_voucher("http://localhost:9000", plan, COMPANY)


def test_wrong_company_stops_before_query(monkeypatch):
    plan, _ = plan_and_voucher()
    monkeypatch.setattr(
        rec, "company_identity", lambda *_: {**COMPANY, "guid": "different"}
    )
    monkeypatch.setattr(
        rec.requests, "post", lambda *a, **k: pytest.fail("wrong company queried")
    )
    with pytest.raises(rec.ReconciliationError, match="identity changed"):
        rec.lookup_voucher("http://localhost:9000", plan, COMPANY)


@pytest.mark.parametrize(
    "field,value",
    [
        ("GODOWNNAME", "Other stores"),
        ("ACTUALQTY", "3 EA"),
        ("ACTUALQTY", "2 BOX"),
        ("LEDGERNAME", "Other purchases"),
    ],
)
def test_inventory_and_accounting_allocations_must_match(field, value):
    plan, actual = plan_and_voucher()
    inventory = ET.fromstring(
        """<ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Material</STOCKITEMNAME>
      <ACTUALQTY>2 EA</ACTUALQTY><BILLEDQTY>2 EA</BILLEDQTY><RATE>50.00/EA</RATE><AMOUNT>-100</AMOUNT>
      <BATCHALLOCATIONS.LIST><GODOWNNAME>Main stores</GODOWNNAME><AMOUNT>-100</AMOUNT></BATCHALLOCATIONS.LIST>
      <ACCOUNTINGALLOCATIONS.LIST><LEDGERNAME>Purchases</LEDGERNAME><AMOUNT>-100</AMOUNT></ACCOUNTINGALLOCATIONS.LIST>
    </ALLINVENTORYENTRIES.LIST>"""
    )
    expected = ET.fromstring(plan["xml"])
    expected.find(".//VOUCHER").append(deepcopy(inventory))
    plan["xml"] = ET.tostring(expected, encoding="unicode")
    actual.append(inventory)
    rec.verify_voucher(plan, ET.tostring(actual, encoding="unicode"))
    inventory.find(".//" + field).text = value
    with pytest.raises(rec.ReconciliationError, match="differs"):
        rec.verify_voucher(plan, ET.tostring(actual, encoding="unicode"))


@pytest.mark.parametrize(
    "data",
    [
        b"<html/>",
        b"<ENVELOPE><HEADER><STATUS>0</STATUS></HEADER></ENVELOPE>",
        b"<!DOCTYPE foo><ENVELOPE/>",
        b"x" * (rec.MAX_BYTES + 1),
    ],
)
def test_partial_unsafe_and_oversized_results_are_held(monkeypatch, data):
    plan, _ = plan_and_voucher()
    monkeypatch.setattr(rec, "company_identity", lambda *_: COMPANY)
    monkeypatch.setattr(rec.requests, "post", lambda *a, **k: Response(data))
    with pytest.raises(rec.ReconciliationError):
        rec.lookup_voucher("http://localhost:9000", plan, COMPANY)


def test_journal_exists_before_tally_and_survives_immediate_crash(
    tmp_path, monkeypatch
):
    cfg = rt.ConnectorConfig(
        cloud_url="https://app.siftentry.com",
        token="test-secret",
        config_path=str(tmp_path / "connector_config.json"),
    )
    monkeypatch.setattr(rt, "test_tally_connection", lambda _: {"success": True})
    monkeypatch.setattr(
        rt,
        "claim_cloud_jobs",
        lambda _: {
            "success": True,
            "jobs": [{"posting_id": "p1", "invoice_id": "i1", "xml": "<ENVELOPE/>"}],
        },
    )
    monkeypatch.setattr(rt, "prepare_execution", lambda *_: {"company": COMPANY})

    def crash(*a, **k):
        assert rt.read_outbox(rt.default_outbox_path(cfg.config_path))[0][
            "outcome_uncertain"
        ]
        raise KeyboardInterrupt()

    monkeypatch.setattr(rt, "post_xml_to_tally", crash)
    with pytest.raises(KeyboardInterrupt):
        rt.poll_once(cfg)
    monkeypatch.setattr(rt, "send_cloud_heartbeat", lambda *a, **k: {"success": True})
    monkeypatch.setattr(
        rt, "claim_cloud_jobs", lambda _: pytest.fail("must not claim again")
    )
    assert rt.poll_once(cfg)["claimed"] == 0


def test_recovery_can_find_server_reservation_without_local_outbox(
    tmp_path, monkeypatch
):
    plan, voucher = plan_and_voucher()
    cfg = rt.ConnectorConfig(
        cloud_url="https://app.siftentry.com",
        token="test-secret",
        config_path=str(tmp_path / "connector_config.json"),
    )
    paths = []

    def cloud(config, path, body):
        paths.append(path)
        if path.endswith("/recovery"):
            return {
                "success": True,
                "jobs": [
                    {
                        "posting_id": "p1",
                        "invoice_id": "i1",
                        "posting_plan": plan,
                        "execution": {"company": COMPANY},
                    }
                ],
            }
        assert path.endswith("/reconcile") and body["voucher_xml"]
        return {"success": True, "state": "matched"}

    monkeypatch.setattr(rt, "cloud_request", cloud)
    monkeypatch.setattr(
        rt,
        "lookup_voucher",
        lambda *_: {
            "voucher_xml": ET.tostring(voucher, encoding="unicode"),
            "company": COMPANY,
        },
    )
    monkeypatch.setattr(
        rt, "post_xml_to_tally", lambda *a, **k: pytest.fail("recovery cannot import")
    )
    assert rt.reconcile_postings(cfg)["matched"] == 1
    assert len(paths) == 2


def test_lost_reconciliation_ack_is_recoverable_without_second_lookup(
    tmp_path, monkeypatch
):
    cfg = rt.ConnectorConfig(
        cloud_url="https://app.siftentry.com",
        token="test-secret",
        config_path=str(tmp_path / "connector_config.json"),
    )
    path = rt.default_outbox_path(cfg.config_path)
    rt.append_outbox(
        path, [{"posting_id": "p1", "success": False, "outcome_uncertain": True}]
    )
    monkeypatch.setattr(
        rt,
        "cloud_request",
        lambda *_: {
            "success": True,
            "jobs": [{"posting_id": "p1", "reconciled": True}],
        },
    )
    monkeypatch.setattr(
        rt, "lookup_voucher", lambda *_: pytest.fail("already verified on server")
    )
    assert rt.reconcile_postings(cfg)["success"]
    assert rt.read_outbox(path) == []
