from pathlib import Path

from siftentry_app.backend.settings import ApiSettings


def _production_settings(tmp_path: Path, **overrides) -> ApiSettings:
    data = {
        "database_url": "postgresql://user:pass@db.example.com:5432/siftentry",
        "database_path": tmp_path / "fallback.db",
        "upload_directory": tmp_path / "uploads",
        "max_upload_bytes": 25 * 1024 * 1024,
        "cors_origins": ("https://app.siftentry.com",),
        "app_base_url": "https://app.siftentry.com",
        "api_public_base_url": "https://api.siftentry.com",
        "jwt_secret": "x" * 64,
        "allow_dev_bootstrap": False,
        "environment": "production",
        "email_provider": "smtp",
        "email_from": "SiftEntry <no-reply@siftentry.com>",
        "smtp_host": "smtp.example.com",
        "smtp_username": "apikey",
        "smtp_password": "secret",
    }
    data.update(overrides)
    return ApiSettings(**data)


def test_postgres_database_url_is_supported(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(
        "EZ_API_DATABASE_URL",
        "postgresql://user:pass@db.example.com:5432/siftentry",
    )
    monkeypatch.setenv("EZ_API_DATABASE_PATH", str(tmp_path / "fallback.db"))
    monkeypatch.setenv("EZ_API_ENVIRONMENT", "pilot")

    settings = ApiSettings.from_environment()

    assert settings.database_path == tmp_path / "fallback.db"
    assert settings.is_sqlite is False


def test_production_readiness_rejects_local_storage(tmp_path: Path):
    settings = _production_settings(tmp_path, storage_backend="local")

    assert "use hosted object storage for retained PDFs" in (
        settings.production_readiness_problems()
    )


def test_production_readiness_accepts_supabase_storage(tmp_path: Path):
    settings = _production_settings(
        tmp_path,
        storage_backend="supabase",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-secret",
        supabase_storage_bucket="siftentry-pdf-review",
    )

    assert not [
        problem
        for problem in settings.production_readiness_problems()
        if "storage" in problem.lower() or "supabase" in problem.lower()
    ]
