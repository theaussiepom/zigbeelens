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
from datetime import date
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


def normalized_document(relative: str) -> str:
    return " ".join((ROOT / relative).read_text(encoding="utf-8").split())


def require_document_fragments(relative: str, fragments: tuple[str, ...]) -> int:
    normalized = normalized_document(relative)
    return require_text_fragments(relative, normalized, fragments)


def require_text_fragments(
    label: str, text: str, fragments: tuple[str, ...]
) -> int:
    normalized = " ".join(text.split())
    missing = [
        fragment
        for fragment in fragments
        if " ".join(fragment.split()).lower() not in normalized.lower()
    ]
    if missing:
        raise DocumentationError(
            f"{label}: missing documentation contract(s): " + ", ".join(missing)
        )
    return len(fragments)


def option_section(text: str, label: str) -> str:
    match = re.search(
        rf"^## Option {re.escape(label)}\b.*?(?=^## Option [A-Z]\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise DocumentationError(
            f"docs/hacs-embedded-view.md: missing Option {label} section"
        )
    return " ".join(match.group(0).split())


def validate_docker_install_truth() -> int:
    expected = "${ZIGBEELENS_IMAGE:-ghcr.io/theaussiepom/zigbeelens:latest}"
    overrideable_examples = (
        "deploy/docker/docker-compose.example.yaml",
        "deploy/docker/docker-compose.mosquitto.example.yaml",
        "deploy/docker/docker-compose.traefik.example.yaml",
        "deploy/docker/docker-compose.caddy.example.yaml",
    )
    for relative in overrideable_examples:
        compose = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        image = compose.get("services", {}).get("zigbeelens", {}).get("image")
        if image != expected:
            raise DocumentationError(
                f"{relative}: ZigbeeLens image must remain overrideable with "
                f"released default {expected!r}"
            )

    assertions = len(overrideable_examples)
    assertions += require_document_fragments(
        "docs/docker.md",
        (
            "## Released/stable install",
            "## Current-main/pre-release validation",
            "`latest` — latest tagged release",
            "`edge` / `main` — rolling current `main`",
            "`sha-*` — a traceable workflow-built commit",
            "`ZIGBEELENS_IMAGE` selects the container image",
        ),
    )
    assertions += require_document_fragments(
        "deploy/docker/README.md",
        (
            "## Released/stable run",
            "## Current-main/pre-release",
            "`latest` — latest tagged release",
            "`edge` / `main` — rolling current `main`",
            "`sha-*` — a traceable workflow-built commit",
        ),
    )

    release_test = (ROOT / "docs/release-test.md").read_text(encoding="utf-8")
    if re.search(
        r"ghcr\.io/theaussiepom/zigbeelens:latest\b",
        release_test,
        flags=re.IGNORECASE,
    ):
        raise DocumentationError(
            "docs/release-test.md: current-main guide must not use the released "
            "latest image"
        )
    if "ghcr.io/theaussiepom/zigbeelens:edge" not in release_test:
        raise DocumentationError(
            "docs/release-test.md: current-main guide must retain the edge image"
        )
    assertions += 2

    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    build_index = root_readme.find(
        "ZIGBEELENS_IMAGE=zigbeelens:local ./scripts/build-docker.sh"
    )
    compose_index = root_readme.find(
        "ZIGBEELENS_IMAGE=zigbeelens:local docker compose up -d"
    )
    if build_index < 0 or compose_index < 0 or build_index >= compose_index:
        raise DocumentationError(
            "README.md: local Docker quick start must build the selected local "
            "image before Compose runs it"
        )
    return assertions + 1


