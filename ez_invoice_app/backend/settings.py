"""Environment-based settings for the SiftEntry API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JWT_SECRET = "ez-invoice-local-development-secret-change-me"


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _database_path_from_url(database_url: str, fallback: Path) -> Path:
    """Translate a local SQLite URL into the path used by the current repository."""

    if not database_url:
        return fallback
    parsed = urlparse(database_url)
    if parsed.scheme in {"", "file"}:
        return Path(unquote(database_url)).expanduser()
    if parsed.scheme != "sqlite":
        # The current repository is SQLite-backed. Keep this explicit so a pilot
        # cannot silently start against an unsupported production database.
        raise RuntimeError(
            "Only sqlite database URLs are supported by the current repository. "
            "Use EZ_API_DATABASE_URL=sqlite:////absolute/path/siftentry.db for "
            "the deployable pilot, then migrate to the planned Postgres adapter."
        )
    if parsed.netloc not in {"", "localhost"}:
        raise RuntimeError("SQLite database URLs must point at a local filesystem path.")
    return Path(unquote(parsed.path)).expanduser()


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    database_path: Path
    upload_directory: Path
    max_upload_bytes: int
    cors_origins: tuple[str, ...]
    app_base_url: str = "http://127.0.0.1:3000"
    api_public_base_url: str = "http://127.0.0.1:8000"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_issuer: str = "siftentry-api"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    allow_dev_bootstrap: bool = True
    environment: str = "development"
    email_provider: str = "log"
    email_from: str = "SiftEntry <no-reply@siftentry.local>"
    email_reply_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        data_dir = APP_ROOT / "data"
        environment = os.environ.get("EZ_API_ENVIRONMENT", "development").strip().lower()
        jwt_secret = os.environ.get("EZ_API_JWT_SECRET", DEFAULT_JWT_SECRET)
        database_url = os.environ.get(
            "EZ_API_DATABASE_URL",
            f"sqlite:///{data_dir / 'ez_invoice.db'}",
        ).strip()
        fallback_database_path = Path(
            os.environ.get("EZ_API_DATABASE_PATH", data_dir / "ez_invoice.db")
        ).expanduser()
        origins = _split_csv(
            os.environ.get(
                "EZ_API_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            )
        )
        settings = cls(
            database_url=database_url,
            database_path=_database_path_from_url(database_url, fallback_database_path),
            upload_directory=Path(
                os.environ.get("EZ_API_UPLOAD_DIRECTORY", data_dir / "uploads")
            ).expanduser(),
            max_upload_bytes=int(
                os.environ.get("EZ_API_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))
            ),
            cors_origins=origins,
            app_base_url=os.environ.get("EZ_APP_BASE_URL", "http://127.0.0.1:3000")
            .strip()
            .rstrip("/"),
            api_public_base_url=os.environ.get(
                "EZ_API_PUBLIC_BASE_URL",
                "http://127.0.0.1:8000",
            )
            .strip()
            .rstrip("/"),
            jwt_secret=jwt_secret,
            jwt_issuer=os.environ.get("EZ_API_JWT_ISSUER", "siftentry-api").strip(),
            access_token_minutes=int(os.environ.get("EZ_API_ACCESS_TOKEN_MINUTES", "15")),
            refresh_token_days=int(os.environ.get("EZ_API_REFRESH_TOKEN_DAYS", "14")),
            allow_dev_bootstrap=_truthy(
                os.environ.get(
                    "EZ_API_ALLOW_DEV_BOOTSTRAP",
                    "true" if environment != "production" else "false",
                )
            ),
            environment=environment,
            email_provider=os.environ.get(
                "EZ_EMAIL_PROVIDER",
                "log" if environment != "production" else "smtp",
            )
            .strip()
            .lower(),
            email_from=os.environ.get(
                "EZ_EMAIL_FROM",
                "SiftEntry <no-reply@siftentry.local>",
            ).strip(),
            email_reply_to=os.environ.get("EZ_EMAIL_REPLY_TO", "").strip(),
            smtp_host=os.environ.get("EZ_SMTP_HOST", "").strip(),
            smtp_port=int(os.environ.get("EZ_SMTP_PORT", "587")),
            smtp_username=os.environ.get("EZ_SMTP_USERNAME", "").strip(),
            smtp_password=os.environ.get("EZ_SMTP_PASSWORD", ""),
            smtp_use_tls=_truthy(os.environ.get("EZ_SMTP_USE_TLS", "true")),
            smtp_timeout_seconds=float(os.environ.get("EZ_SMTP_TIMEOUT_SECONDS", "10")),
        )
        settings.validate_startup()
        return settings

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return urlparse(self.database_url).scheme in {"", "file", "sqlite"}

    def validate_startup(self) -> None:
        """Fail fast when a production deployment is missing required controls."""

        if not self.is_production:
            return
        problems = self.production_readiness_problems()
        if problems:
            raise RuntimeError(
                "SiftEntry production configuration is incomplete: "
                + "; ".join(problems)
            )

    def production_readiness_problems(self) -> list[str]:
        problems: list[str] = []
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("set EZ_API_JWT_SECRET to a 32+ character random secret")
        if self.allow_dev_bootstrap:
            problems.append("set EZ_API_ALLOW_DEV_BOOTSTRAP=false")
        if not self.database_url:
            problems.append("set EZ_API_DATABASE_URL")
        if self.is_sqlite:
            problems.append(
                "pilot uses SQLite; attach a persistent disk or migrate to Postgres before production data"
            )
        if not self.app_base_url.startswith("https://"):
            problems.append("set EZ_APP_BASE_URL to the HTTPS app domain")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
            problems.append("remove localhost from EZ_API_CORS_ORIGINS")
        if not self.cors_origins:
            problems.append("set EZ_API_CORS_ORIGINS to the app domain")
        if self.email_provider != "smtp":
            problems.append("set EZ_EMAIL_PROVIDER=smtp")
        if not self.email_from:
            problems.append("set EZ_EMAIL_FROM")
        if self.email_provider == "smtp":
            if not self.smtp_host:
                problems.append("set EZ_SMTP_HOST")
            if not self.smtp_username:
                problems.append("set EZ_SMTP_USERNAME")
            if not self.smtp_password:
                problems.append("set EZ_SMTP_PASSWORD")
        return problems
