from ez_invoice_app.gst_invoice_parser import _seller_name, looks_like_gst_invoice


def test_seller_name_skips_irn_acknowledgement_metadata():
    lines = [
        "TAX INVOICE",
        "IRN",
        ": ec6cbea56178dfcc95690958a2133b87e9ebac4a7ac-bbc0886d9661fdcecd7c8",
        "Ack No.",
        ": 122526510797333",
        "Ack Date",
        ": 2-May-25",
        "e-Invoice",
        "CRESCENT BEARING CORPORATION",
        "H.O: 39, Nagdevi Cross Lane, Gr. Floor",
    ]

    assert _seller_name("\n".join(lines), lines) == "CRESCENT BEARING CORPORATION"


def test_gst_detector_accepts_einvoice_without_explicit_tax_labels():
    text = """
    TAX INVOICE
    IRN
    Ack No.
    e-Invoice
    CRESCENT BEARING CORPORATION
    GSTIN/UIN: 27AAAFC0330M1ZS
    Sl
    Description of Goods
    HSN/SAC
    Amount
    """

    assert looks_like_gst_invoice(text)
