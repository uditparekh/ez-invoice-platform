"""One-way storage for cloud connector bearer credentials.

Existing installations keep their token: migration hashes it without rotation.
Hashes never act as bearer tokens and never leave normal profile responses.
"""
import hashlib
import hmac
import re

PREFIX = "sha256:"


def is_token_hash(value: str) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def token_hash(token: str) -> str:
    return PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored: str) -> bool:
    return is_token_hash(stored) and hmac.compare_digest(token_hash(token), stored)


def protected_settings(settings: dict) -> dict:
    settings = dict(settings)
    connection = dict(settings.get("connection_settings") or {})
    value = str(connection.get("connector_token") or "")
    if value and not is_token_hash(value):
        connection["connector_token"] = token_hash(value)
    connection.pop("connector_token_set", None)
    settings["connection_settings"] = connection
    return settings
