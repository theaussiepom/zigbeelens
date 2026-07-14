#!/usr/bin/env python3
"""Validate release-surface version equality across Core, HACS, and add-on."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _core_version() -> str:
    text = (ROOT / "apps/core/src/zigbeelens/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("FAIL: Core __version__ not found")
    return match.group(1)


def _manifest_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f"FAIL: missing version in {path}")
    return version.strip()


def _addon_version() -> str:
    text = (ROOT / "apps/addon/zigbeelens/config.yaml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise SystemExit("FAIL: add-on config.yaml version not found")


def main() -> int:
    versions: dict[str, str] = {
        "core": _core_version(),
        "hacs_manifest": _manifest_version(
            ROOT / "apps/ha_integration/custom_components/zigbeelens/manifest.json"
        ),
        "addon": _addon_version(),
    }
    packaged = ROOT / "dist/zigbeelens-hacs/custom_components/zigbeelens/manifest.json"
    if packaged.exists():
        versions["packaged_hacs_manifest"] = _manifest_version(packaged)

    unique = set(versions.values())
    if len(unique) != 1:
        print("FAIL: release surface versions diverge:", file=sys.stderr)
        for name, value in versions.items():
            print(f"  {name}={value}", file=sys.stderr)
        return 1

    version = next(iter(unique))
    checked = ", ".join(f"{name}={value}" for name, value in versions.items())
    print(f"OK: release versions synchronised ({checked})")
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
