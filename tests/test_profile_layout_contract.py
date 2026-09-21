"""Storage/XML contracts the profile reorganization must not change."""
import pytest

from siftentry_app.backend.adapters import _profiled_legacy_payload, _tally_settings_from_profile
from siftentry_app.backend.domain import legacy_payload_to_invoice
from siftentry_app.backend.models import ClientProfile, ClientProfileSettings, Invoice
from siftentry_app.backend.repository import utc_now
from siftentry_app.tally_integration import build_tally_xml
from tests.test_domain import sample_legacy_payload
from tests.test_api import make_client, bootstrap, organization_id, authorization, _tally_profile_body


def test_hidden_inventory_defaults_do_not_change_accounting_voucher_xml():
    now = utc_now()
    invoice = Invoice(id="layout-invoice", created_at=now, updated_at=now,
        **legacy_payload_to_invoice(sample_legacy_payload(), organization_id="org", source_file="sample.pdf").model_dump())
    profile = ClientProfile(id="profile", organization_id="org", name="Profile", created_at=now, updated_at=now,
        accounting_system="tally", settings=ClientProfileSettings(company_name="TEST", purchase_ledger="Purchases",
        tax_ledger="Tax", posting_mode="accounting_voucher"))
    def xml():
        return build_tally_xml(_profiled_legacy_payload(invoice, profile), settings=_tally_settings_from_profile(profile))
    before = xml()
    profile.settings.stock_item_name = "INACTIVE STOCK"
    profile.settings.stock_item_hsn = "9999"
    profile.settings.stock_item_uom = "INACTIVE UNIT"
    profile.settings.godown_name = "INACTIVE GODOWN"
    assert xml() == before
    assert "INACTIVE" not in before


@pytest.mark.parametrize("mode", ["accounting_voucher", "item_invoice", "voucher_with_inventory"])
def test_profile_edit_round_trip_preserves_posting_settings_and_token(tmp_path, mode):
    with make_client(tmp_path) as client:
        owner = bootstrap(client)
        url = f"/api/v1/organizations/{organization_id(owner)}/client-profiles"
        headers = authorization(owner)
        body = _tally_profile_body("Layout preservation", True)
        body["settings"].update(posting_mode=mode, godown_name="Main Stores", stock_item_name="Material",
            stock_item_uom="KGS", stock_item_hsn="1234", metadata={"preserve_me": {"value": 42}})
        body["settings"]["training_profile"] = {"onboarding_status": "active", "exception_examples": "Keep this note"}
        created = client.post(url, json=body, headers=headers)
        assert created.status_code == 201
        public = created.json()
        saved_before = client.app.state.repository.get_client_profile(public["id"])
        # The editor sends the redacted settings back without revealing/replacing the secret.
        result = client.patch(url + "/" + public["id"], headers=headers,
            json={"description": "Layout-only edit", "settings": public["settings"]})
        assert result.status_code == 200
        saved_after = client.app.state.repository.get_client_profile(public["id"])
        assert saved_after.settings.model_dump() == saved_before.settings.model_dump()
        assert saved_after.settings.connection_settings["connector_token"] == "connector-secret"
        assert saved_after.settings.training_profile.onboarding_status == "active"
