"""Build the client-facing SiftEntry Tally Connector kit zip.

Run from anywhere:

    python packaging/client-kit/make_client_kit.py

Output goes to apps/web/public/downloads/SiftEntry-Tally-Connector-Kit.zip so
the deployed web app serves it at /downloads/SiftEntry-Tally-Connector-Kit.zip.
Re-run after any change to the connector modules or kit files, then commit the
regenerated zip.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
ROOT = KIT_DIR.parents[1]
APP_DIR = ROOT / "siftentry_app"
OUTPUT = ROOT / "apps" / "web" / "public" / "downloads" / "SiftEntry-Tally-Connector-Kit.zip"
FOLDER = "SiftEntry-Tally-Connector"

CONNECTOR_MODULES = [
    "tally_connector_desktop.py",
    "tally_connector_agent.py",
    "tally_connector_runtime.py",
]

KIT_FILES = [
    "README-START-HERE.txt",
    "SETUP_WINDOWS.bat",
    "START_CONNECTOR.bat",
    "INSTALL_STARTUP.bat",
    "UNINSTALL_STARTUP.bat",
]

CONFIG_SAMPLE = {
    "cloud_url": "https://app.siftentry.com",
    "workspace_id": "paste-your-workspace-id-here",
    "token": "paste-your-connector-token-here",
    "tally_url": "http://localhost:9000",
    "poll_interval": 15,
    "claim_limit": 5,
    "dry_run": False,
}


def main() -> None:
    missing = [
        name
        for name in CONNECTOR_MODULES
        if not (APP_DIR / name).exists()
    ] + [name for name in KIT_FILES if not (KIT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"Missing kit inputs: {', '.join(missing)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in CONNECTOR_MODULES:
            bundle.write(APP_DIR / name, f"{FOLDER}/{name}")
        for name in KIT_FILES:
            bundle.write(KIT_DIR / name, f"{FOLDER}/{name}")
        bundle.writestr(
            f"{FOLDER}/tally_connector_config.sample.json",
            json.dumps(CONFIG_SAMPLE, indent=2) + "\n",
        )

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Kit written: {OUTPUT} ({size_kb:.1f} KB)")
    with zipfile.ZipFile(OUTPUT) as bundle:
        for info in bundle.infolist():
            print(f"  {info.filename}")


if __name__ == "__main__":
    main()
