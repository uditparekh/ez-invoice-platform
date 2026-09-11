"""Keep runtime test state away from real connector installations."""
import pytest


@pytest.fixture(autouse=True)
def isolated_connector_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