def validate_addon_operational_truth() -> int:
    required: dict[str, tuple[str, ...]] = {
        "docs/hacs.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "apps/ha_integration/README.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "docs/hacs-embedded-view.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "docs/upgrades.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "docs/backups.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "docs/troubleshooting.md": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "release/zigbeelens-hacs/README.md.in": (
            "source-built/local pre-release testing",
            "future published add-on artifact",
            "publication gates close",
        ),
        "docs/configuration.md": (
            "source-built/local pre-release runner",
            "future published add-on artifact",
            "publication gates close",
        ),
        "SECURITY.md": (
            "HAOS add-on source/local pre-release",
            "future published artifact",
            "publication gates close",
        ),
    }
    assertions = sum(
        require_document_fragments(relative, fragments)
        for relative, fragments in required.items()
    )

    operational = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8") for relative in required
    )
    forbidden = {
        "shipped add-on claim": r"\bshipped Home Assistant add-on\b",
        "already-available add-on claim": r"\badd-on already provides\b",
        "bare add-on Ingress direction": r"\bUse the add-on['’]s Ingress UI\b",
        "unqualified designed add-on path": (
            r"\bHAOS add-on \+ Ingress\b[^\n]*\bdesigned embedded path\b"
        ),
        "unconditional store upgrade": (
            r"^\s*\d+\.\s+Update the add-on from the store\s*$"
        ),
        "unqualified preferred add-on restore": (
            r"\bpreferred add-on restore mechanism\b"
        ),
        "unqualified add-on troubleshooting heading": (
            r"^## Add-on Ingress blank page\s*$"
        ),
        "available packaged add-on claim": (
            r"\bThe packaged Home Assistant add-on exposes\b"
        ),
        "unqualified HAOS deployment row": (
            r"^\|\s*HAOS add-on\s*\|\s*Full dashboard\b"
        ),
        "unqualified add-on configuration row": (
            r"^\|\s*Home Assistant add-on\s*\|\s*Supervisor"
        ),
    }
    failures = [
        label
        for label, pattern in forbidden.items()
        if re.search(pattern, operational, flags=re.IGNORECASE | re.MULTILINE)
    ]
    if failures:
        raise DocumentationError(
            "unqualified blocked add-on operational guidance found:\n- "
            + "\n- ".join(failures)
        )
    return assertions + len(forbidden)


def validate_hacs_proxy_image_truth() -> int:
    beast = yaml.safe_load(
        (
            ROOT / "deploy/docker/docker-compose.beast-traefik.example.yaml"
        ).read_text(encoding="utf-8")
    )
    beast_image = beast.get("services", {}).get("zigbeelens", {}).get("image")
    expected_beast = "ghcr.io/theaussiepom/zigbeelens:edge"
    if beast_image != expected_beast:
        raise DocumentationError(
            "deploy/docker/docker-compose.beast-traefik.example.yaml: "
            f"current-main HACS path must remain on {expected_beast!r}"
        )

    embedded = (ROOT / "docs/hacs-embedded-view.md").read_text(encoding="utf-8")
    stale_current_hacs_terms = (
        "current HACS pre-release procedure",
        "HACS Core URL",
        "HACS sensors",
        "HACS companion panel",
        "future compatible released HACS/Core pair",
        "enter the same token in HACS",
        "For a HACS direct iframe",
        "required for HACS over HTTPS",
    )
    stale_terms_found = [
        term for term in stale_current_hacs_terms if term.lower() in embedded.lower()
    ]
    if stale_terms_found:
        raise DocumentationError(
            "docs/hacs-embedded-view.md: stale current-public-HACS ownership "
            "wording found: " + ", ".join(stale_terms_found)
        )
    required: dict[str, tuple[str, ...]] = {
        "A": (
            expected_beast,
            "deliberately hardcodes",
            "current-main/pre-release testing",
            "not remote release validation",
            "`X.Y.Z`",
        ),
        "B": (
            "defaults to `latest`",
            "export ZIGBEELENS_IMAGE=ghcr.io/theaussiepom/zigbeelens:edge",
            "Keep `ZIGBEELENS_IMAGE` set",
            "not remote release-validation evidence",
        ),
        "C": (
            "future compatible published companion/Core pair",
            "export ZIGBEELENS_IMAGE=ghcr.io/theaussiepom/zigbeelens:edge",
            "mkdir -p ~/zigbeelens-traefik/{config,data}",
            "cp deploy/docker/docker-compose.traefik.example.yaml",
            "~/zigbeelens-traefik/docker-compose.yaml",
            "cp deploy/docker/config.example.yaml",
            "~/zigbeelens-traefik/config/config.yaml",
            "`mqtt.server`",
            "`base_topic`",
            "security settings",
            "Traefik hostname",
            "external proxy-network name",
            "cd ~/zigbeelens-traefik",
            "docker compose config",
            "docker compose pull",
            "docker compose up -d",
            "Keep `ZIGBEELENS_IMAGE` set",
            "~/zigbeelens-traefik/.env",
            "default `latest` tagged release",
            "ghcr.io/theaussiepom/zigbeelens:X.Y.Z",
            "not remote release-validation evidence",
        ),
        "D": (
            "nginx does not select or start a ZigbeeLens Core image",
            "Current-main/pre-release validation",
            "`edge`",
            "`sha-*`",
            "`X.Y.Z`",
        ),
    }
    assertions = 1 + len(stale_current_hacs_terms)
    for label, fragments in required.items():
        section = option_section(embedded, label).lower()
        missing = [
            fragment
            for fragment in fragments
            if " ".join(fragment.split()).lower() not in section
        ]
        if missing:
            raise DocumentationError(
                "docs/hacs-embedded-view.md: "
                f"Option {label} is missing image-channel contract(s): "
                + ", ".join(missing)
            )
        assertions += len(fragments)

    option_c = option_section(embedded, "C")
    if re.search(
        r"docker compose\s+-f\s+(?:\./)?deploy/docker/"
        r"docker-compose\.traefik\.example\.yaml",
        option_c,
        flags=re.IGNORECASE,
    ):
        raise DocumentationError(
            "docs/hacs-embedded-view.md: Option C must not execute the "
            "maintained Traefik template in place"
        )
    copied_layout_order = (
        "mkdir -p ~/zigbeelens-traefik/{config,data}",
        "cp deploy/docker/docker-compose.traefik.example.yaml",
        "cp deploy/docker/config.example.yaml",
        "cd ~/zigbeelens-traefik",
        "export ZIGBEELENS_IMAGE=ghcr.io/theaussiepom/zigbeelens:edge",
        "docker compose config",
        "docker compose pull",
        "docker compose up -d",
    )
    ordered_positions = tuple(option_c.find(command) for command in copied_layout_order)
    if any(position < 0 for position in ordered_positions) or ordered_positions != tuple(
        sorted(ordered_positions)
    ):
        raise DocumentationError(
            "docs/hacs-embedded-view.md: Option C copied-layout commands must "
            "create, enter, render, pull, and start the installation in order"
        )
    assertions += 1 + len(copied_layout_order)
    return assertions


