from siftentry_app.tally_integration import (
    build_tally_xml,
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
    assert "exact ledger name" in message


def test_tally_item_invoice_preflight_accepts_profile_mapped_stock_and_igst():
    payload = sample_legacy_payload()
    row = payload["INVOICE"]["LINE ITEMS"]["ROWS"][0]
    row["TALLY_STOCK_ITEM"] = "PTA SWEEP"
    issues = _tally_preflight_issues(
        payload,
        {
            "company": "NEEL ENTERPRISE",
            "voucher_type": "Purchase",
            "posting_mode": "Item Invoice",
            "purchase_ledger": "PURCHASES A/C",
            "stock_item_name": "",
            "stock_item_hsn": "",
            "stock_item_uom": "KGS",
            "tax_ledger": "",
            "tax_mode": "gst_igst",
            "tax_settings": {"igst_ledger": "IGST A/C"},
            "tcs_ledger": "TCS",
            "round_off_ledger": "ROUND OFF",
        },
    )

    assert all(issue["code"] != "tally_stock_item_missing" for issue in issues)
    assert all(issue["code"] != "tally_igst_ledger_missing" for issue in issues)


def test_tally_cgst_sgst_mode_requires_separate_ledgers():
    payload = sample_legacy_payload()
    issues = _tally_preflight_issues(
        payload,
        {
            "company": "NEEL ENTERPRISE",
            "voucher_type": "Purchase",
            "posting_mode": "Accounting Voucher",
            "purchase_ledger": "PURCHASES A/C",
            "tax_ledger": "GST A/C",
            "tax_mode": "gst_cgst_sgst",
            "tax_settings": {},
            "tcs_ledger": "TCS",
            "round_off_ledger": "ROUND OFF",
        },
    )

    assert any(issue["code"] == "tally_cgst_ledger_missing" for issue in issues)
    assert any(issue["code"] == "tally_sgst_ledger_missing" for issue in issues)


def _golden_settings(posting_mode: str) -> dict:
    """Shared profile settings so the three golden tests differ only by mode."""
    return {
        "company": "NEEL ENTERPRISE",
        "voucher_type": "Purchase",
        "posting_mode": posting_mode,
        "purchase_ledger": "PURCHASES A/C",
        "stock_item_name": "PTA SWEEP",
        "stock_item_hsn": "1234",
        "stock_item_uom": "KGS",
        "tax_ledger": "GST A/C",
        "tcs_ledger": "",
        "round_off_ledger": "ROUND OFF",
        "godown_name": "",
    }


def test_golden_xml_item_invoice_mode_uses_invoice_view_and_inventory_entries():
    xml = build_tally_xml(sample_legacy_payload(), settings=_golden_settings("Item Invoice"))

    assert '<ISINVOICE>Yes</ISINVOICE>' in xml
    assert 'OBJVIEW="Invoice Voucher View"' in xml
    assert "<VCHENTRYMODE>Item Invoice</VCHENTRYMODE>" in xml
    # Item invoice mode carries stock as top-level inventory entries.
    assert "<ALLINVENTORYENTRIES.LIST>" in xml
    assert "<ACCOUNTINGALLOCATIONS.LIST>" in xml
    # It must never emit the voucher-mode nested allocation element.
    assert "<INVENTORYALLOCATIONS.LIST>" not in xml
    assert "<STOCKITEMNAME>PTA SWEEP</STOCKITEMNAME>" in xml


def test_golden_xml_accounting_voucher_mode_has_no_inventory_at_all():
    xml = build_tally_xml(
        sample_legacy_payload(),
        settings=_golden_settings("Accounting Voucher"),
    )

    assert "<ISINVOICE>No</ISINVOICE>" in xml
    assert 'OBJVIEW="Accounting Voucher View"' in xml
    # Ledger-only posting: no stock movement of any kind.
    assert "<ALLINVENTORYENTRIES.LIST>" not in xml
    assert "<INVENTORYALLOCATIONS.LIST>" not in xml
    assert "<STOCKITEMNAME>" not in xml
    assert "<LEDGERNAME>PURCHASES A/C</LEDGERNAME>" in xml


def test_golden_xml_voucher_with_stock_allocation_nests_inventory_in_ledger():
    xml = build_tally_xml(
        sample_legacy_payload(),
        settings=_golden_settings("Voucher with stock allocation"),
    )

    # Looks like an accounting voucher on screen...
    assert "<ISINVOICE>No</ISINVOICE>" in xml
    assert 'OBJVIEW="Accounting Voucher View"' in xml
    assert "<VCHENTRYMODE>Voucher</VCHENTRYMODE>" in xml
    # ...but stock still updates through allocations nested in the ledger entry.
    assert "<INVENTORYALLOCATIONS.LIST>" in xml
    assert "<STOCKITEMNAME>PTA SWEEP</STOCKITEMNAME>" in xml
    # It must not use the item-invoice shape.
    assert "<ALLINVENTORYENTRIES.LIST>" not in xml

    # The allocation must sit inside the purchase ledger entry, not beside it.
    purchase_block = xml.split("<LEDGERNAME>PURCHASES A/C</LEDGERNAME>")[1].split(
        "</ALLLEDGERENTRIES.LIST>"
    )[0]
    assert "<INVENTORYALLOCATIONS.LIST>" in purchase_block


def test_voucher_with_stock_allocation_balances_party_purchase_and_tax():
    xml = build_tally_xml(
        sample_legacy_payload(),
        settings=_golden_settings("Voucher with stock allocation"),
    )

    assert "<LEDGERNAME>Example Supplier</LEDGERNAME>" in xml
    assert "<AMOUNT>118.00</AMOUNT>" in xml
    assert "<AMOUNT>-100.00</AMOUNT>" in xml
    assert "<AMOUNT>-18.00</AMOUNT>" in xml


def test_voucher_with_stock_allocation_groups_lines_by_purchase_ledger():
    payload = sample_legacy_payload()
    rows = payload["INVOICE"]["LINE ITEMS"]["ROWS"]
    rows[0]["TALLY_LEDGER"] = "RAW MATERIAL A/C"
    rows.append(
        {
            "DESCRIPTION": "Consumable",
            "QUANTITY": 2,
            "UOM": "EA",
            "UNIT PRICE": 50,
            "EXTENDED AMOUNT": 100,
            "TAX AMOUNT": 0,
            "AMOUNT": 100,
            "TALLY_LEDGER": "CONSUMABLES A/C",
            "TALLY_STOCK_ITEM": "BRUSH",
        }
    )

    xml = build_tally_xml(payload, settings=_golden_settings("Voucher with stock allocation"))

    assert "<LEDGERNAME>RAW MATERIAL A/C</LEDGERNAME>" in xml
    assert "<LEDGERNAME>CONSUMABLES A/C</LEDGERNAME>" in xml
    # Each ledger block holds only its own stock allocations.
    raw_block = xml.split("<LEDGERNAME>RAW MATERIAL A/C</LEDGERNAME>")[1].split(
        "</ALLLEDGERENTRIES.LIST>"
    )[0]
    assert "<STOCKITEMNAME>PTA SWEEP</STOCKITEMNAME>" in raw_block
    assert "<STOCKITEMNAME>BRUSH</STOCKITEMNAME>" not in raw_block


def test_voucher_with_stock_allocation_preflight_requires_stock_item():
    payload = sample_legacy_payload()
    settings = _golden_settings("Voucher with stock allocation")
    settings["stock_item_name"] = ""
    issues = _tally_preflight_issues(payload, settings)

    assert any(issue["code"] == "tally_stock_item_missing" for issue in issues)


def test_voucher_with_stock_allocation_emits_godown_when_configured():
    settings = _golden_settings("Voucher with stock allocation")
    settings["godown_name"] = "MAIN LOCATION"
    xml = build_tally_xml(sample_legacy_payload(), settings=settings)

    assert "<GODOWNNAME>MAIN LOCATION</GODOWNNAME>" in xml
    assert "<BATCHALLOCATIONS.LIST>" in xml
