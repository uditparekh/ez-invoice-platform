"""Tests for Step 10 workspace features: organization settings,
the learn_vendor_memory gate on invoice PATCH, and batch posting."""

from pathlib import Path

from .test_api import (
    authorization,
    bootstrap,
    import_sample_invoice,
    make_client,
    organization_id,
)


def test_organization_settings_roundtrip(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        # Defaults before anything is saved.
        response = client.get(
            f"/api/v1/organizations/{org_id}/settings", headers=headers
        )
        assert response.status_code == 200
        defaults = response.json()
        assert defaults["default_currency"] == "USD"
        assert defaults["data_retention"] == "review_window"
        assert defaults["notifications"]["approvals"] is True

        # Save workspace defaults.
        response = client.put(
            f"/api/v1/organizations/{org_id}/settings",
            json={
                "default_currency": "inr",
                "default_country": "IN",
                "primary_accounting_system": "tally",
                "data_retention": "retain_90",
                "notifications": {
                    "approvals": True,
                    "failures": False,
                    "digest": True,
                },
            },
            headers=headers,
        )
        assert response.status_code == 200
        saved = response.json()
        assert saved["default_currency"] == "INR"  # normalized to uppercase
        assert saved["data_retention"] == "retain_90"

        # Persisted across reads.
        response = client.get(
            f"/api/v1/organizations/{org_id}/settings", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["default_country"] == "IN"
        assert response.json()["notifications"]["digest"] is True

        # Unauthenticated access is rejected.
        assert (
            client.get(f"/api/v1/organizations/{org_id}/settings").status_code == 401
        )


def test_patch_invoice_learn_vendor_memory_gate(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        def learning_count() -> int:
            response = client.get(
                f"/api/v1/organizations/{org_id}/corrections/learning?limit=200",
                headers=headers,
            )
            assert response.status_code == 200
            return len(response.json())

        baseline = learning_count()

        # Patch WITH learning disabled: correction must NOT be recorded.
        invoice_a = import_sample_invoice(client, tokens, org_id, "gate-a.pdf")
        response = client.patch(
            f"/api/v1/invoices/{invoice_a['id']}",
            json={"invoice_number": "GATE-OFF-001", "learn_vendor_memory": False},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["invoice_number"] == "GATE-OFF-001"
        assert learning_count() == baseline

        # Patch WITH learning on (default): correction IS recorded.
        invoice_b = import_sample_invoice(client, tokens, org_id, "gate-b.pdf")
        response = client.patch(
            f"/api/v1/invoices/{invoice_b['id']}",
            json={"invoice_number": "GATE-ON-001"},
            headers=headers,
        )
        assert response.status_code == 200
        assert learning_count() > baseline

        # The flag itself must never leak into the invoice payload.
        assert "learn_vendor_memory" not in response.json()


def test_batch_post_ready_invoices(tmp_path: Path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org_id = organization_id(tokens)
        headers = authorization(tokens)

        # Two invoices moved to approved, one left extracted.
        approved_ids = []
        for name in ("batch-1.pdf", "batch-2.pdf"):
            invoice = import_sample_invoice(client, tokens, org_id, name)
            assert (
                client.post(
                    f"/api/v1/invoices/{invoice['id']}/validate", headers=headers
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/v1/invoices/{invoice['id']}/approve", headers=headers
                ).status_code
                == 200
            )
            approved_ids.append(invoice["id"])
        import_sample_invoice(client, tokens, org_id, "not-ready.pdf")

        response = client.post(
            f"/api/v1/organizations/{org_id}/invoices/post-ready",
            json={"dry_run": True},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["attempted"] == 2
        assert payload["succeeded"] + payload["failed"] == len(payload["results"])
        result_invoice_ids = {result["invoice_id"] for result in payload["results"]}
        skipped_invoice_ids = {item["invoice_id"] for item in payload["skipped"]}
        assert result_invoice_ids | skipped_invoice_ids == set(approved_ids)

        # Every attempt (or skip) is per-invoice — one failure never blocks the rest.
        assert len(payload["results"]) + len(payload["skipped"]) == 2
