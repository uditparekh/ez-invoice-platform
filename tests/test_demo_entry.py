"""Prepared demo entry must stay fast without caching authorization decisions."""
from unittest.mock import patch

from siftentry_app.backend.demo_seed import _prepared_demo_user, ensure_public_demo_workspace
from siftentry_app.backend.models import OrganizationRole
from .test_api import make_client, authorization


def test_prepared_demo_uses_one_connection_and_never_reseeds(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post('/api/v1/auth/demo')
        assert 'demo_prepare;dur=' in response.headers['server-timing']
        assert 'demo_session;dur=' in response.headers['server-timing']
        tokens = response.json()
        repo = client.app.state.repository
        with patch.object(repo, '_connect', wraps=repo._connect) as connect, \
             patch.object(repo, 'list_invoices', side_effect=AssertionError('full invoice graph loaded')), \
             patch.object(repo, 'create_invoice', side_effect=AssertionError('reseeded')):
            user = ensure_public_demo_workspace(repo)
            assert user.id == tokens['user']['id']
            assert connect.call_count == 1


def test_fast_path_rechecks_role_and_repairs_missing_samples(tmp_path):
    with make_client(tmp_path) as client:
        tokens = client.post('/api/v1/auth/demo').json()
        repo = client.app.state.repository
        user_id = tokens['user']['id']
        org = tokens['user']['memberships'][0]['organization_id']
        repo.create_membership(user_id, org, OrganizationRole.ADMIN)
        assert _prepared_demo_user(repo) is None
        ensure_public_demo_workspace(repo)
        assert repo.get_membership(user_id, org).role == OrganizationRole.VIEWER
        assert _prepared_demo_user(repo) is not None
        with repo._connect() as db:
            db.execute("DELETE FROM posting_attempts WHERE organization_id = ?", (org,))
        assert _prepared_demo_user(repo) is None
        ensure_public_demo_workspace(repo)
        assert _prepared_demo_user(repo) is not None


def test_demo_period_uses_real_receipt_dates_without_moving_records(tmp_path):
    with make_client(tmp_path) as client:
        tokens = client.post('/api/v1/auth/demo').json()
        repo = client.app.state.repository
        org = tokens['user']['memberships'][0]['organization_id']
        with repo._connect() as db:
            db.execute("UPDATE invoices SET created_at = ? WHERE organization_id = ?",
                       ('2026-01-10T12:00:00+00:00', org))
        # Re-entry must not rewrite historical samples to artificially fill a month.
        client.post('/api/v1/auth/demo')
        response = client.get(f'/api/v1/organizations/{org}/analytics?start=2026-09-01&end=2026-09-30',
                              headers=authorization(tokens))
        data = response.json()
        assert response.status_code == 200
        assert data['received_count'] == 0
        assert data['available_range'] == {'start': '2026-01-10', 'end': '2026-01-10'}
        assert data['queue']['posted'] == 2
        assert data['posting_outcomes'] == {}
