#!/usr/bin/env python3
"""Narrow release-documentation validation.

Checks tracked Markdown links/anchors, parses maintained JSON/YAML examples,
validates canonical Core configuration examples with production models, and
seals a few high-risk public documentation contracts.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import struct
import subprocess
import sys
import unicodedata
import zlib
from collections import Counter
from datetime import date
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin
from urllib.parse import unquote, urlsplit

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


SCREENSHOT_MANIFEST = Path("docs/screenshots/manifest.json")
SCREENSHOT_DIRECTORY = Path("docs/screenshots")
PHASE_7C2_CAPTURE_SOURCE_SHA = "af04ee906b71de77ee6e0eb5d866c0647d502410"
SCREENSHOT_CAPTION_PREFIX = "Illustrative synthetic release-candidate data."
SCREENSHOT_PREFERRED_MAX_BYTES = 500 * 1024
SCREENSHOT_HARD_MAX_BYTES = 750 * 1024
SCREENSHOT_DEFAULT_WIDTH = 1440
SCREENSHOT_DEFAULT_HEIGHT = 900
SCREENSHOT_HOME_ASSISTANT_VERSION = "2026.7.3"
PNG_DECODE_MAX_BYTES = 100_000_000
SCREENSHOT_ASSETS: dict[str, tuple[str, str]] = {
    "overview-dashboard.png": ("core", "README.md"),
    "mesh-investigate.png": ("core", "docs/topology.md"),
    "device-detail-history.png": ("core", "docs/topology.md"),
    "incidents-page.png": ("core", "docs/troubleshooting.md"),
    "reports-page.png": ("core", "docs/reports.md"),
    "report-contextual-create.png": ("core", "docs/reports.md"),
    "hacs-config-flow.png": ("home_assistant", "docs/hacs.md"),
    "hacs-companion-panel.png": ("home_assistant", "docs/hacs.md"),
    "hacs-embedded-blocked.png": (
        "home_assistant",
        "docs/hacs-embedded-view.md",
    ),
}
SCREENSHOT_EXACT_ROUTE_STATES = {
    "incidents-page.png": (
        "Core Incident detail for the deterministic synthetic Study Lamp "
        "availability incident with resolved status, recorded severity Incident, "
        "recorded confidence High, evidence, counter-evidence, interpretation, "
        "and limitations"
    ),
    "reports-page.png": (
        "Core Reports saved-report collection with a generated synthetic report, "
        "current scope/format/redaction metadata, and saved-report actions"
    ),
    "hacs-config-flow.png": (
        "Home Assistant ZigbeeLens initial config flow before submission with "
        "synthetic Core URL, blank token, TLS verification, and companion-panel "
        "ownership"
    ),
}
SCREENSHOT_TOP_LEVEL_FIELDS = {
    "screenshot_manifest_version",
    "capture_source_sha",
    "release_candidate_version",
    "capture_date",
    "data_classification",
    "contains_real_device_identifiers",
    "capture_provenance_note",
    "assets",
}
SCREENSHOT_ASSET_FIELDS = {
    "filename",
    "surface_owner",
    "route_or_state",
    "data_source",
    "capture_source_sha",
    "width",
    "height",
    "device_scale_factor",
    "zoom_percent",
    "theme",
    "byte_size",
    "sha256",
    "format",
    "capture_method",
    "identifier_presentation",
    "privacy_review",
    "visual_review",
    "documentation_destinations",
}
SCREENSHOT_ASSET_OPTIONAL_FIELDS = {
    "capture_exception_rationale",
    "size_exception_rationale",
}
SCREENSHOT_HOME_ASSISTANT_FIELDS = {
    "hacs_package_source_sha",
    "hacs_package_origin",
    "public_hacs_satellite_used",
    "home_assistant_version",
}
SCREENSHOT_IDENTIFIER_PRESENTATIONS = {
    "full_synthetic_fixture",
    "application_abbreviated",
    "not_visible",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_FORBIDDEN_METADATA_CHUNKS = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}
PNG_ALLOWED_CRITICAL_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
# Canonical screenshots are opaque RGB captures. Retain only the fixed,
# one-byte standard rendering-intent marker; broader ancillary chunks are
# unnecessary here and can carry private/profile metadata.
PNG_ALLOWED_ANCILLARY_CHUNKS = {b"sRGB"}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_ALLOWED_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}
PNG_ADAM7_PASSES = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _path_label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json_without_duplicate_keys(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DocumentationError(
                    f"{path.relative_to(path.parents[2])}: duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except OSError as exc:
        raise DocumentationError(f"cannot read screenshot manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DocumentationError(f"invalid screenshot manifest JSON: {exc}") from exc


def _png_passes(
    width: int,
    height: int,
    interlace: int,
) -> list[tuple[int, int]]:
    if interlace == 0:
        return [(width, height)]
    passes: list[tuple[int, int]] = []
    for x_start, y_start, x_step, y_step in PNG_ADAM7_PASSES:
        pass_width = (
            0 if width <= x_start else (width - x_start + x_step - 1) // x_step
        )
        pass_height = (
            0 if height <= y_start else (height - y_start + y_step - 1) // y_step
        )
        if pass_width and pass_height:
            passes.append((pass_width, pass_height))
    return passes


def _validate_png_scanlines(
    path: Path,
    compressed: bytes,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace: int,
) -> None:
    label = _path_label(path)
    channels = PNG_CHANNELS[color_type]
    passes = _png_passes(width, height, interlace)
    rows = [
        ((pass_width * channels * bit_depth + 7) // 8, pass_height)
        for pass_width, pass_height in passes
    ]
    expected_size = sum((row_bytes + 1) * pass_height for row_bytes, pass_height in rows)
    # Canonical documentation images are modest. Fail before decompression if a
    # malformed IHDR claims an unreasonable decoded allocation.
    if expected_size > PNG_DECODE_MAX_BYTES:
        raise DocumentationError(
            f"{label}: decoded PNG exceeds the 100 MB safety limit"
        )

    try:
        decompressor = zlib.decompressobj()
        # The exact decoded scanline size is the allocation budget. Never call
        # flush() or drain unconsumed input: either could inflate attacker-owned
        # data after the bound has been reached.
        decoded = decompressor.decompress(compressed, expected_size)
    except zlib.error as exc:
        raise DocumentationError(
            f"{label}: IDAT zlib stream does not decode: {exc}"
        ) from exc
    if decompressor.unconsumed_tail:
        raise DocumentationError(
            f"{label}: decoded PNG exceeds its exact scanline budget"
        )
    if not decompressor.eof:
        raise DocumentationError(f"{label}: IDAT zlib stream is truncated")
    if decompressor.unused_data:
        raise DocumentationError(
            f"{label}: IDAT zlib stream has trailing data"
        )
    if len(decoded) != expected_size:
        raise DocumentationError(
            f"{label}: decoded PNG scanline size is {len(decoded)}, "
            f"expected {expected_size}"
        )

    offset = 0
    for row_bytes, pass_height in rows:
        for _ in range(pass_height):
            filter_type = decoded[offset]
            if filter_type > 4:
                raise DocumentationError(
                    f"{label}: invalid PNG filter {filter_type}"
                )
            offset += row_bytes + 1


def parse_png(path: Path) -> tuple[int, int, tuple[str, ...]]:
    """Decode enough PNG structure and image data to seal documentation assets."""
    label = _path_label(path)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise DocumentationError(f"cannot read {path}: {exc}") from exc
    if not payload.startswith(PNG_SIGNATURE):
        raise DocumentationError(f"{label}: invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    saw_iend = False
    while offset < len(payload):
        if saw_iend:
            raise DocumentationError(f"{label}: data appears after PNG IEND")
        if len(payload) - offset < 12:
            raise DocumentationError(f"{label}: truncated PNG chunk header")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            raise DocumentationError(
                f"{label}: truncated {chunk_type!r} PNG chunk"
            )
        chunk_data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(
            ">I", payload[offset + 8 + length : chunk_end]
        )[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise DocumentationError(
                f"{label}: invalid CRC for {chunk_type!r}"
            )
        if chunk_type in PNG_FORBIDDEN_METADATA_CHUNKS:
            raise DocumentationError(
                f"{label}: forbidden PNG metadata chunk "
                f"{chunk_type.decode('ascii', errors='replace')}"
            )
        ancillary = bool(chunk_type[0] & 0x20)
        if ancillary and chunk_type not in PNG_ALLOWED_ANCILLARY_CHUNKS:
            raise DocumentationError(
                f"{label}: unsupported ancillary PNG chunk "
                f"{chunk_type.decode('ascii', errors='replace')}; "
                "metadata-bearing private chunks are not allowed"
            )
        if chunk_type == b"sRGB" and (
            len(chunk_data) != 1 or chunk_data[0] not in range(4)
        ):
            raise DocumentationError(f"{label}: invalid PNG sRGB rendering intent")
        if not ancillary and chunk_type not in PNG_ALLOWED_CRITICAL_CHUNKS:
            raise DocumentationError(
                f"{label}: unsupported critical PNG chunk {chunk_type!r}"
            )
        chunks.append((chunk_type, chunk_data))
        saw_iend = chunk_type == b"IEND"
        offset = chunk_end

    if not chunks or chunks[0][0] != b"IHDR":
        raise DocumentationError(f"{label}: IHDR must be first")
    if len(chunks[0][1]) != 13:
        raise DocumentationError(f"{label}: PNG IHDR must contain 13 bytes")
    chunk_types = [chunk_type for chunk_type, _ in chunks]
    if chunk_types.count(b"IHDR") != 1:
        raise DocumentationError(f"{label}: PNG must contain exactly one IHDR")
    if chunk_types.count(b"IEND") != 1 or chunk_types[-1] != b"IEND":
        raise DocumentationError(f"{label}: PNG must end with exactly one IEND")
    if b"IDAT" not in chunk_types:
        raise DocumentationError(f"{label}: PNG has no IDAT data")
    if chunk_types.count(b"sRGB") > 1:
        raise DocumentationError(f"{label}: PNG must contain at most one sRGB chunk")
    if (
        b"sRGB" in chunk_types
        and chunk_types.index(b"sRGB") > chunk_types.index(b"IDAT")
    ):
        raise DocumentationError(f"{label}: PNG sRGB must precede IDAT")
    if (
        b"sRGB" in chunk_types
        and b"PLTE" in chunk_types
        and chunk_types.index(b"sRGB") > chunk_types.index(b"PLTE")
    ):
        raise DocumentationError(f"{label}: PNG sRGB must precede PLTE")
    if chunk_types.count(b"PLTE") > 1:
        raise DocumentationError(f"{label}: PNG must contain at most one PLTE")
    if chunks[-1][1]:
        raise DocumentationError(f"{label}: PNG IEND must be empty")
    idat_indexes = [
        index for index, chunk_type in enumerate(chunk_types) if chunk_type == b"IDAT"
    ]
    if idat_indexes != list(range(idat_indexes[0], idat_indexes[-1] + 1)):
        raise DocumentationError(f"{label}: PNG IDAT chunks must be consecutive")

    width, height, bit_depth, color_type, compression, filtering, interlace = (
        struct.unpack(">IIBBBBB", chunks[0][1])
    )
    if width <= 0 or height <= 0:
        raise DocumentationError(f"{label}: PNG dimensions must be positive")
    if color_type not in PNG_CHANNELS:
        raise DocumentationError(
            f"{label}: unsupported PNG color type {color_type}"
        )
    if bit_depth not in PNG_ALLOWED_BIT_DEPTHS[color_type]:
        raise DocumentationError(
            f"{label}: invalid bit depth {bit_depth} for PNG color type {color_type}"
        )
    if compression != 0 or filtering != 0 or interlace not in {0, 1}:
        raise DocumentationError(
            f"{label}: invalid PNG compression/filter/interlace"
        )
    if color_type == 3 and b"PLTE" not in chunk_types:
        raise DocumentationError(f"{label}: indexed PNG is missing PLTE")
    if b"PLTE" in chunk_types:
        palette_index = chunk_types.index(b"PLTE")
        if palette_index > idat_indexes[0]:
            raise DocumentationError(f"{label}: PNG PLTE must precede IDAT")
        palette = chunks[palette_index][1]
        if not palette or len(palette) % 3 or len(palette) > 768:
            raise DocumentationError(f"{label}: invalid PNG PLTE length")

    compressed = b"".join(
        chunk_data
        for chunk_type, chunk_data in chunks
        if chunk_type == b"IDAT"
    )
    _validate_png_scanlines(
        path,
        compressed,
        width,
        height,
        bit_depth,
        color_type,
        interlace,
    )
    return width, height, tuple(
        chunk_type.decode("ascii", errors="replace") for chunk_type in chunk_types
    )


def _manifest_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [
            string
            for item in value
            for string in _manifest_string_values(item)
        ]
    if isinstance(value, dict):
        return [
            string
            for item in value.values()
            for string in _manifest_string_values(item)
        ]
    return []


def _manifest_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            key
            for item_key, item_value in value.items()
            for key in (str(item_key), *_manifest_keys(item_value))
        ]
    if isinstance(value, list):
        return [key for item in value for key in _manifest_keys(item)]
    return []


SCREENSHOT_APPROVED_ORIGINS = {
    "https://zigbeelens.example.test": (
        "https",
        "zigbeelens.example.test",
    ),
    "http://core.zigbeelens.test": (
        "http",
        "core.zigbeelens.test",
    ),
}
SCREENSHOT_APPROVED_BARE_HOSTS = {
    host for _, host in SCREENSHOT_APPROVED_ORIGINS.values()
}
SCREENSHOT_APPROVED_DOTTED_LITERALS = {
    "0.1.14",
    SCREENSHOT_HOME_ASSISTANT_VERSION,
}
NETWORK_URL_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9+.-])"
    r"(?:[a-z][a-z0-9+.-]*:)?//"
    r"[^\s<>(){}\"',;]+"
)
NETWORK_DOTTED_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9_.-])"
    r"(?:[a-z0-9_%:-]+\.)+[a-z0-9_%:-]+\.?"
    r"(?![a-z0-9_.-])"
)
NETWORK_IPV6_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9])"
    r"\[?(?:[0-9a-f]{0,4}:){2,}[0-9a-f:.%]*\]?"
    r"(?![a-z0-9])"
)


def _approved_origin(token: str) -> bool:
    expected = SCREENSHOT_APPROVED_ORIGINS.get(token)
    if expected is None:
        return False
    try:
        parsed = urlsplit(token)
        port = parsed.port
    except ValueError:
        return False
    expected_scheme, expected_host = expected
    return (
        parsed.scheme == expected_scheme
        and parsed.hostname == expected_host
        and parsed.netloc == expected_host
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
    )


def _has_forbidden_network_reference(value: str) -> bool:
    """Allow only exact approved origins or bare hosts; reject bypass spellings."""
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    ):
        return True
    normalized_unicode = unicodedata.normalize("NFKC", value)
    if normalized_unicode != value and any(
        marker in normalized_unicode for marker in (".", ":", "/", "\\", "@")
    ):
        return True
    if any(ord(character) > 127 for character in value) and any(
        marker in value for marker in (".", ":", "/", "\\", "@")
    ):
        return True
    stripped = value.strip().lower()
    if re.fullmatch(r"\d{1,10}", stripped) and int(stripped, 10) <= 2**32 - 1:
        return True
    if re.fullmatch(r"0x[0-9a-f]{1,8}", stripped) and int(stripped, 16) <= 2**32 - 1:
        return True
    if re.fullmatch(r"0[0-7]{1,11}", stripped) and int(stripped, 8) <= 2**32 - 1:
        return True
    if re.search(r"%[0-9a-f]{2}", value, flags=re.IGNORECASE):
        return True
    if any(
        character in value
        for character in ("\u2024", "\u3002", "\uff0e", "\uff61", "\uff0f", "\uff1a", "\uff20")
    ):
        return True
    if "@" in value or re.search(
        r"(?i)\b[a-z][a-z0-9+.-]*:\\", value
    ):
        return True

    remainder = list(value)
    for match in NETWORK_URL_PATTERN.finditer(value):
        token = match.group(0)
        if not _approved_origin(token):
            return True
        remainder[match.start() : match.end()] = " " * len(token)
    without_urls = "".join(remainder)

    for match in NETWORK_DOTTED_PATTERN.finditer(without_urls):
        token = match.group(0)
        if token in SCREENSHOT_APPROVED_DOTTED_LITERALS:
            continue
        if token not in SCREENSHOT_APPROVED_BARE_HOSTS:
            return True
        before = without_urls[match.start() - 1 : match.start()]
        after = without_urls[match.end() : match.end() + 1]
        if before in {"/", ":", "@"} or after in {"/", "?", "#", ":", "@", "\\"}:
            return True

    if NETWORK_IPV6_PATTERN.search(without_urls):
        return True
    if re.search(r"(?i)\blocalhost\b", without_urls):
        return True
    if re.search(r"(?i)\b0x[0-9a-f]{7,8}\b", without_urls):
        return True
    if re.search(r"\b0[0-7]{8,11}\b", without_urls):
        return True
    for candidate in re.findall(
        r"(?i)(?<![0-9a-z])\d{8,10}(?![0-9a-z])",
        without_urls,
    ):
        if int(candidate) <= (2**32 - 1):
            return True
    # ipaddress closes uncommon but valid dotted and IPv6 spellings extracted
    # as standalone tokens; malformed network-like tokens already fail above.
    for candidate in re.findall(r"(?i)\[?[0-9a-f:.%]+\]?", without_urls):
        if not any(marker in candidate for marker in (".", ":")):
            continue
        try:
            ipaddress.ip_address(candidate.strip("[]").split("%", 1)[0])
        except ValueError:
            continue
        return True
    return False


def _normalized_manifest_key_parts(key: str) -> tuple[str, ...]:
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
    normalized = re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")
    return tuple(part for part in normalized.split("_") if part)


def _sensitive_manifest_key(key: str) -> bool:
    parts = _normalized_manifest_key_parts(key)
    sensitive_parts = {
        "apikey",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "host",
        "hostname",
        "key",
        "password",
        "passwd",
        "path",
        "port",
        "profile",
        "secret",
        "session",
        "token",
        "uri",
        "url",
    }
    if sensitive_parts.intersection(parts):
        return True
    compact = "".join(parts)
    sensitive_suffixes = (
        "cookie",
        "credential",
        "credentials",
        "hostname",
        "password",
        "passwd",
        "profile",
        "secret",
        "session",
        "token",
    )
    if compact.endswith(sensitive_suffixes):
        return True
    return compact.endswith("port") and compact not in {"transport", "viewport"}


def _validate_manifest_privacy(manifest: dict[str, object], errors: list[str]) -> None:
    approved_dotted_values = set(SCREENSHOT_ASSETS)
    approved_dotted_values.update(
        destination for _, destination in SCREENSHOT_ASSETS.values()
    )
    approved_dotted_values.update(SCREENSHOT_APPROVED_DOTTED_LITERALS)
    strings = [
        value
        for value in _manifest_string_values(manifest)
        if value not in approved_dotted_values
    ]
    serialized = "\n".join((*strings, *_manifest_keys(manifest)))
    if any(
        _has_forbidden_network_reference(value)
        for value in (*strings, *_manifest_keys(manifest))
    ):
        errors.append("screenshot manifest stores forbidden URL/hostname")
    forbidden_values = {
        "complete IEEE address": (
            r"(?i)\b0x[0-9a-f]{16}\b|"
            r"\b(?:[0-9a-f]{2}[:-]){7}[0-9a-f]{2}\b"
        ),
        "absolute filesystem path": (
            r"(?i)(?:^|[\s\"'(])/(?:users|home|private|tmp|var|opt)/|"
            r"\b[a-z]:\\"
        ),
        "explicit port": r"(?<!\d):[0-9]{2,5}\b",
        "browser profile": r"(?i)\bbrowser[- ]profile\b",
        "cookie": r"(?i)\bcookie\b",
        "token value": r"(?i)\btoken\s*[:=]\s*[^\s,;]+",
    }
    for label, pattern in forbidden_values.items():
        if re.search(pattern, serialized, flags=re.MULTILINE):
            errors.append(f"screenshot manifest stores forbidden {label}")

    sensitive = sorted(
        {key for key in _manifest_keys(manifest) if _sensitive_manifest_key(key)}
    )
    if sensitive:
        errors.append(
            "screenshot manifest stores forbidden sensitive field(s): "
            + ", ".join(sensitive)
        )


def _next_nonempty_line(text: str, offset: int) -> str:
    for line in text[offset:].splitlines():
        if line.strip():
            return line.strip()
    return ""


def _validate_screenshot_markdown(
    markdown_files: list[Path],
    root: Path,
    errors: list[str],
) -> None:
    screenshot_directory = (root / SCREENSHOT_DIRECTORY).resolve()
    references: dict[str, list[tuple[str, str]]] = {
        filename: [] for filename in SCREENSHOT_ASSETS
    }
    image_pattern = re.compile(r"!\[([^\]]*)]\(([^)]+)\)")

    for source in markdown_files:
        text = strip_fenced_blocks(source.read_text(encoding="utf-8"))
        for match in image_pattern.finditer(text):
            alt = match.group(1).strip()
            destination = link_destination(match.group(2))
            if not destination or re.match(
                r"^(?:https?|data):", destination, flags=re.IGNORECASE
            ):
                continue
            path_part = unquote(destination.partition("#")[0])
            target = (source.parent / path_part).resolve()
            try:
                screenshot_relative = target.relative_to(screenshot_directory)
            except ValueError:
                continue
            filename = screenshot_relative.as_posix()
            source_relative = source.relative_to(root).as_posix()
            if filename not in SCREENSHOT_ASSETS:
                errors.append(
                    f"{source_relative}: obsolete or unapproved screenshot "
                    f"reference {filename!r}"
                )
                continue
            references[filename].append((source_relative, alt))

            normalized_alt = " ".join(alt.split()).lower()
            if (
                not normalized_alt
                or normalized_alt == "screenshot"
                or normalized_alt == filename.lower()
                or normalized_alt == Path(filename).stem.lower()
            ):
                errors.append(
                    f"{source_relative}: {filename} needs meaningful alt text"
                )
            caption = _next_nonempty_line(text, match.end())
            if not caption.startswith(SCREENSHOT_CAPTION_PREFIX):
                errors.append(
                    f"{source_relative}: {filename} must have an immediate caption "
                    f"starting {SCREENSHOT_CAPTION_PREFIX!r}"
                )

    for filename, (_, expected_destination) in SCREENSHOT_ASSETS.items():
        found = references[filename]
        if len(found) != 1:
            errors.append(
                f"{filename}: expected exactly one approved Markdown embed, "
                f"found {len(found)}"
            )
            continue
        found_destination, _ = found[0]
        if found_destination != expected_destination:
            errors.append(
                f"{filename}: Markdown destination must be {expected_destination}, "
                f"found {found_destination}"
            )


def validate_screenshot_manifest(
    markdown_files: list[Path],
    root: Path = ROOT,
) -> int:
    manifest_path = root / SCREENSHOT_MANIFEST
    if not manifest_path.is_file():
        raise DocumentationError(
            f"missing screenshot manifest: {SCREENSHOT_MANIFEST.as_posix()}"
        )
    loaded = _load_json_without_duplicate_keys(manifest_path)
    if not isinstance(loaded, dict):
        raise DocumentationError("screenshot manifest root must be an object")
    manifest: dict[str, object] = loaded
    errors: list[str] = []

    missing_top_level = sorted(SCREENSHOT_TOP_LEVEL_FIELDS - manifest.keys())
    extra_top_level = sorted(manifest.keys() - SCREENSHOT_TOP_LEVEL_FIELDS)
    if missing_top_level:
        errors.append(
            "screenshot manifest missing top-level field(s): "
            + ", ".join(missing_top_level)
        )
    if extra_top_level:
        errors.append(
            "screenshot manifest has unapproved top-level field(s): "
            + ", ".join(extra_top_level)
        )
    if not (
        _is_plain_int(manifest.get("screenshot_manifest_version"))
        and manifest.get("screenshot_manifest_version") == 1
    ):
        errors.append("screenshot_manifest_version must be integer 1")
    capture_sha = manifest.get("capture_source_sha")
    if not isinstance(capture_sha, str) or not re.fullmatch(
        r"[0-9a-f]{40}", capture_sha
    ):
        errors.append("capture_source_sha must be 40 lowercase hexadecimal characters")
    elif capture_sha != PHASE_7C2_CAPTURE_SOURCE_SHA:
        errors.append(
            "capture_source_sha must match the accepted Phase 7C2 runtime source "
            f"{PHASE_7C2_CAPTURE_SOURCE_SHA}"
        )

    try:
        repository_version = json.loads(
            (root / "package.json").read_text(encoding="utf-8")
        )["version"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read repository version from package.json: {exc}")
        repository_version = None
    if manifest.get("release_candidate_version") != repository_version:
        errors.append(
            "release_candidate_version must equal the repository version "
            f"{repository_version!r}"
        )
    if repository_version != "0.1.14":
        errors.append("Phase 7C2 repository version must remain 0.1.14")

    capture_date = manifest.get("capture_date")
    try:
        parsed_date = date.fromisoformat(capture_date)  # type: ignore[arg-type]
        if parsed_date.isoformat() != capture_date:
            raise ValueError("non-canonical ISO date")
    except (TypeError, ValueError):
        errors.append("capture_date must be a canonical YYYY-MM-DD date")
    if manifest.get("data_classification") != "synthetic":
        errors.append("data_classification must be synthetic")
    if manifest.get("contains_real_device_identifiers") is not False:
        errors.append("contains_real_device_identifiers must be false")
    provenance_note = manifest.get("capture_provenance_note")
    if not isinstance(provenance_note, str) or not all(
        fragment in provenance_note.lower()
        for fragment in ("capture_source_sha", "final documentation commit", "not runtime")
    ):
        errors.append(
            "capture_provenance_note must explain capture runtime versus final "
            "documentation provenance"
        )
    _validate_manifest_privacy(manifest, errors)

    assets = manifest.get("assets")
    if not isinstance(assets, list):
        errors.append("screenshot manifest assets must be a list")
        assets = []
    manifest_names = [
        asset.get("filename")
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("filename"), str)
    ]
    counts = Counter(manifest_names)
    duplicate_names = sorted(name for name, count in counts.items() if count != 1)
    if duplicate_names:
        errors.append(
            "screenshot manifest filenames must appear exactly once: "
            + ", ".join(duplicate_names)
        )
    manifest_inventory = set(manifest_names)
    missing_assets = sorted(set(SCREENSHOT_ASSETS) - manifest_inventory)
    extra_assets = sorted(manifest_inventory - set(SCREENSHOT_ASSETS))
    if missing_assets:
        errors.append("screenshot manifest missing: " + ", ".join(missing_assets))
    if extra_assets:
        errors.append("screenshot manifest has unapproved assets: " + ", ".join(extra_assets))
    malformed_assets = sum(not isinstance(asset, dict) for asset in assets)
    if malformed_assets:
        errors.append(f"screenshot manifest has {malformed_assets} non-object asset(s)")

    screenshots_root = root / SCREENSHOT_DIRECTORY
    approved_directory_entries = {
        "README.md",
        SCREENSHOT_MANIFEST.name,
        *SCREENSHOT_ASSETS,
    }
    actual_entries = {
        path.relative_to(screenshots_root).as_posix()
        for path in screenshots_root.rglob("*")
    }
    actual_files = {
        path.relative_to(screenshots_root).as_posix()
        for path in screenshots_root.rglob("*")
        if path.is_file()
    }
    unexpected_entries = sorted(actual_entries - approved_directory_entries)
    missing_files = sorted(set(SCREENSHOT_ASSETS) - actual_files)
    if unexpected_entries:
        errors.append(
            "unmanifested screenshot directory entry(s): "
            + ", ".join(unexpected_entries)
        )
    if missing_files:
        errors.append("missing screenshot image(s): " + ", ".join(missing_files))

    binary_owners: dict[str, list[str]] = {}
    for asset_object in assets:
        if not isinstance(asset_object, dict):
            continue
        asset: dict[str, object] = asset_object
        filename_value = asset.get("filename")
        if not isinstance(filename_value, str):
            errors.append("screenshot asset filename must be a string")
            continue
        filename = filename_value
        if Path(filename).name != filename or filename not in SCREENSHOT_ASSETS:
            errors.append(
                f"{filename}: filename must be an approved bare name relative "
                "to docs/screenshots"
            )
            continue
        required_fields = set(SCREENSHOT_ASSET_FIELDS)
        allowed_fields = required_fields | SCREENSHOT_ASSET_OPTIONAL_FIELDS
        expected_owner, expected_destination = SCREENSHOT_ASSETS[filename]
        if expected_owner == "home_assistant":
            required_fields |= SCREENSHOT_HOME_ASSISTANT_FIELDS
            allowed_fields |= SCREENSHOT_HOME_ASSISTANT_FIELDS
        missing_fields = sorted(required_fields - asset.keys())
        extra_fields = sorted(asset.keys() - allowed_fields)
        if missing_fields:
            errors.append(
                f"{filename}: missing manifest field(s): " + ", ".join(missing_fields)
            )
        if extra_fields:
            errors.append(
                f"{filename}: unapproved manifest field(s): "
                + ", ".join(extra_fields)
            )
        if asset.get("surface_owner") != expected_owner:
            errors.append(f"{filename}: surface_owner must be {expected_owner}")
        for field in ("route_or_state", "data_source", "capture_method"):
            value = asset.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{filename}: {field} must be a nonempty string")
        exact_route_state = SCREENSHOT_EXACT_ROUTE_STATES.get(filename)
        if (
            exact_route_state is not None
            and asset.get("route_or_state") != exact_route_state
        ):
            errors.append(
                f"{filename}: route_or_state must exactly describe the accepted "
                f"surface as {exact_route_state!r}"
            )
        data_source = asset.get("data_source")
        if isinstance(data_source, str) and "synthetic" not in data_source.lower():
            errors.append(f"{filename}: data_source must disclose synthetic data")
        capture_method = asset.get("capture_method")
        if isinstance(capture_method, str) and not all(
            fragment in capture_method.lower() for fragment in ("real", "reduced motion")
        ):
            errors.append(
                f"{filename}: capture_method must record real UI capture "
                "with reduced motion"
            )
        asset_capture_sha = asset.get("capture_source_sha")
        if not isinstance(asset_capture_sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", asset_capture_sha
        ):
            errors.append(
                f"{filename}: capture_source_sha must be 40 lowercase "
                "hexadecimal characters"
            )
        if asset_capture_sha != capture_sha:
            errors.append(f"{filename}: capture_source_sha differs from manifest")

        if expected_owner == "home_assistant":
            hacs_contract = {
                "hacs_package_source_sha": capture_sha,
                "home_assistant_version": SCREENSHOT_HOME_ASSISTANT_VERSION,
                "hacs_package_origin": "local_repository_stage",
                "public_hacs_satellite_used": False,
            }
            for field, expected in hacs_contract.items():
                value = asset.get(field)
                if (
                    field == "public_hacs_satellite_used"
                    and value is not False
                ) or (
                    field != "public_hacs_satellite_used"
                    and value != expected
                ):
                    errors.append(f"{filename}: {field} must be {expected!r}")
        else:
            inappropriate = sorted(
                field
                for field in (
                    "hacs_package_source_sha",
                    "home_assistant_version",
                    "hacs_package_origin",
                    "public_hacs_satellite_used",
                )
                if field in asset
            )
            if inappropriate:
                errors.append(
                    f"{filename}: Core asset has Home Assistant provenance "
                    + ", ".join(inappropriate)
                )

        for field in ("width", "height", "byte_size", "zoom_percent"):
            if not _is_plain_int(asset.get(field)):
                errors.append(f"{filename}: {field} must be an integer")
        scale = asset.get("device_scale_factor")
        if not (
            (_is_plain_int(scale) or isinstance(scale, float))
            and not isinstance(scale, bool)
            and scale > 0
        ):
            errors.append(f"{filename}: device_scale_factor must be numeric")
        width = asset.get("width")
        height = asset.get("height")
        byte_size = asset.get("byte_size")
        zoom = asset.get("zoom_percent")
        if _is_plain_int(width) and width <= 0:
            errors.append(f"{filename}: width must be positive")
        if _is_plain_int(height) and height <= 0:
            errors.append(f"{filename}: height must be positive")
        if _is_plain_int(byte_size) and byte_size <= 0:
            errors.append(f"{filename}: byte_size must be positive")
        if scale != 1:
            errors.append(f"{filename}: device_scale_factor must be 1")
        if zoom != 100:
            errors.append(f"{filename}: zoom_percent must be 100")
        if asset.get("theme") != "production_default":
            errors.append(f"{filename}: theme must be production_default")

        exception_rationale = asset.get("capture_exception_rationale")
        if exception_rationale is not None and (
            not isinstance(exception_rationale, str)
            or not exception_rationale.strip()
        ):
            errors.append(
                f"{filename}: capture_exception_rationale must be nonempty"
            )
        if (
            width != SCREENSHOT_DEFAULT_WIDTH
            or height != SCREENSHOT_DEFAULT_HEIGHT
        ) and not (
            isinstance(exception_rationale, str) and exception_rationale.strip()
        ):
            errors.append(
                f"{filename}: non-default viewport requires "
                "capture_exception_rationale"
            )

        size_rationale = asset.get("size_exception_rationale")
        if size_rationale is not None and (
            not isinstance(size_rationale, str) or not size_rationale.strip()
        ):
            errors.append(f"{filename}: size_exception_rationale must be nonempty")
        if _is_plain_int(byte_size):
            if byte_size > SCREENSHOT_HARD_MAX_BYTES:
                errors.append(
                    f"{filename}: {byte_size} bytes exceeds the 750 KB hard maximum"
                )
            elif byte_size > SCREENSHOT_PREFERRED_MAX_BYTES and not (
                isinstance(size_rationale, str) and size_rationale.strip()
            ):
                errors.append(
                    f"{filename}: image over 500 KB requires "
                    "size_exception_rationale"
                )

        sha256 = asset.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            errors.append(f"{filename}: sha256 must be 64 lowercase hexadecimal characters")
        if asset.get("format") != "png":
            errors.append(f"{filename}: format must be png")
        identifier = asset.get("identifier_presentation")
        if identifier not in SCREENSHOT_IDENTIFIER_PRESENTATIONS:
            errors.append(
                f"{filename}: identifier_presentation must be one of "
                + ", ".join(sorted(SCREENSHOT_IDENTIFIER_PRESENTATIONS))
            )
        if asset.get("privacy_review") != "passed":
            errors.append(f"{filename}: privacy_review must be passed")
        if asset.get("visual_review") != "passed":
            errors.append(f"{filename}: visual_review must be passed")
        destinations = asset.get("documentation_destinations")
        if destinations != [expected_destination]:
            errors.append(
                f"{filename}: documentation_destinations must be "
                f"[{expected_destination!r}]"
            )

        asset_path = screenshots_root / filename
        if not asset_path.is_file():
            continue
        actual_payload = asset_path.read_bytes()
        actual_size = len(actual_payload)
        actual_sha = hashlib.sha256(actual_payload).hexdigest()
        binary_owners.setdefault(actual_sha, []).append(filename)
        if actual_size != byte_size:
            errors.append(
                f"{filename}: byte_size is {byte_size!r}, actual {actual_size}"
            )
        if actual_sha != sha256:
            errors.append(f"{filename}: sha256 does not match the image")
        try:
            actual_width, actual_height, _ = parse_png(asset_path)
        except DocumentationError as exc:
            errors.append(str(exc))
        else:
            if actual_width != width or actual_height != height:
                errors.append(
                    f"{filename}: manifest dimensions {width!r} x {height!r}, "
                    f"actual {actual_width} x {actual_height}"
                )

    duplicate_binaries = [
        filenames for filenames in binary_owners.values() if len(filenames) > 1
    ]
    for filenames in duplicate_binaries:
        errors.append("duplicate binary screenshot images: " + ", ".join(filenames))

    _validate_screenshot_markdown(markdown_files, root, errors)
    if errors:
        raise DocumentationError("\n".join(errors))
    return len(SCREENSHOT_ASSETS)


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


RELEASE_BLOCKER_STATUS_GUARDS: tuple[tuple[str, str, str], ...] = (
    (
        "hacs_main_commit",
        "docs/release.md",
        "public `main` was commit "
        "`21c24e3355369b94c9ab596cf9fc0591f1282297`",
    ),
    (
        "hacs_tree",
        "docs/release.md",
        "tree `9e33bcbf919cdc90eee37e6c3f635f6b6292fbc9`",
    ),
    (
        "hacs_source_commit",
        "docs/release.md",
        "`SOURCE_COMMIT` "
        "`906527063ad8bd594fbec51f69f6fc72205302dd`",
    ),
    (
        "hacs_no_tag_or_release",
        "docs/release.md",
        "no `v0.1.14` tag or release exists",
    ),
    (
        "hacs_stale_after_correction",
        "docs/release.md",
        "the public tree is stale again until a separately authorized "
        "resynchronization",
    ),
    (
        "public_installation_gated",
        "docs/release.md",
        "Public installation remains gated",
    ),
    (
        "rejected_digest_invalid",
        "docs/release.md",
        "GHCR manifest digest "
        "`sha256:8549c49bd3e0389def669ce2e6c14bcbe2b54c967a725fd6373f5d82921f6bc7` "
        "is rejected Phase 7D evidence",
    ),
    (
        "package_version_oci_metadata",
        "docs/release.md",
        "org.opencontainers.image.version=0.1.14",
    ),
    (
        "full_revision_oci_metadata",
        "docs/release.md",
        "org.opencontainers.image.revision=<full final source SHA>",
    ),
    (
        "canonical_source_oci_metadata",
        "docs/release.md",
        "org.opencontainers.image.source=https://github.com/theaussiepom/zigbeelens",
    ),
    (
        "schema_target_15",
        "docs/release.md",
        "The current schema target is `15`",
    ),
    (
        "migration_014_unchanged",
        "docs/release.md",
        "Migration `014_report_v3_only_reset.sql` remains unchanged",
    ),
    (
        "snapshot_parsed_json_null",
        "docs/safety-audit.md",
        "snapshot `parsed_json` is `NULL`",
    ),
    (
        "snapshot_typed_counts_preserved",
        "docs/safety-audit.md",
        "Normalized router, end-device, and link counts remain in their typed "
        "columns",
    ),
    (
        "screenshots_s1_s9_current",
        "docs/test-architecture.md",
        "the current S1–S9 evidence retains capture source "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`",
    ),
    (
        "screenshots_one_runtime_source",
        "docs/test-architecture.md",
        "all nine assets were captured together from one final corrected runtime",
    ),
    (
        "phase_7d_blocked",
        "docs/test-architecture.md",
        "Phase 7D live Beast validation remains blocked",
    ),
    (
        "addon_deferred",
        "docs/release.md",
        "The add-on is deferred and is not part of the current HACS release",
    ),
    (
        "phase_7c2_complete",
        "CHANGELOG.md",
        "Phase 7C2 is complete: PR #108 merged the one-source synthetic S1–S9 "
        "set captured from "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`",
    ),
    (
        "phase_7c2_pr_108_merged",
        "RELEASE_CHECKLIST.md",
        "PR #108's final reviewed head was "
        "`1ea2949ab09038cdfe94d1c6d6b8e5fd45d8d87f` and its evidence merge was "
        "`93fb26617042ed46d8920a7b75a42e3ae9da4d62`",
    ),
    (
        "phase_7c2_capture_source_exact",
        "README.md",
        "its evidence merge is "
        "`93fb26617042ed46d8920a7b75a42e3ae9da4d62`, and every image retains "
        "immutable runtime capture source "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`",
    ),
    (
        "review_inventory_resolved",
        "RELEASE_CHECKLIST.md",
        "The review inventory is resolved. Every listed item has merged fixing "
        "evidence, an exact reply or closure record, and a resolved thread "
        "where a thread exists",
    ),
    (
        "pr_107_review_closures",
        "RELEASE_CHECKLIST.md",
        "PR #107 closed its inventory at reviewed head "
        "`d4771860f155e8ecbe51d995ff729c8da6529c87`, merged as "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`",
    ),
    (
        "pr_108_s4_review_closed",
        "RELEASE_CHECKLIST.md",
        "| PR #108 `discussion_r3671437623` | Recorded severity `Incident` "
        "versus recorded confidence `High` | PR #108 / "
        "`93fb26617042ed46d8920a7b75a42e3ae9da4d62`; reply "
        "`discussion_r3672142130`; resolved |",
    ),
    (
        "pr_106_p1",
        "RELEASE_CHECKLIST.md",
        "| PR #106 `discussion_r3654140180` (P1) | PNG decompression bounds | "
        "PR #107 / `af04ee906b71de77ee6e0eb5d866c0647d502410`; reply "
        "`discussion_r3669046766`; resolved |",
    ),
    (
        "pr_106_p2",
        "RELEASE_CHECKLIST.md",
        "| PR #106 `discussion_r3654140181` (P2) | Screenshot privacy/schema "
        "parsing | PR #107 / "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`; reply "
        "`discussion_r3669047203`; resolved |",
    ),
    (
        "pr_100_mixed_case_ieee",
        "RELEASE_CHECKLIST.md",
        "| PR #100 `discussion_r3626646727` | Mixed-case IEEE topology lookup | "
        "PR #107 / `af04ee906b71de77ee6e0eb5d866c0647d502410`; reply "
        "`discussion_r3669047791`; resolved |",
    ),
    (
        "pr_97_coordinator_action",
        "RELEASE_CHECKLIST.md",
        "| PR #97 `discussion_r3618354267` | Coordinator action uses "
        "device-neutral copy | PR #107 / "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`; reply "
        "`discussion_r3669048273`; resolved |",
    ),
    (
        "delayed_approved_host_bypass",
        "RELEASE_CHECKLIST.md",
        "| Delayed approved-host integer/userinfo bypass | Exact-origin and "
        "bare-host parser bypass cases | PR #107 / "
        "`af04ee906b71de77ee6e0eb5d866c0647d502410`; "
        "[closure record]"
        "(https://github.com/theaussiepom/zigbeelens/pull/106"
        "#issuecomment-5109485498) |",
    ),
    (
        "changelog_exact_hacs_state",
        "CHANGELOG.md",
        "at `21c24e3355369b94c9ab596cf9fc0591f1282297` "
        "(tree `9e33bcbf919cdc90eee37e6c3f635f6b6292fbc9`, "
        "source `906527063ad8bd594fbec51f69f6fc72205302dd`)",
    ),
    (
        "changelog_hacs_stale_and_gated",
        "CHANGELOG.md",
        "It is stale for this correction until a separately authorized "
        "resynchronization; public installation remains gated",
    ),
)


CURRENT_RELEASE_STATUS_SCOPES: tuple[tuple[str, str, str, str], ...] = (
    (
        "changelog_unreleased",
        "CHANGELOG.md",
        "## [Unreleased]",
        "## [0.1.14]",
    ),
    (
        "readme_install_status",
        "README.md",
        "## Install",
        "## Using the UI",
    ),
    (
        "release_checklist_phase_status",
        "RELEASE_CHECKLIST.md",
        "## Phase 7 release status",
        "## Security acknowledgement",
    ),
    (
        "release_checklist_documentation_status",
        "RELEASE_CHECKLIST.md",
        "## Documentation",
        "## Packaging and publish",
    ),
    (
        "cursor_current_status",
        "docs/decision-engine-cursor-guardrails.md",
        "**Current status:**",
        "## Required starting prompt",
    ),
    (
        "cursor_phase_7c2_status",
        "docs/decision-engine-cursor-guardrails.md",
        "### Phase 7C2 — Screenshot and visual evidence",
        "### Phase 7D — Deployment validation",
    ),
    (
        "implementation_current_status",
        "docs/decision-engine-implementation-plan.md",
        "**Status:**",
        "## Purpose",
    ),
    (
        "implementation_phase_7c2_status",
        "docs/decision-engine-implementation-plan.md",
        "## Phase 7C2 — Screenshot and visual evidence",
        "## Phase 7D — Deployment validation",
    ),
    (
        "migration_current_status",
        "docs/decision-engine-migration.md",
        "**Current release status:**",
        "## Programme statement",
    ),
    (
        "migration_phase_7c2_status",
        "docs/decision-engine-migration.md",
        "### Phase 7C2 — Screenshot and visual evidence",
        "### Phase 7D — Deployment validation",
    ),
    (
        "migration_current_map",
        "docs/decision-engine-migration.md",
        "## Current migration map",
        "## Per-PR checklist",
    ),
    (
        "hacs_release_status",
        "docs/hacs.md",
        "## Release status — local/staged integration only",
        "## Local staged integration testing",
    ),
    (
        "lens_release_work_boundary",
        "docs/lens-alignment-status.md",
        "## Release-work boundary",
        "See:",
    ),
    (
        "release_infra_phase_status",
        "docs/release-infra.md",
        "## Release-quality phase status",
        "## Add-on publication status",
    ),
    (
        "release_test_phase_boundary",
        "docs/release-test.md",
        "## Phase 7 release boundary",
        "## Pre-flight checklist",
    ),
    (
        "release_prepare_branch",
        "docs/release.md",
        "### 1. Prepare branch",
        "### 2. Update version",
    ),
    (
        "release_review_inventory",
        "docs/release.md",
        "## Review-thread closure before release",
        "## Safety verification",
    ),
    (
        "reports_screenshot_status",
        "docs/reports.md",
        "# Reports",
        "## Current contract: exact ReportDetailV3",
    ),
    (
        "screenshots_current_evidence",
        "docs/screenshots/README.md",
        "# Canonical release-candidate screenshots",
        "## Canonical inventory",
    ),
    (
        "test_architecture_current_status",
        "docs/test-architecture.md",
        "# Test architecture (Phase 7B)",
        "## Layers",
    ),
    (
        "test_architecture_review_inventory",
        "docs/test-architecture.md",
        "## Pre-Phase-7D release-blocker ownership",
        "## Adding a new Decision code",
    ),
    (
        "topology_screenshot_status",
        "docs/topology.md",
        "## Current investigation surfaces",
        "## Product surfaces",
    ),
)

STALE_CURRENT_STATUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "status_closure_pending_merge",
        r"(?:"
        r"(?:this|the) status[- ]closure(?: pr)?\b.{0,160}"
        r"(?:(?:still )?(?:requires?|needs?|awaits?)\b.{0,80}(?:review|merge)"
        r"|is pending\b.{0,40}merge"
        r"|is independently reviewed\b.{0,80}(?:and )?merged\b)"
        r"|phase 7d\b.{0,160}(?:waits?|blocked)\b.{0,160}"
        r"(?:this|the) status[- ]closure(?: pr)?\b.{0,100}(?:review|merge)"
        r")",
    ),
    (
        "focused_screenshot_pr_pending",
        r"focused(?: phase 7c2)?(?: screenshot)? pr.{0,160}"
        r"(?:still (?:requires|needs)|gated (?:on|pending)).{0,200}"
        r"(?:independent review|remote ci|merge)",
    ),
    (
        "ready_for_independent_review",
        r"ready for independent review",
    ),
    (
        "local_screenshot_candidate_until_merge",
        r"local.{0,100}candidate.{0,240}"
        r"(?:until|pending|awaiting|review|ci|merge)",
    ),
    (
        "review_inventory_unresolved_future_pr",
        r"remain(?:s)? (?:unresolved|open).{0,180}"
        r"(?:future fixing pr|fixing pr|reply|resolve)",
    ),
    (
        "final_candidate_review_evidence",
        r"final-candidate review evidence",
    ),
    (
        "phase_7c2_awaiting_remote_gate",
        r"phase 7c2.{0,180}(?:awaiting|pending).{0,160}"
        r"(?:independent review|remote ci|pr merge|merge)",
    ),
    (
        "phase_7c2_incomplete",
        r"phase 7c2.{0,100}(?:is|remains) incomplete",
    ),
    (
        "phase_7c2_recapture_pending",
        r"phase 7c2.{0,180}(?:still )?"
        r"(?:requires|needs|requiring).{0,120}recaptur",
    ),
)

STALE_TOPOLOGY_PARSED_JSON_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        "legacy parsed_json reduced to counts",
        r"reduces? (?:legacy )?`parsed_json` to normalized counts",
    ),
    (
        "parsed_json limited to counts",
        r"`parsed_json` is limited to (?:the )?normalized",
    ),
    (
        "count-only parsed_json",
        r"(?:bounded )?count-only `parsed_json`",
    ),
    (
        "non-null parsed_json rebuild",
        r"rebuilds? (?:non-null )?(?:snapshot )?`parsed_json`",
    ),
)


def normalized_release_status_scope(
    relative: str, start_marker: str, end_marker: str
) -> str:
    text = (ROOT / relative).read_text(encoding="utf-8")
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)
    if start_count != 1 or end_count != 1:
        raise DocumentationError(
            f"{relative}: current release-status scope marker count must be "
            f"exactly one ({start_marker!r}: {start_count}; "
            f"{end_marker!r}: {end_count})"
        )
    start = text.index(start_marker)
    end = text.index(end_marker)
    if end <= start:
        raise DocumentationError(
            f"{relative}: current release-status scope markers are out of "
            f"order: {start_marker!r}..{end_marker!r}"
        )
    return " ".join(text[start:end].split())


def validate_release_blocker_status_truth() -> int:
    """Seal the exact pre-Phase-7D correction and review state."""
    normalized_by_file: dict[str, str] = {}
    missing: list[str] = []
    for label, relative, fragment in RELEASE_BLOCKER_STATUS_GUARDS:
        normalized = normalized_by_file.setdefault(
            relative, normalized_document(relative).lower()
        )
        if " ".join(fragment.split()).lower() not in normalized:
            missing.append(f"{relative}: {label}")
    if missing:
        raise DocumentationError(
            "missing pre-Phase-7D release status guard(s):\n- "
            + "\n- ".join(missing)
        )

    status_text = "\n".join(normalized_by_file.values())
    stale = [
        label
        for label, pattern in STALE_TOPOLOGY_PARSED_JSON_CLAIMS
        if re.search(pattern, status_text, flags=re.IGNORECASE)
    ]
    if stale:
        raise DocumentationError(
            "stale topology parsed_json release claim(s): " + ", ".join(stale)
        )

    stale_current: list[str] = []
    for scope, relative, start_marker, end_marker in CURRENT_RELEASE_STATUS_SCOPES:
        scoped_text = normalized_release_status_scope(
            relative, start_marker, end_marker
        )
        stale_current.extend(
            f"{scope}: {label}"
            for label, pattern in STALE_CURRENT_STATUS_PATTERNS
            if re.search(pattern, scoped_text, flags=re.IGNORECASE)
        )
    if stale_current:
        raise DocumentationError(
            "stale current Phase 7C2 status claim(s): "
            + ", ".join(stale_current)
        )

    return (
        len(RELEASE_BLOCKER_STATUS_GUARDS)
        + len(STALE_TOPOLOGY_PARSED_JSON_CLAIMS)
        + len(CURRENT_RELEASE_STATUS_SCOPES)
        * len(STALE_CURRENT_STATUS_PATTERNS)
    )


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
            "add-on is deferred and is not part of the current HACS release",
            "does not define a portable HACS-to-add-on Core origin",
            "Do not use `http://localhost:8377` as an add-on URL",
        ),
        "apps/ha_integration/README.md": (
            "add-on is deferred and is not part of this HACS release",
            "does not define a portable HACS-to-add-on backend URL",
            "Do not use `http://localhost:8377` as an add-on backend URL",
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
            "add-on is deferred and is not part of this HACS release",
            "`http://localhost:8377` is not a portable add-on URL",
            "Run standalone Core at a reachable origin",
        ),
        "docs/configuration.md": (
            "add-on is deferred and is not part of the current HACS release",
            "source configuration boundary for non-regression purposes",
            "not current installation guidance",
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


def validate_live_enrichment_gate_ownership() -> int:
    """Keep the cross-runtime live gate remote, required, and truthfully scoped."""
    command = "bash scripts/test-enrichment-live-e2e.sh"
    setup_uv = (
        "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
    )
    assertions = 0

    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/release-check.yml",
    ):
        assertions += require_document_fragments(
            relative,
            (
                "enrichment-live-e2e:",
                "timeout-minutes: 30",
                'python-version: "3.12"',
                setup_uv,
                'version: "0.11.16"',
                "uv sync --project apps/core --python 3.12 --extra dev",
                "pnpm install --frozen-lockfile",
                "pnpm --filter @zigbeelens/shared build",
                command,
            ),
        )

    assertions += require_document_fragments(
        "scripts/run-release-checks.sh",
        (
            "bash dist/zigbeelens-hacs/scripts/test-ha-integration-matrix.sh",
            command,
            "bash scripts/package-hacs-repo.sh",
        ),
    )
    assertions += require_document_fragments(
        "RELEASE_CHECKLIST.md",
        (
            "required monorepo PR/main `enrichment-live-e2e` check",
            "`v*` release gate depends on that same canonical live test",
            "generated satellite CI is package-scoped and does not replace this gate",
        ),
    )
    assertions += require_document_fragments(
        "docs/test-architecture.md",
        (
            "Packaging and the tag release gate depend on that job",
            "Generated HACS workflows remain package-scoped",
            "do not replace the green live-E2E result",
        ),
    )
    assertions += require_document_fragments(
        "docs/release.md",
        (
            "PR/main packaging gate and `v*` release gate",
            "dedicated `enrichment-live-e2e` job",
            "complement rather than replace that monorepo live-convergence result",
        ),
    )
    assertions += require_document_fragments(
        "docs/hacs.md",
        (
            "required monorepo `enrichment-live-e2e` check passes remotely",
            "Generated satellite CI is package-scoped",
            "does not replace the monorepo live-enrichment gate",
        ),
    )

    for relative in (
        "release/zigbeelens-hacs/.github/workflows/ci.yml",
        "release/zigbeelens-hacs/.github/workflows/release.yml",
    ):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        if command in workflow or "enrichment-live-e2e" in workflow:
            raise DocumentationError(
                f"{relative}: generated satellite workflow cannot claim the "
                "omitted monorepo cross-runtime live gate"
            )
        assertions += 2
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
        r"(?<!dist/)\b(?:(?!dist/)[A-Za-z0-9_.-]+/)?zigbeelens-hacs\b)",
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
            "staged tree matches the intended satellite tree exactly",
            "manifest/package version uniquely identifies that tree",
            "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
            "`2026.7.3` / Python `3.14` coverage passes",
            "official HACS and hassfest validation passes remotely",
            "explicit publication authorization is recorded",
        ),
        "apps/ha_integration/README.md": (
            "staged tree must match the intended satellite tree",
            "version must uniquely identify that tree",
            "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
            "`2026.7.3` / Python `3.14` coverage must pass",
            "official HACS and hassfest validation must pass remotely",
            "explicit publication authorization must be recorded",
        ),
        "release/zigbeelens-hacs/README.md.in": (
            "staged tree must match the intended satellite tree",
            "version must uniquely identify that tree",
            "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
            "`2026.7.3` / Python `3.14` coverage must pass",
            "official HACS and hassfest validation must pass remotely",
            "explicit publication authorization must be recorded",
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

    hacs_release_truth = (
        "OptionsFlow returns panel visibility and the selected 15–900-second",
        "missing or malformed Core versions fail closed as `unknown`",
        "Exact v2 with missing/malformed Dashboard Decision data",
        "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
        "`2026.7.3` / Python `3.14`",
        "`single_config_entry: true`",
        "official HACS and hassfest validation passes remotely",
        "add-on is deferred and is not part of the current HACS release",
    )
    assertions += require_document_fragments("docs/hacs.md", hacs_release_truth)
    assertions += require_document_fragments(
        "release/zigbeelens-hacs/README.md.in",
        (
            "OptionsFlow behind **Configure** persists a selected "
            "15–900-second interval",
            "missing/malformed Core versions fail closed as **Unknown**",
            "missing/malformed exact-v2 Dashboard Decision data",
            "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
            "`2026.7.3` / Python `3.14`",
            "`single_config_entry: true`",
            "official HACS and hassfest validation must pass remotely",
            "add-on is deferred and is not part of this HACS release",
        ),
    )
    assertions += require_document_fragments(
        "README.md",
        (
            "Current portable deployment route",
            "Local/staged source testing only",
            "public install unavailable until satellite synchronization "
            "and remote official checks pass",
            "Deferred — not part of the current HACS release",
        ),
    )
    synchronization_gates: dict[str, tuple[str, ...]] = {
        "RELEASE_CHECKLIST.md": (
            "complete staged tree matches the intended",
            "manifest/package version uniquely identifies that tree",
            "Home Assistant `2025.1.0` / Python `3.12` and Home Assistant "
            "`2026.7.3` / Python `3.14`",
            "generated remote official HACS/hassfest checks",
            "Explicit authorization to synchronize and publish",
        ),
        "docs/release-infra.md": (
            "complete staged tree matches the intended satellite tree",
            "manifest/package version that uniquely identifies that exact tree",
            "Home Assistant 2025.1.0/Python 3.12 and "
            "2026.7.3/Python 3.14 lanes remotely",
            "generated official HACS and hassfest validation remotely",
            "explicit publication authorization before modifying",
        ),
        "docs/release.md": (
            "complete staged tree must match the intended satellite tree",
            "manifest/package version must uniquely identify that exact tree",
            "Home Assistant 2025.1.0/Python 3.12 and "
            "2026.7.3/Python 3.14 lanes must pass",
            "generated official HACS and hassfest validation must pass remotely",
            "explicit publication authorization must be recorded",
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
            "`reporting.max_recent_events` accepts `1..1000`",
            "Removed sample-limit and raw-payload switches are rejected",
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
            "Home Assistant persists them and the registered update listener "
            "performs one effective reload",
            "Home Assistant `2025.1.0` on Python `3.12` and Home Assistant "
            "`2026.7.3` on Python `3.14`",
            "`reporting.default_profile`",
            "`mqtt_discovery.object_id_prefix`",
        ),
        "docs/hacs.md": (
            "`shared_decisions_available === true` and "
            "`core_version_compatible === true`",
            "payload-specific repair that does not prescribe a Core upgrade",
            "Decision payload: `valid`, `missing`, `malformed`",
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
            "Configure adjusts panel visibility and durably persists a "
            "15–900-second polling interval through one effective reload",
            "Exact minimum lane passed: Home Assistant `2025.1.0` / Python `3.12`",
            "Exact current lane passed: Home Assistant `2026.7.3` / Python `3.14`",
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
        + validate_live_enrichment_gate_ownership()
        + validate_companion_publication_truth()
        + validate_release_document_ownership()
        + validate_release_blocker_status_truth()
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
    screenshots = validate_screenshot_manifest(markdown_files)
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
        f"{screenshots} canonical screenshots validated, "
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
