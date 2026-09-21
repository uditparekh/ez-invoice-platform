"""Shared, transport-safe connector credential rules (never log the value)."""

TOKEN_FORMAT_MESSAGE = (
    "Connector token must contain 1–512 printable ASCII characters with no spaces. "
    "Generate a new token, save the profile, then copy it into the connector."
)


def valid_connector_token(value: str) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 512 and all(
        33 <= ord(character) <= 126 for character in value
    )