def validate_shared_package_test_truth() -> int:
    package = json.loads(
        (ROOT / "packages/shared/package.json").read_text(encoding="utf-8")
    )
    test_script = package.get("scripts", {}).get("test", "")
    assertions = 1
    if "No tests configured for shared" not in test_script:
        return assertions

    claim_owners = (
        "CONTRIBUTING.md",
        "RELEASE_CHECKLIST.md",
        "docs/release.md",
        "docs/release-test.md",
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release-check.yml",
        "scripts/run-release-checks.sh",
    )
    command = "pnpm --filter @zigbeelens/shared test"
    offenders = [
        relative
        for relative in claim_owners
        if command in (ROOT / relative).read_text(encoding="utf-8")
    ]
    if offenders:
        raise DocumentationError(
            "shared package no-op is presented as a test lane in: "
            + ", ".join(offenders)
        )

    assertions += len(claim_owners)
    assertions += require_document_fragments(
        "CONTRIBUTING.md",
        (
            "no dedicated shared package test suite",
            "pnpm --filter @zigbeelens/shared build",
            "pnpm --filter @zigbeelens/shared typecheck",
        ),
    )
    assertions += require_document_fragments(
        "RELEASE_CHECKLIST.md",
        (
            "Shared package build passes",
            "no dedicated test suite",
            "do not treat its no-op `test` script as release evidence",
        ),
    )
    assertions += require_document_fragments(
        ".github/pull_request_template.md",
        ("UI tests, shared build/typecheck",),
    )
    return assertions


