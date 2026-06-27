from ez_invoice_app.tally_integration import (
    _friendly_tally_message,
    _tally_preflight_issues,
)

from .test_domain import sample_legacy_payload


def test_tally_item_invoice_preflight_requires_tax_ledger_for_taxed_bill():
    issues = _tally_preflight_issues(
        sample_legacy_payload(),
        {
            "company": "NEEL ENTERPRISE",
            "voucher_type": "Purchase",
            "posting_mode": "Item Invoice",
            "purchase_ledger": "PURCHASES A/C",
            "stock_item_name": "PTA SWEEP",
            "stock_item_hsn": "1234",
            "stock_item_uom": "KGS",
            "tax_ledger": "",
            "tcs_ledger": "TCS",
            "round_off_ledger": "ROUND OFF",
        },
    )

    assert any(issue["code"] == "tally_tax_ledger_missing" for issue in issues)
    assert all(issue["code"] != "tally_purchase_ledger_missing" for issue in issues)


def test_tally_error_message_explains_missing_ledgers():
    message = _friendly_tally_message("Ledger 'Materials' does not exist!")

    assert "Materials" in message
    assert "client profile" in message
    assert "exact Tally ledger names" in message
