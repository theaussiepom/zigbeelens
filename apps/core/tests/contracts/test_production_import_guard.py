"""Production modules must not import test support."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "zigbeelens"


def test_production_modules_do_not_import_test_support():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "tests.support" in text or "from support." in text or "import support" in text:
            # Allow comments that mention the rule.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "tests.support" in stripped
                    or "from support." in stripped
                    or stripped == "import support"
                ):
                    offenders.append(f"{path}:{stripped}")
    assert offenders == []


def test_production_modules_do_not_import_tests_package():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "from tests." in stripped or stripped.startswith("import tests"):
                offenders.append(f"{path}:{stripped}")
    assert offenders == []