def validate_companion_publication_truth() -> int:
    assertions = 0
    hacs_documents = (
        "docs/hacs.md",
        "apps/ha_integration/README.md",
        "release/zigbeelens-hacs/README.md.in",
    )
    status_heading = "## Release status — local/staged integration only"
    local_heading = "## Local staged integration testing"
    future_heading = "## Conditional public HACS installation"
    current_install_pattern = re.compile(
        r"(?:https://github\.com/[^\s`)\]]+/zigbeelens-hacs(?:[^\s`)\]]*)?|"
        r"HACS\s*→\s*Integrations\s*→\s*Custom repositories|"
        r"pre-release install via HACS|HACS is required|"
        r"requires[^\n.]{0,120}\bHACS\b|"
        r"\b(?:install|add|use)\b[^\n]{0,160}"
        r"\b(?:[A-Za-z0-9_.-]+/)?zigbeelens-hacs\b)",
        flags=re.IGNORECASE,
    )
    local_install_contracts: dict[str, tuple[str, ...]] = {
        "docs/hacs.md": (
            "./scripts/package-hacs-repo.sh",
            "dist/zigbeelens-hacs/custom_components/zigbeelens",
            "<home-assistant-config>/custom_components/zigbeelens/",
            "full Home Assistant restart",
            "Do not add the public satellite",
        ),
        "apps/ha_integration/README.md": (
            "./scripts/package-hacs-repo.sh",
            "dist/zigbeelens-hacs/custom_components/zigbeelens/",
            "<home-assistant-config>/custom_components/zigbeelens/",
            "full Home Assistant restart",
            "Do not use the public HACS satellite",
        ),
        "release/zigbeelens-hacs/README.md.in": (
            "./scripts/package-hacs-repo.sh",
            "custom_components/zigbeelens/",
            "<home-assistant-config>/custom_components/zigbeelens/",
            "full Home Assistant restart",
            "Do not use the unsynchronized public satellite",
            "@SOURCE_REPOSITORY@",
            "@SOURCE_COMMIT@",
            "generated `SOURCE_COMMIT` file records the same commit",
            "blob/@SOURCE_COMMIT@/docs/hacs.md",
        ),
    }
    future_install_contracts: dict[str, tuple[str, ...]] = {
        "docs/hacs.md": (
            "staged tree matches the intended satellite tree",
            "version uniquely identifies that tree",
            "2025.1.0 plus current-version coverage",
            "official HACS and hassfest validation",
            "explicit publication authorization",
        ),
        "apps/ha_integration/README.md": (
            "staged tree must match the intended satellite tree",
            "version must uniquely identify that tree",
            "2025.1.0 plus current coverage",
            "official HACS and hassfest validation",
            "explicit publication authorization",
        ),
        "release/zigbeelens-hacs/README.md.in": (
            "staged tree must match the intended satellite tree",
            "version must uniquely identify that tree",
            "2025.1.0 plus current-version coverage",
            "official HACS and hassfest validation",
            "explicit publication authorization",
            "https://github.com/@FUTURE_HACS_REPOSITORY@",
        ),
    }
    for relative in hacs_documents:
        text = (ROOT / relative).read_text(encoding="utf-8")
        indexes = tuple(
            text.find(heading)
            for heading in (status_heading, local_heading, future_heading)
        )
        if any(index < 0 for index in indexes) or indexes != tuple(sorted(indexes)):
            raise DocumentationError(
                f"{relative}: release status, local staged testing, and future "
                "public HACS sections must appear in that order"
            )
        current_guidance = text[: indexes[2]]
        if current_install_pattern.search(current_guidance):
            raise DocumentationError(
                f"{relative}: current guidance directs users to the "
                "unsynchronized public HACS satellite"
            )
        if relative == "release/zigbeelens-hacs/README.md.in":
            expected_operational_docs = {
                "https://github.com/@SOURCE_REPOSITORY@/blob/"
                "@SOURCE_COMMIT@/docs/docker.md",
                "https://github.com/@SOURCE_REPOSITORY@/blob/"
                "@SOURCE_COMMIT@/docs/hacs.md",
            }
            operational_docs = set(
                re.findall(
                    r"https://github\.com/[^\s`)\]]+/blob/"
                    r"[^\s`)\]]+/docs/[^\s`)\]]+",
                    current_guidance,
                )
            )
            if operational_docs != expected_operational_docs:
                raise DocumentationError(
                    f"{relative}: current operational documentation must be "
                    "the exact SOURCE_REPOSITORY/SOURCE_COMMIT Docker and "
                    f"HACS URLs, found {sorted(operational_docs)}"
                )
            if "/blob/main/docs/" in current_guidance:
                raise DocumentationError(
                    f"{relative}: current/local-stage guidance must not use "
                    "moving blob/main documentation"
                )
            if "@FUTURE_HACS_REPOSITORY@" in current_guidance:
                raise DocumentationError(
                    f"{relative}: future HACS repository identity must remain "
                    "inside the conditional publication section"
                )
            assertions += 3
        local_guidance = text[indexes[1] : indexes[2]]
        future_guidance = text[indexes[2] :]
        assertions += require_text_fragments(
            f"{relative} local staged integration section",
            local_guidance,
            local_install_contracts[relative],
        )
        assertions += require_text_fragments(
            f"{relative} conditional public HACS section",
            future_guidance,
            future_install_contracts[relative],
        )
        assertions += 4

    addon_ordered_sections = (
        (
            "apps/addon/zigbeelens/README.md",
            "## Release status — generated repository publication blocked",
            "## Conditional public-repository install",
        ),
        (
            "scripts/package-addon-repo.sh",
            "## Release status — generated repository publication blocked",
            "## Conditional install after publication",
        ),
    )
    for relative, addon_status_heading, install_heading in addon_ordered_sections:
        text = (ROOT / relative).read_text(encoding="utf-8")
        status_index = text.find(addon_status_heading)
        install_index = text.find(install_heading)
        if status_index < 0 or install_index < 0 or status_index >= install_index:
            raise DocumentationError(
                f"{relative}: publication status must precede install procedure"
            )
        assertions += 1

    current_guidance_owners = (
        "README.md",
        "docs/release-test.md",
        "docs/troubleshooting.md",
    )
    offenders = [
        relative
        for relative in current_guidance_owners
        if current_install_pattern.search(
            (ROOT / relative).read_text(encoding="utf-8")
        )
    ]
    if offenders:
        raise DocumentationError(
            "current guidance points to the unsynchronized public HACS "
            "satellite in: " + ", ".join(offenders)
        )
    assertions += len(current_guidance_owners)

    hacs_blockers = (
        "OptionsFlow",
        "missing or malformed Core versions",
        "exact-v2 Dashboard",
        "2025.1.0",
        "`single_config_entry`",
        "official HACS and hassfest",
    )
    assertions += require_document_fragments("docs/hacs.md", hacs_blockers)
    assertions += require_document_fragments(
        "release/zigbeelens-hacs/README.md.in",
        (
            "OptionsFlow",
            "missing/malformed Core versions",
            "exact-v2 Dashboard",
            "2025.1.0",
            "`single_config_entry`",
            "official HACS and hassfest",
        ),
    )
    assertions += require_document_fragments(
        "README.md",
        (
            "Current portable deployment route",
            "Local/staged source testing only",
            "public HACS satellite unsynchronized",
            "Pre-release source — generated repository publication blocked",
        ),
    )
    synchronization_gates: dict[str, tuple[str, ...]] = {
        "RELEASE_CHECKLIST.md": (
            "complete staged tree matches the intended",
            "version uniquely identifies that tree",
            "Exact Home Assistant 2025.1.0 minimum and a current",
            "official HACS/hassfest checks",
            "Explicit authorization",
        ),
        "docs/release-infra.md": (
            "complete staged tree matches the intended satellite tree",
            "version that uniquely identifies that exact tree",
            "2025.1.0 plus current-version coverage",
            "official HACS and hassfest validation",
            "explicit publication authorization",
        ),
        "docs/release.md": (
            "complete staged tree must match the intended satellite tree",
            "version must uniquely identify that exact tree",
            "2025.1.0 plus current-version coverage",
            "official HACS and hassfest validation",
            "explicit publication authorization",
        ),
    }
    assertions += sum(
        require_document_fragments(relative, fragments)
        for relative, fragments in synchronization_gates.items()
    )
    reviewed_state_pattern = re.compile(
        r"Reviewed public-satellite state \(historical evidence\):\s*"
        r"- repository: `(?P<repository>@REVIEWED_HACS_REPOSITORY@|"
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`\s*"
        r"- commit: `(?P<commit>[0-9a-f]{40})`\s*"
        r"- reviewed: `(?P<reviewed>[0-9]{4}-[0-9]{2}-[0-9]{2})`"
    )
    reviewed_evidence: list[tuple[str, str, str]] = []
    for relative in (
        "docs/release-infra.md",
        "release/zigbeelens-hacs/README.md.in",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        reviewed_states = list(reviewed_state_pattern.finditer(text))
        if len(reviewed_states) != 1:
            raise DocumentationError(
                f"{relative}: reviewed public-satellite state must contain "
                "exactly one repository, 40-character commit SHA, and "
                "ISO-format review date block"
            )
        reviewed_state = reviewed_states[0]
        reviewed_repository = reviewed_state.group("repository")
        if reviewed_repository == "@REVIEWED_HACS_REPOSITORY@":
            reviewed_repository = "theaussiepom/zigbeelens-hacs"
        if reviewed_repository != "theaussiepom/zigbeelens-hacs":
            raise DocumentationError(
                f"{relative}: reviewed public-satellite repository must remain "
                "theaussiepom/zigbeelens-hacs"
            )
        try:
            date.fromisoformat(reviewed_state.group("reviewed"))
        except ValueError as exc:
            raise DocumentationError(
                f"{relative}: public-satellite review date must be a valid ISO date"
            ) from exc
        if re.search(
            r"re-check its current tree(?: immediately)? before (?:any )?publication",
            text,
            flags=re.IGNORECASE,
        ) is None:
            raise DocumentationError(
                f"{relative}: public-satellite evidence must require a re-check "
                "before publication"
            )
        reviewed_evidence.append(
            (
                reviewed_repository,
                reviewed_state.group("commit"),
                reviewed_state.group("reviewed"),
            )
        )
        assertions += 5
    if len(set(reviewed_evidence)) != 1:
        raise DocumentationError(
            "public-satellite reviewed repository, commit, and date must agree between "
            "release infrastructure and the generated HACS README template"
        )
    expected_reviewed_evidence = (
        "theaussiepom/zigbeelens-hacs",
        "050d118b3e1406343255594fe64cd569e2420888",
        "2026-07-23",
    )
    if reviewed_evidence[0] != expected_reviewed_evidence:
        raise DocumentationError(
            "public-satellite historical evidence must remain coupled to the "
            "repository, commit, and review date actually inspected"
        )
    assertions += 2
    manifest = json.loads(
        (
            ROOT
            / "apps/ha_integration/custom_components/zigbeelens/manifest.json"
        ).read_text(encoding="utf-8")
    )
    expected_documentation = (
        "https://github.com/theaussiepom/zigbeelens/blob/main/docs/hacs.md"
    )
    if manifest.get("documentation") != expected_documentation:
        raise DocumentationError(
            "Home Assistant manifest documentation must point to the "
            "monorepo's current HACS status guide"
        )
    hacs_generator = (ROOT / "scripts/package-hacs-repo.sh").read_text(
        encoding="utf-8"
    )
    assertions += require_text_fragments(
        "scripts/package-hacs-repo.sh tree-exact staged-package provenance",
        hacs_generator,
        (
            "ZIGBEELENS_SOURCE_COMMIT",
            "ZIGBEELENS_SOURCE_REPOSITORY",
            "ZIGBEELENS_FUTURE_HACS_REPOSITORY",
            'rev-parse --show-toplevel',
            "rev-parse --verify 'HEAD^{commit}'",
            "cat-file -e",
            "diff --quiet",
            "ls-files --others --exclude-standard",
            "git -C",
            "archive",
            "SOURCE_COMMIT_VALUE",
            '${#SOURCE_COMMIT_VALUE}',
            "*[!0-9a-f]*",
            '"${DIST}/SOURCE_COMMIT"',
            "@SOURCE_REPOSITORY@",
            "@FUTURE_HACS_REPOSITORY@",
            "@REVIEWED_HACS_REPOSITORY@",
            "@SOURCE_COMMIT@",
            "docs/hacs.md",
        ),
    )
    hacs_template = (
        ROOT / "release/zigbeelens-hacs/README.md.in"
    ).read_text(encoding="utf-8")
    if "@GITHUB_OWNER@" in hacs_template:
        raise DocumentationError(
            "release/zigbeelens-hacs/README.md.in: GITHUB_OWNER must not "
            "conflate source, destination, and reviewed repository identities"
        )
    assertions += require_text_fragments(
        "release/zigbeelens-hacs/README.md.in repository identities",
        hacs_template,
        (
            "@SOURCE_REPOSITORY@",
            "@FUTURE_HACS_REPOSITORY@",
            "@REVIEWED_HACS_REPOSITORY@",
        ),
    )
    template_future_start = hacs_template.index(
        "## Conditional public HACS installation"
    )
    template_current = hacs_template[:template_future_start]
    template_future = hacs_template[template_future_start:]
    identity_classes = (
        (
            "Core repository link",
            re.findall(
                r"\[ZigbeeLens Core\]\((https://github\.com/[^)]+)\)",
                template_current,
            ),
            ["https://github.com/@SOURCE_REPOSITORY@"],
        ),
        (
            "Docker image",
            re.findall(r"`(ghcr\.io/[^`]+)`", template_current),
            ["ghcr.io/@SOURCE_REPOSITORY@"],
        ),
        (
            "package commit link",
            re.findall(
                r"\[[^\]]+\]\((https://github\.com/[^)\s]+/"
                r"commit/[^)\s]+)\)",
                template_current,
            ),
            [
                "https://github.com/@SOURCE_REPOSITORY@/"
                "commit/@SOURCE_COMMIT@"
            ],
        ),
        (
            "Issues link",
            re.findall(
                r"^Issues:\s*(\S+)\s*$",
                hacs_template,
                flags=re.MULTILINE,
            ),
            ["https://github.com/@SOURCE_REPOSITORY@/issues"],
        ),
        (
            "future HACS repository link",
            re.findall(
                r"`(https://github\.com/[^`\s]+)` as a HACS Integration",
                template_future,
            ),
            ["https://github.com/@FUTURE_HACS_REPOSITORY@"],
        ),
    )
    for label, actual, expected in identity_classes:
        if actual != expected:
            raise DocumentationError(
                "release/zigbeelens-hacs/README.md.in: expected exactly "
                f"one {label} owned by its declared identity; found {actual}"
            )
        assertions += 1
    assertions += 1
    assertions += require_document_fragments(
        "release/zigbeelens-hacs/scripts/validate-hacs-repo.sh",
        (
            "SOURCE_COMMIT",
            'r"[0-9a-f]{40}\\n"',
            'documentation_match.group("commit") != source_commit',
            "README package source commit does not match SOURCE_COMMIT",
            "README pinned documentation URL does not match manifest documentation",
            "README current/local guidance must not use blob/main documentation",
            "README pinned Docker documentation URL does not match",
            "theaussiepom/zigbeelens-hacs",
            "unresolved template placeholder",
        ),
    )
    assertions += require_document_fragments(
        "apps/core/tests/test_hacs_package_provenance.py",
        (
            "test_packager_derives_source_commit_from_git_head",
            "test_packager_normalizes_source_commit_override",
            "test_packager_rejects_invalid_source_commit_override",
            "test_packager_rejects_nonexistent_source_commit",
            "test_packager_rejects_different_existing_source_commit",
            "test_packager_rejects_dirty_integration_source",
            "test_packager_rejects_dirty_readme_template",
            "test_packager_rejects_untracked_integration_source",
            "test_packager_separates_nondefault_repository_identities",
            "test_package_validator_rejects_source_commit_mismatch",
        ),
    )
    assertions += require_document_fragments(
        "scripts/run-release-checks.sh",
        (
            "set -euo pipefail",
            "bash scripts/package-hacs-repo.sh",
            "bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh",
        ),
    )
    assertions += 1
    assertions += require_document_fragments(
        "apps/addon/zigbeelens/README.md",
        (
            "source-built add-on runner",
            "generated image-based repository",
            "optional API-token propagation",
            "UID-1000 `/data` writability",
            "reporting schema/default/unused-control alignment",
            "portable HACS-to-Core origin",
        ),
    )
    assertions += require_document_fragments(
        "scripts/package-addon-repo.sh",
        (
            "generated repository publication blocked",
            "not a supported release install",
            "conditional install after publication",
            "source-built runner",
        ),
    )
    generator = (ROOT / "scripts/package-addon-repo.sh").read_text(encoding="utf-8")
    if re.search(
        r"(?:the add-on / Ingress|Supervisor Ingress) is the supported",
        generator,
        flags=re.IGNORECASE,
    ):
        raise DocumentationError(
            "scripts/package-addon-repo.sh: generated add-on README contains "
            "an unqualified supported-route claim while publication is blocked"
        )
    assertions += 1
    return assertions


def validate_release_document_ownership() -> int:
    embedded = (ROOT / "docs/hacs-embedded-view.md").read_text(encoding="utf-8")
    status_index = embedded.find(
        "## Release status — local/staged integration only"
    )
    operational_index = embedded.find("## Lens family — embedded view decision tree")
    first_option_index = embedded.find("## Option A")
    if (
        status_index < 0
        or operational_index < 0
        or first_option_index < 0
        or not status_index < operational_index < first_option_index
    ):
        raise DocumentationError(
            "docs/hacs-embedded-view.md: local/staged release status must "
            "precede operational guidance"
        )
    option_labels = re.findall(
        r"^## Option ([A-Z])\b", embedded, flags=re.MULTILINE
    )
    if option_labels != ["A", "B", "C", "D"]:
        raise DocumentationError(
            "docs/hacs-embedded-view.md: option headings must be unique and "
            f"sequential A-D, found {option_labels}"
        )

    assertions = 2
    assertions += require_document_fragments(
        "docs/hacs-embedded-view.md",
        (
            "public HACS satellite is not the reviewed staged package",
            "future public HACS artifact",
            "synchronization, version, validation, and explicit-publication gates",
            "HACS integration release status",
            "native companion experience",
            "non-embedded companion path",
        ),
    )
    assertions += require_document_fragments(
        "docs/release.md",
        (
            "The current portable route is unconditional",
            "Fresh released Docker install",
            "If an add-on artifact was included and published",
            "If the HACS integration was synchronized and published",
        ),
    )
    assertions += require_document_fragments(
        "RELEASE_CHECKLIST.md",
        (
            "### Structural companion-package validation",
            "does **not** establish publication readiness",
            "## HACS publication readiness and live gates",
            "## Add-on publication readiness and live package gates",
            "If HACS was included and published",
            "If an add-on was included and published",
        ),
    )

    strict_command = (
        "ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 bash scripts/validate-compose.sh"
    )
    strict_callers = (
        "scripts/run-release-checks.sh",
        ".github/workflows/ci.yml",
        ".github/workflows/release-check.yml",
    )
    for relative in strict_callers:
        if strict_command not in (ROOT / relative).read_text(encoding="utf-8"):
            raise DocumentationError(
                f"{relative}: release/CI Compose validation must be strict"
            )
        assertions += 1

    assertions += require_document_fragments(
        "scripts/validate-compose.sh",
        (
            "ZIGBEELENS_REQUIRE_DOCKER_COMPOSE",
            "Docker/Compose source checks passed; rendering not run",
            "Docker/Compose validation passed",
        ),
    )
    strict_document_command = (
        "ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 ./scripts/validate-compose.sh"
    )
    for relative in ("RELEASE_CHECKLIST.md", "docs/release.md"):
        if strict_document_command not in (ROOT / relative).read_text(
            encoding="utf-8"
        ):
            raise DocumentationError(
                f"{relative}: strict Compose release command is missing"
            )
        assertions += 1
    return assertions


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
        "recommended HACS install heading": (
            r"^## Install via HACS \(recommended\)\s*$"
        ),
        "recommended HACS comparison row": r"^\|\s*Recommended default\s*\|",
        "stale UI safety skip claim": (
            r"`test_ui_has_no_repair_controls` (?:currently|unintentionally) skips"
        ),
        "unqualified blocked add-on support claim": (
            r"(?:the add-on / Ingress|Supervisor Ingress) is the supported"
        ),
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
            "`apps/ui/src`",
            "never a skip",
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
        + validate_docker_install_truth()
        + validate_addon_operational_truth()
        + validate_hacs_proxy_image_truth()
        + validate_shared_package_test_truth()
        + validate_companion_publication_truth()
        + validate_release_document_ownership()
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
