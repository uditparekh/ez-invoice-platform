"""Environment-based settings for the EZ-Invoice API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ApiSettings:
    database_path: Path
    upload_directory: Path
    max_upload_bytes: int
    cors_origins: tuple[str, ...]
    jwt_secret: str = "ez-invoice-local-development-secret-change-me"
    jwt_issuer: str = "ez-invoice-api"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    allow_dev_bootstrap: bool = True
    environment: str = "development"

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        data_dir = APP_ROOT / "data"
        environment = os.environ.get("EZ_API_ENVIRONMENT", "development").strip().lower()
        jwt_secret = os.environ.get(
            "EZ_API_JWT_SECRET",
            "ez-invoice-local-development-secret-change-me",
        )
        if environment == "production" and jwt_secret == "ez-invoice-local-development-secret-change-me":
            raise RuntimeError("Set EZ_API_JWT_SECRET before starting the production API.")
        origins = tuple(
            origin.strip()
            for origin in os.environ.get(
                "EZ_API_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if origin.strip()
        )
        return cls(
            database_path=Path(
                os.environ.get("EZ_API_DATABASE_PATH", data_dir / "ez_invoice.db")
            ).expanduser(),
            upload_directory=Path(
                os.environ.get("EZ_API_UPLOAD_DIRECTORY", data_dir / "uploads")
            ).expanduser(),
            max_upload_bytes=int(
                os.environ.get("EZ_API_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))
            ),
            cors_origins=origins,
            jwt_secret=jwt_secret,
            jwt_issuer=os.environ.get("EZ_API_JWT_ISSUER", "ez-invoice-api").strip(),
            access_token_minutes=int(os.environ.get("EZ_API_ACCESS_TOKEN_MINUTES", "15")),
            refresh_token_days=int(os.environ.get("EZ_API_REFRESH_TOKEN_DAYS", "14")),
            allow_dev_bootstrap=(
                os.environ.get(
                    "EZ_API_ALLOW_DEV_BOOTSTRAP",
                    "true" if environment != "production" else "false",
                ).strip().lower()
                in {"1", "true", "yes", "on"}
            ),
            environment=environment,
        )
