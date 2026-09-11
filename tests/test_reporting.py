import csv
import io
from urllib.parse import urlencode
from datetime import datetime, timezone

import pytest

from siftentry_app.backend.models import InvoiceCreate, InvoiceStatus, OrganizationCreate, PostingTarget
from .test_api import make_client, bootstrap, authorization, organization_id


def invoice(repo, org, number, currency="USD", total=10.1, at="2026-09-10T12:00:00+00:00"):
    result = repo.create_invoice(InvoiceCreate(organization_id=org, invoice_number=number,
        source_file=f"{number}.pdf", currency=currency, total=total, subtotal=total,
        supplier={"name": "Acme"}))
    with repo._connect() as connection:
        connection.execute("UPDATE invoices SET created_at = ? WHERE id = ?", (at, result.id))
    return result


def test_analytics_full_dataset_currencies_boundaries_and_current_queue(tmp_path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org = organization_id(tokens)
        repo = client.app.state.repository
        for i in range(121):
            invoice(repo, org, str(i))
        invoice(repo, org, "inr", "INR", 900)
        invoice(repo, org, "prior", total=10000, at="2026-08-31T23:59:59+00:00")
        invoice(repo, org, "next", total=10000, at="2026-09-11T00:00:00+00:00")
        other = repo.create_organization(OrganizationCreate(name="Other client"))
        invoice(repo, other.id, "private", total=999999)
        response = client.get(f"/api/v1/organizations/{org}/analytics?start=2026-09-01&end=2026-09-10", headers=authorization(tokens))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['received_count'] == 122
        currencies = {row['currency']: row for row in data['currencies']}
        assert currencies['USD']['total'] == '1222.1'
        assert currencies['INR']['total'] == '900.0'
        assert sum(data['queue'].values()) == 124
        assert data['daily'] == [{'date': '2026-09-10', 'count': 122}]
        assert data['supplier_count'] == 1


def test_history_persisted_events_pagination_snapshot_and_export(tmp_path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org = organization_id(tokens)
        repo = client.app.state.repository
        item = invoice(repo, org, '=HYPERLINK("bad")')
        at = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        for _ in range(65):
            repo.record_audit_event(org, "invoice.approved", {"actor_id": tokens['user']['id'], "status": "approved", "connector_token": "SECRET-DO-NOT-EXPORT"}, item.id, at)
        query = "start=2026-09-10&end=2026-09-10&category=invoice&search=approved&limit=7"
        url = f"/api/v1/organizations/{org}/events?{query}"
        first = client.get(url, headers=authorization(tokens)).json()
        assert first['total'] == 65
        assert first['items'][0]['actor'] == 'Owner'
        assert 'SECRET-DO-NOT-EXPORT' not in str(first)
        repo.record_audit_event(org, "invoice.approved", {}, item.id, datetime(2099, 1, 1, tzinfo=timezone.utc))
        ids = [row['id'] for row in first['items']]
        cursor = first['next_cursor']
        while cursor:
            page = client.get(url + "&" + urlencode({"cursor": cursor, "snapshot": first['snapshot']}), headers=authorization(tokens)).json()
            ids.extend(row['id'] for row in page['items'])
            cursor = page['next_cursor']
        assert len(ids) == len(set(ids)) == 65
        export = client.get(f"/api/v1/organizations/{org}/events/export?{query}&" + urlencode({"snapshot": first['snapshot']}), headers=authorization(tokens))
        assert export.status_code == 200
        records = list(csv.reader(io.StringIO(export.text)))
        assert len(records) == 66
        assert {row[0] for row in records[1:]} == set(ids)
        assert records[1][4].startswith("'=HYPERLINK")
        assert 'SECRET-DO-NOT-EXPORT' not in export.text


@pytest.mark.parametrize("path", ["analytics", "events", "events/export"])
def test_reporting_auth_and_tenant_boundaries(tmp_path, path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        other = client.app.state.repository.create_organization(OrganizationCreate(name="Other client"))
        url = f"/api/v1/organizations/{other.id}/{path}"
        assert client.get(url).status_code == 401
        assert client.get(url, headers=authorization(tokens)).status_code == 404


@pytest.mark.parametrize("query", ["start=2026-09-11&end=2026-09-10", "start=bad", "cursor=not-valid", "snapshot=not-valid", "category=anything", "limit=0"])
def test_history_invalid_queries_fail_cleanly(tmp_path, query):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        response = client.get(f"/api/v1/organizations/{organization_id(tokens)}/events?{query}", headers=authorization(tokens))
        assert response.status_code == 422, response.text


def test_posting_metrics_exclude_dry_runs_and_use_completion_date(tmp_path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org = organization_id(tokens)
        repo = client.app.state.repository
        item = invoice(repo, org, "old", at="2026-08-01T00:00:00+00:00")
        for success, dry_run in [(True, False), (False, False), (True, True)]:
            posting = repo.create_posting(item.id, PostingTarget.TALLY, success, dry_run, "test")
            with repo._connect() as connection:
                connection.execute("UPDATE posting_attempts SET updated_at = ? WHERE id = ?", ("2026-09-10T00:00:00+00:00", posting.id))
        data = client.get(f"/api/v1/organizations/{org}/analytics?start=2026-09-10&end=2026-09-10", headers=authorization(tokens)).json()
        assert data['received_count'] == 0
        assert data['posting_outcomes'] == {'succeeded': 1, 'failed': 1}


def test_approval_actor_and_no_synthetic_history(tmp_path):
    with make_client(tmp_path) as client:
        tokens = bootstrap(client)
        org = organization_id(tokens)
        repo = client.app.state.repository
        item = invoice(repo, org, "approval")
        repo.set_status(item.id, InvoiceStatus.VALIDATED)
        response = client.post(f"/api/v1/invoices/{item.id}/approve", headers=authorization(tokens))
        assert response.status_code == 200
        # A state-only change does not manufacture a new history event.
        with repo._connect() as connection:
            connection.execute("UPDATE invoices SET status = 'posted' WHERE id = ?", (item.id,))
        data = client.get(f"/api/v1/organizations/{org}/events", headers=authorization(tokens)).json()
        types = [row['event_type'] for row in data['items']]
        assert 'invoice.approved' in types
        assert 'invoice.posted' not in types
        approved = next(row for row in data['items'] if row['event_type'] == 'invoice.approved')
        assert approved['actor'] == 'Owner'
