#!/usr/bin/env python3
"""Narrow release-documentation validation.

Checks tracked Markdown links/anchors, parses maintained JSON/YAML examples,
validates canonical Core configuration examples with production models, and
seals a few high-risk public documentation contracts.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin
from urllib.parse import unquote

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "apps/core/src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from zigbeelens.config import AppConfig, load_config  # noqa: E402
from zigbeelens.schemas import ReportRequest  # noqa: E402


class DocumentationError(RuntimeError):
    """One actionable documentation validation failure."""


def tracked_files(pattern: str) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def strip_fenced_blocks(text: str) -> str:
    return re.sub(r"^```.*?^```\s*$", "", text, flags=re.MULTILINE | re.DOTALL)


def github_anchor(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    # GitHub replaces each remaining space, so punctuation between two spaces
    # can intentionally yield a double hyphen (for example "proxy / Traefik").
    return re.sub(r"\s", "-", text)


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        base = github_anchor(match.group(1))
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def link_destination(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    # Optional Markdown title follows whitespace. Repository paths do not use
    # spaces; angle brackets are required if that changes.
    return raw.split(maxsplit=1)[0]


def validate_markdown_links(markdown_files: list[Path]) -> tuple[int, int]:
    link_count = 0
    external_count = 0
    anchor_cache: dict[Path, set[str]] = {}
    errors: list[str] = []
    link_pattern = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")

    for source in markdown_files:
        text = strip_fenced_blocks(source.read_text(encoding="utf-8"))
        for match in link_pattern.finditer(text):
            destination = link_destination(match.group(1))
            if not destination:
                continue
            if re.match(r"^(?:https?|mailto):", destination, flags=re.IGNORECASE):
                external_count += 1
                continue
            link_count += 1
            path_part, separator, fragment = destination.partition("#")
            path_part = unquote(path_part)
            fragment = unquote(fragment).lower()

            if not path_part:
                target = source
            elif path_part.startswith("/"):
                errors.append(
                    f"{source.relative_to(ROOT)}: repository link must be relative: {destination}"
                )
                continue
            else:
                target = (source.parent / path_part).resolve()

            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"{source.relative_to(ROOT)}: link escapes repository: {destination}"
                )
                continue

            if not target.exists():
                errors.append(
                    f"{source.relative_to(ROOT)}: missing link target: {destination}"
                )
                continue

            if separator and fragment and target.suffix.lower() == ".md":
                anchors = anchor_cache.setdefault(target, markdown_anchors(target))
                if fragment not in anchors:
                    errors.append(
                        f"{source.relative_to(ROOT)}: missing heading #{fragment} "
                        f"in {target.relative_to(ROOT)}"
                    )

    if errors:
        raise DocumentationError("\n".join(errors))
    return link_count, external_count


def fenced_data_blocks(path: Path) -> list[tuple[str, str, int]]:
    blocks: list[tuple[str, str, int]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        opening = re.match(r"^```(json|ya?ml)\s*$", lines[index], flags=re.IGNORECASE)
        if opening is None:
            index += 1
            continue
        start = index + 1
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != "```":
            body.append(lines[index])
            index += 1
        if index >= len(lines):
            raise DocumentationError(
                f"{path.relative_to(ROOT)}:{start}: unterminated data fence"
            )
        blocks.append((opening.group(1).lower(), "\n".join(body), start))
        index += 1
    return blocks


def validate_fenced_examples(markdown_files: list[Path]) -> int:
    count = 0
    errors: list[str] = []
    for path in markdown_files:
        for language, body, line in fenced_data_blocks(path):
            if not body.strip():
                continue
            try:
                if language == "json":
                    json.loads(body)
                else:
                    yaml.safe_load(body)
            except (json.JSONDecodeError, yaml.YAMLError) as exc:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line}: invalid {language} example: {exc}"
                )
            count += 1
    if errors:
        raise DocumentationError("\n".join(errors))
    return count


GENERIC_DATA_FILES = (
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/diagnostic_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/docker.yml",
    ".github/workflows/release-check.yml",
    "apps/addon/repository.yaml",
    "apps/addon/zigbeelens/config.yaml",
    "apps/addon/zigbeelens/translations/en.yaml",
    "apps/ha_integration/custom_components/zigbeelens/manifest.json",
    "apps/ha_integration/custom_components/zigbeelens/strings.json",
    "apps/ha_integration/custom_components/zigbeelens/translations/en.json",
    "apps/ha_integration/hacs.json",
    "deploy/compose/docker-compose.dev.yaml",
    "deploy/docker/docker-compose.example.yaml",
    "deploy/docker/docker-compose.mosquitto.example.yaml",
    "deploy/docker/docker-compose.traefik.example.yaml",
    "deploy/docker/docker-compose.caddy.example.yaml",
    "deploy/docker/docker-compose.beast-traefik.example.yaml",
    "release/zigbeelens-addons/.github/workflows/ci.yml",
    "release/zigbeelens-hacs/.github/workflows/ci.yml",
    "release/zigbeelens-hacs/.github/workflows/release.yml",
)

CORE_CONFIG_EXAMPLES = (
    "config/config.yaml",
    "config/config.live.example.yaml",
    "examples/config.example.yaml",
    "deploy/compose/config.dev.yaml",
    "deploy/docker/config.example.yaml",
    "deploy/docker/config.multi-network.example.yaml",
    "local/zigbeelens-test/config/config.yaml.example",
)


def validate_data_files() -> tuple[int, int]:
    parsed = 0
    for relative in GENERIC_DATA_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise DocumentationError(f"missing maintained data example: {relative}")
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            json.loads(text)
        else:
            yaml.safe_load(text)
        parsed += 1

    config_count = 0
    for relative in CORE_CONFIG_EXAMPLES:
        path = ROOT / relative
        if not path.is_file():
            raise DocumentationError(f"missing Core configuration example: {relative}")
        load_config(path)
        config_count += 1

    request_path = ROOT / "examples/report-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    ReportRequest.model_validate(request)
    parsed += 1
    return parsed, config_count


CURRENT_CONTRACT_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "RELEASE_CHECKLIST.md",
    "SECURITY.md",
    "docs/api.md",
    "docs/architecture.md",
    "docs/configuration.md",
    "docs/docker.md",
    "docs/development.md",
    "docs/hacs.md",
    "docs/hacs-embedded-view.md",
    "docs/mqtt-dev.md",
    "docs/mqtt-discovery.md",
    "docs/redaction.md",
    "docs/reports.md",
    "docs/safety-audit.md",
    "docs/security.md",
    "docs/topology.md",
    "docs/troubleshooting.md",
    "docs/upgrades.md",
    "docs/backups.md",
    "docs/release.md",
    "docs/release-infra.md",
    "docs/release-test.md",
    "apps/addon/zigbeelens/README.md",
    "apps/core/README.md",
    "apps/ha_integration/README.md",
    "apps/ui/src/viewModels/README.md",
    "deploy/docker/README.md",
    "release/zigbeelens-hacs/README.md.in",
)


def validate_current_contract_copy() -> int:
    combined = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8") for relative in CURRENT_CONTRACT_DOCS
    )
    forbidden = {
        "string-valued report redaction": (
            r'(?<!do not send )(?<!do not send `)"redaction"\s*:\s*"'
        ),
        "retired report configuration section": r"`reports\.\*`|\breports:\s*\n",
        "retired report overview scope": r"report scope[^\n]*overview|scope:\s*overview",
        "retired HACS decision contract v1": r"decision_contract_version\s*=\s*1",
        "retired HACS auto-embed": r"\bauto-embed\b|\bsame-protocol auto",
        "blanket MQTT no-publish claim": r"\bnever publishes MQTT\b|\bno MQTT writes\b",
        "retired root scenario catalogue": r"^## Mock scenarios\s*$",
    }
    failures = [
        label
        for label, pattern in forbidden.items()
        if re.search(pattern, combined, flags=re.IGNORECASE | re.MULTILINE)
    ]
    if failures:
        raise DocumentationError(
            "stale current-contract copy found:\n- " + "\n- ".join(failures)
        )

    packaged = (ROOT / "release/zigbeelens-hacs/README.md.in").read_text(
        encoding="utf-8"
    )
    required_packaged = (
        "decision_contract_version = 2",
        "native companion",
        "Back to Summary",
        "ZigbeeLens Core must already be running",
    )
    missing = [value for value in required_packaged if value.lower() not in packaged.lower()]
    if missing:
        raise DocumentationError(
            "packaged HACS README missing current contract text: " + ", ".join(missing)
        )

    for relative in (
        "docs/decision-engine-migration.md",
        "docs/decision-engine-implementation-plan.md",
        "docs/decision-engine-cursor-guardrails.md",
        "docs/lens-alignment-status.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for required in ("Phase 7C1", "Phase 7C2", "Phase 7D"):
            if required not in text:
                raise DocumentationError(f"{relative}: missing {required} status boundary")

    required_truth: dict[str, tuple[str, ...]] = {
        "docs/addon-dev.md": (
            "not a direct `localhost:8377` development server",
            "not an equivalent test",
        ),
        "docs/configuration.md": (
            "a changed interval is not durable",
            "`reporting.default_profile`",
            "`mqtt_discovery.object_id_prefix`",
        ),
        "docs/hacs.md": (
            "`core_version_compatible()` returns `true`",
            "factually wrong for a payload-shape failure",
            "`capabilities.report_contract_v3`",
            "Only one ZigbeeLens config entry/Core target is supported",
        ),
        "docs/hacs-embedded-view.md": (
            "ZigbeeLens → Reconfigure",
            "changes trust inside the Caddy container only",
            "This bypass covers every `/api` route",
        ),
        "docs/release-test.md": (
            "freshly generated staging directory",
            "currently blocked: the empty OptionsFlow result",
        ),
        "docs/safety-audit.md": (
            "Current release blocker: the MQTT client last will",
            "parsed node/link `raw_json`",
        ),
        "RELEASE_CHECKLIST.md": (
            "`test_ui_has_no_repair_controls` currently skips",
            "Missing or malformed Core versions project compatibility Unknown",
        ),
    }
    truth_assertions = 0
    for relative, required_fragments in required_truth.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        normalized_text = " ".join(text.split())
        missing = [
            fragment
            for fragment in required_fragments
            if " ".join(fragment.split()) not in normalized_text
        ]
        if missing:
            raise DocumentationError(
                f"{relative}: missing current truth guard(s): " + ", ".join(missing)
            )
        truth_assertions += len(required_fragments)

    configuration = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    missing_config_keys = [
        path for path in model_leaf_paths(AppConfig) if f"`{path}`" not in configuration
    ]
    if missing_config_keys:
        raise DocumentationError(
            "docs/configuration.md is missing production keys: "
            + ", ".join(missing_config_keys)
        )
    return (
        len(forbidden)
        + len(required_packaged)
        + 12
        + truth_assertions
        + len(model_leaf_paths(AppConfig))
    )


def nested_model(annotation: object) -> tuple[type[BaseModel] | None, bool]:
    """Return a nested Pydantic model and whether it is list-valued."""
    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        candidate = args[0] if args else None
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate, True
        return None, True
    if origin in (UnionType, Union):
        for candidate in get_args(annotation):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                return candidate, False
        return None, False
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation, False
    return None, False


def model_leaf_paths(model: type[BaseModel], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for name, field in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        child, list_valued = nested_model(field.annotation)
        if child is None:
            paths.append(path)
            continue
        child_prefix = f"{path}[]" if list_valued else path
        paths.extend(model_leaf_paths(child, child_prefix))
    return paths


def main() -> int:
    markdown_files = tracked_files("*.md")
    # Include the new uncommitted guide during local validation before its first commit.
    configuration = ROOT / "docs/configuration.md"
    if configuration.is_file() and configuration not in markdown_files:
        markdown_files.append(configuration)
    markdown_files.sort()

    links, external = validate_markdown_links(markdown_files)
    fenced = validate_fenced_examples(markdown_files)
    data_files, configs = validate_data_files()
    seals = validate_current_contract_copy()

    print(
        "Documentation validation OK: "
        f"{len(markdown_files)} Markdown files, "
        f"{links} internal links/images, "
        f"{external} external links inventoried, "
        f"{fenced} fenced JSON/YAML blocks parsed, "
        f"{data_files} maintained JSON/YAML files parsed, "
        f"{configs} Core configs validated, "
        "1 ReportRequest validated, "
        f"{seals} contract/status assertions."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        DocumentationError,
        json.JSONDecodeError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Documentation validation failed:\n{exc}", file=sys.stderr)
        raise SystemExit(1) from None
