"""Fail-closed contracts for canonical Phase 7C2 screenshot evidence."""

from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import struct
import sys
from typing import Iterator
import zlib

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-docs.py"
SPEC = importlib.util.spec_from_file_location(
    "zigbeelens_validate_docs_screenshot_contract",
    VALIDATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

CAPTURE_SHA = VALIDATOR.PHASE_7C2_CAPTURE_SOURCE_SHA
CAPTION = VALIDATOR.SCREENSHOT_CAPTION_PREFIX


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", crc)
    )


def _png(
    rgb: bytes = b"\x11\x22\x33",
    *,
    width: int = 1,
    height: int = 1,
    raw_scanlines: bytes | None = None,
    extra_chunks: tuple[tuple[bytes, bytes], ...] = (),
    compressed_override: bytes | None = None,
    interlace: int = 0,
    split_idat: bool = False,
) -> bytes:
    if compressed_override is None:
        if raw_scanlines is None:
            assert len(rgb) == 3
            raw_scanlines = b"".join(
                b"\x00" + rgb * width for _ in range(height)
            )
        compressed = zlib.compress(raw_scanlines)
    else:
        compressed = compressed_override
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, interlace)
    if split_idat:
        midpoint = max(1, len(compressed) // 2)
        idat = _chunk(b"IDAT", compressed[:midpoint]) + _chunk(
            b"IDAT", compressed[midpoint:]
        )
    else:
        idat = _chunk(b"IDAT", compressed)
    return (
        VALIDATOR.PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + b"".join(_chunk(chunk_type, data) for chunk_type, data in extra_chunks)
        + idat
        + _chunk(b"IEND", b"")
    )


@contextmanager
def _validator_root(root: Path) -> Iterator[None]:
    original = VALIDATOR.ROOT
    VALIDATOR.ROOT = root
    try:
        yield
    finally:
        VALIDATOR.ROOT = original


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _manifest(root: Path) -> dict[str, object]:
    return json.loads(
        (root / VALIDATOR.SCREENSHOT_MANIFEST).read_text(encoding="utf-8")
    )


def _asset(manifest: dict[str, object], filename: str) -> dict[str, object]:
    assets = manifest["assets"]
    assert isinstance(assets, list)
    return next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("filename") == filename
    )


def _refresh_asset_file(
    root: Path,
    manifest: dict[str, object],
    filename: str,
    payload: bytes,
    width: int,
    height: int,
) -> None:
    path = root / VALIDATOR.SCREENSHOT_DIRECTORY / filename
    path.write_bytes(payload)
    asset = _asset(manifest, filename)
    asset["width"] = width
    asset["height"] = height
    asset["byte_size"] = len(payload)
    asset["sha256"] = hashlib.sha256(payload).hexdigest()
    if (width, height) != (
        VALIDATOR.SCREENSHOT_DEFAULT_WIDTH,
        VALIDATOR.SCREENSHOT_DEFAULT_HEIGHT,
    ):
        asset["capture_exception_rationale"] = (
            "Focused contract fixture uses a non-default viewport."
        )


def _build_contract(root: Path) -> list[Path]:
    _write_json(root / "package.json", {"version": "0.1.14"})
    screenshot_root = root / VALIDATOR.SCREENSHOT_DIRECTORY
    screenshot_root.mkdir(parents=True)
    assets: list[dict[str, object]] = []
    document_parts: dict[str, list[str]] = {}

    for index, (filename, contract) in enumerate(
        VALIDATOR.SCREENSHOT_ASSETS.items(),
        start=1,
    ):
        owner, destination = contract
        payload = _png(bytes((index, index + 20, index + 40)))
        image_path = screenshot_root / filename
        image_path.write_bytes(payload)
        asset: dict[str, object] = {
            "filename": filename,
            "surface_owner": owner,
            "route_or_state": VALIDATOR.SCREENSHOT_EXACT_ROUTE_STATES.get(
                filename,
                f"Real synthetic fixture state {index}",
            ),
            "data_source": "isolated deterministic synthetic fixture",
            "capture_source_sha": CAPTURE_SHA,
            "width": 1,
            "height": 1,
            "device_scale_factor": 1,
            "zoom_percent": 100,
            "theme": "production_default",
            "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "format": "png",
            "capture_method": (
                "real production UI capture with reduced motion enabled"
            ),
            "identifier_presentation": (
                "full_synthetic_fixture" if index == 1 else "not_visible"
            ),
            "privacy_review": "passed",
            "visual_review": "passed",
            "documentation_destinations": [destination],
            "capture_exception_rationale": (
                "Focused contract fixture uses a 1 x 1 viewport."
            ),
        }
        if owner == "home_assistant":
            asset.update(
                {
                    "hacs_package_source_sha": CAPTURE_SHA,
                    "hacs_package_origin": "local_repository_stage",
                    "public_hacs_satellite_used": False,
                    "home_assistant_version": "2026.7.3",
                }
            )
        assets.append(asset)

        document = root / destination
        relative_image = os.path.relpath(image_path, document.parent)
        document_parts.setdefault(destination, []).append(
            f"![Meaningful rendered product state {index}]({relative_image})\n\n"
            f"{CAPTION} Contract fixture {index}.\n"
        )

    markdown_files: list[Path] = []
    for destination, parts in document_parts.items():
        path = root / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(parts), encoding="utf-8")
        markdown_files.append(path)

    _write_json(
        root / VALIDATOR.SCREENSHOT_MANIFEST,
        {
            "screenshot_manifest_version": 1,
            "capture_source_sha": CAPTURE_SHA,
            "release_candidate_version": "0.1.14",
            "capture_date": "2026-07-29",
            "data_classification": "synthetic",
            "contains_real_device_identifiers": False,
            "capture_provenance_note": (
                "Assets use capture_source_sha; the final documentation commit "
                "may differ because documentation changes are not runtime changes."
            ),
            "assets": assets,
        },
    )
    return sorted(markdown_files)


def _validate(root: Path, markdown_files: list[Path]) -> int:
    with _validator_root(root):
        return VALIDATOR.validate_screenshot_manifest(markdown_files, root)


def test_canonical_phase_7c2_screenshot_manifest_contract():
    markdown_files = VALIDATOR.tracked_files("*.md")
    assert VALIDATOR.validate_screenshot_manifest(markdown_files) == 9


def test_complete_isolated_screenshot_contract_is_accepted(tmp_path: Path):
    markdown_files = _build_contract(tmp_path)
    assert _validate(tmp_path, markdown_files) == 9


@pytest.mark.parametrize(
    ("filename", "stale_route"),
    (
        (
            "reports-page.png",
            "Core Reports with a saved synthetic ReportDetailV3 report selected",
        ),
        (
            "hacs-config-flow.png",
            "Home Assistant combined config flow with URL, token, TLS, panel, "
            "and polling interval",
        ),
    ),
)
def test_amended_s5_s7_route_state_semantics_fail_closed(
    tmp_path: Path,
    filename: str,
    stale_route: str,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    _asset(manifest, filename)["route_or_state"] = stale_route
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    with pytest.raises(
        VALIDATOR.DocumentationError,
        match="route_or_state must exactly describe the accepted surface",
    ):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize(
    "key",
    (
        "capture_password",
        "capture-passwd",
        "capture secret",
        "api_key",
        "apikey",
        "sessionId",
        "session-secret",
        "service credential",
        "HTTPAuthorization",
        "authBearer",
        "captureToken",
        "sessionCookie",
        "browserProfile",
        "filesystemPath",
        "absolute_path",
        "servicePort",
    ),
)
def test_sensitive_manifest_key_vocabulary_and_casing(key: str):
    assert VALIDATOR._sensitive_manifest_key(key)


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("wrong_source", "accepted Phase 7C2 runtime source"),
        ("wrong_version", "release_candidate_version"),
        ("non_synthetic_classification", "data_classification must be synthetic"),
        ("real_identifiers", "contains_real_device_identifiers"),
        ("visible_ieee", "complete IEEE address"),
        ("sensitive_field", "forbidden sensitive field"),
        ("nested_sensitive_fields", "forbidden sensitive field"),
        ("camel_token", "forbidden sensitive field"),
        ("camel_cookie", "forbidden sensitive field"),
        ("camel_profile", "forbidden sensitive field"),
        ("camel_port", "forbidden sensitive field"),
        ("upper_camel_token", "forbidden sensitive field"),
        ("kebab_secret", "forbidden sensitive field"),
        ("nested_api_key", "forbidden sensitive field"),
        ("ieee_object_key", "complete IEEE address"),
        ("privacy_pending", "privacy_review must be passed"),
        ("wrong_hacs_source", "hacs_package_source_sha"),
        ("public_satellite", "public_hacs_satellite_used must be False"),
        ("wrong_destination", "documentation_destinations"),
        ("wrong_scale", "device_scale_factor must be 1"),
        ("wrong_zoom", "zoom_percent must be 100"),
        ("wrong_theme", "theme must be production_default"),
        ("missing_field", "missing manifest field"),
        ("missing_viewport_rationale", "non-default viewport requires"),
    ),
)
def test_manifest_provenance_privacy_and_review_fail_closed(
    tmp_path: Path,
    case: str,
    expected: str,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    if case == "wrong_source":
        manifest["capture_source_sha"] = "a" * 40
    elif case == "wrong_version":
        manifest["release_candidate_version"] = "0.1.13"
    elif case == "non_synthetic_classification":
        manifest["data_classification"] = "production"
    elif case == "real_identifiers":
        manifest["contains_real_device_identifiers"] = True
    elif case == "visible_ieee":
        _asset(manifest, "overview-dashboard.png")["route_or_state"] = (
            "real device 0x0017880102b3c4d5"
        )
    elif case == "sensitive_field":
        _asset(manifest, "overview-dashboard.png")["api_token"] = "secret"
    elif case == "nested_sensitive_fields":
        manifest["extra"] = {
            "capture": {
                "cookie": "secret",
                "port": 18123,
            }
        }
    elif case == "camel_token":
        manifest["extra"] = {"apiToken": "secret"}
    elif case == "camel_cookie":
        manifest["extra"] = {"sessionCookie": "secret"}
    elif case == "camel_profile":
        manifest["extra"] = {"browserProfile": "temporary"}
    elif case == "camel_port":
        manifest["extra"] = {"servicePort": 18123}
    elif case == "upper_camel_token":
        manifest["extra"] = {"APIToken": "secret"}
    elif case == "kebab_secret":
        manifest["extra"] = {"session-secret": "secret"}
    elif case == "nested_api_key":
        manifest["extra"] = {"nested": [{"api.key": "secret"}]}
    elif case == "ieee_object_key":
        manifest["extra"] = {"0x0017880102b3c4d5": "must not be stored"}
    elif case == "privacy_pending":
        _asset(manifest, "overview-dashboard.png")["privacy_review"] = "pending"
    elif case == "wrong_hacs_source":
        _asset(manifest, "hacs-config-flow.png")[
            "hacs_package_source_sha"
        ] = "b" * 40
    elif case == "public_satellite":
        _asset(manifest, "hacs-config-flow.png")[
            "public_hacs_satellite_used"
        ] = True
    elif case == "wrong_destination":
        _asset(manifest, "overview-dashboard.png")[
            "documentation_destinations"
        ] = ["docs/topology.md"]
    elif case == "wrong_scale":
        _asset(manifest, "overview-dashboard.png")["device_scale_factor"] = 2
    elif case == "wrong_zoom":
        _asset(manifest, "overview-dashboard.png")["zoom_percent"] = 90
    elif case == "wrong_theme":
        _asset(manifest, "overview-dashboard.png")["theme"] = "dark"
    elif case == "missing_field":
        _asset(manifest, "overview-dashboard.png").pop("route_or_state")
    elif case == "missing_viewport_rationale":
        _asset(manifest, "overview-dashboard.png").pop(
            "capture_exception_rationale"
        )
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    with pytest.raises(VALIDATOR.DocumentationError, match=expected):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("extra_top_level", "unapproved top-level field"),
        ("extra_core_asset", "unapproved manifest field"),
        ("extra_ha_asset", "unapproved manifest field"),
        ("missing_ha_field", "missing manifest field"),
    ),
)
def test_manifest_schema_is_exact(
    tmp_path: Path,
    case: str,
    expected: str,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    if case == "extra_top_level":
        manifest["review_batch"] = "phase-7c2"
    elif case == "extra_core_asset":
        _asset(manifest, "overview-dashboard.png")["review_batch"] = "phase-7c2"
    elif case == "extra_ha_asset":
        _asset(manifest, "hacs-config-flow.png")["package_channel"] = "local"
    elif case == "missing_ha_field":
        _asset(manifest, "hacs-config-flow.png").pop("hacs_package_source_sha")
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    with pytest.raises(VALIDATOR.DocumentationError, match=expected):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("unmanifested", "unmanifested screenshot"),
        ("addon_jpeg", "unmanifested screenshot"),
        ("addon_gif", "unmanifested screenshot"),
        ("addon_heic", "unmanifested screenshot"),
        ("addon_svg", "unmanifested screenshot"),
        ("unexpected_text", "unmanifested screenshot"),
        ("unexpected_directory", "unmanifested screenshot"),
        ("missing_manifest_asset", "screenshot manifest missing"),
        ("duplicate_manifest_name", "filenames must appear exactly once"),
        ("duplicate_binary", "duplicate binary screenshot"),
    ),
)
def test_inventory_and_duplicate_images_fail_closed(
    tmp_path: Path,
    case: str,
    expected: str,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    screenshot_root = tmp_path / VALIDATOR.SCREENSHOT_DIRECTORY
    if case == "unmanifested":
        (screenshot_root / "addon-panel.webp").write_bytes(b"not a WebP")
    elif case == "addon_jpeg":
        (screenshot_root / "addon-panel.jpg").write_bytes(b"not a JPEG")
    elif case == "addon_gif":
        (screenshot_root / "addon-panel.gif").write_bytes(b"not a GIF")
    elif case == "addon_heic":
        (screenshot_root / "addon-panel.heic").write_bytes(b"not a HEIC")
    elif case == "addon_svg":
        (screenshot_root / "addon-panel.svg").write_text(
            "<svg/>",
            encoding="utf-8",
        )
    elif case == "unexpected_text":
        (screenshot_root / "capture-notes.txt").write_text(
            "private capture notes",
            encoding="utf-8",
        )
    elif case == "unexpected_directory":
        (screenshot_root / "working").mkdir()
    elif case == "missing_manifest_asset":
        manifest["assets"] = [
            asset
            for asset in manifest["assets"]
            if asset["filename"] != "overview-dashboard.png"
        ]
    elif case == "duplicate_manifest_name":
        manifest["assets"].append(copy.deepcopy(manifest["assets"][0]))
    elif case == "duplicate_binary":
        source = screenshot_root / "overview-dashboard.png"
        duplicate_name = "mesh-investigate.png"
        duplicate = source.read_bytes()
        _refresh_asset_file(
            tmp_path,
            manifest,
            duplicate_name,
            duplicate,
            width=1,
            height=1,
        )
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    with pytest.raises(VALIDATOR.DocumentationError, match=expected):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("invalid_signature", "invalid PNG signature"),
        ("invalid_crc", "invalid CRC"),
        ("invalid_zlib", "IDAT zlib stream does not decode"),
        ("truncated_zlib", "zlib stream is truncated"),
        ("trailing_zlib", "zlib stream has trailing data"),
        ("one_byte_over", "exceeds its exact scanline budget"),
        ("one_byte_under", "decoded PNG scanline size"),
        ("invalid_filter", "invalid PNG filter"),
        ("global_budget", "100 MB safety limit"),
        ("invalid_srgb", "invalid PNG sRGB rendering intent"),
        ("duplicate_srgb", "at most one sRGB"),
        ("srgb_after_plte", "sRGB must precede PLTE"),
        ("missing_iend", "exactly one IEND"),
        ("trailing_data", "data appears after PNG IEND"),
    ),
)
def test_png_parser_rejects_structural_and_decode_failures(
    tmp_path: Path,
    case: str,
    expected: str,
):
    payload = _png()
    if case == "invalid_signature":
        payload = b"not png"
    elif case == "invalid_crc":
        corrupted = bytearray(payload)
        idat = payload.index(b"IDAT")
        corrupted[idat + 4] ^= 0x01
        payload = bytes(corrupted)
    elif case == "invalid_zlib":
        payload = _png(compressed_override=b"not a zlib stream")
    elif case == "truncated_zlib":
        payload = _png(compressed_override=zlib.compress(b"\x00\x11\x22\x33")[:-2])
    elif case == "trailing_zlib":
        payload = _png(
            compressed_override=zlib.compress(b"\x00\x11\x22\x33") + b"trailing"
        )
    elif case == "one_byte_over":
        payload = _png(
            compressed_override=zlib.compress(b"\x00\x11\x22\x33\x44")
        )
    elif case == "one_byte_under":
        payload = _png(compressed_override=zlib.compress(b"\x00\x11\x22"))
    elif case == "invalid_filter":
        payload = _png(compressed_override=zlib.compress(b"\x05\x11\x22\x33"))
    elif case == "global_budget":
        payload = _png(
            width=100_000,
            height=100_000,
            compressed_override=zlib.compress(b""),
        )
    elif case == "invalid_srgb":
        payload = _png(extra_chunks=((b"sRGB", b"/Users/private"),))
    elif case == "duplicate_srgb":
        payload = _png(
            extra_chunks=((b"sRGB", b"\x00"), (b"sRGB", b"\x01"))
        )
    elif case == "srgb_after_plte":
        payload = _png(
            extra_chunks=((b"PLTE", b"\x00\x00\x00"), (b"sRGB", b"\x00"))
        )
    elif case == "missing_iend":
        payload = payload[: -len(_chunk(b"IEND", b""))]
    elif case == "trailing_data":
        payload += _chunk(b"vpAg", b"trailing")
    path = tmp_path / "image.png"
    path.write_bytes(payload)

    with _validator_root(tmp_path):
        with pytest.raises(VALIDATOR.DocumentationError, match=expected):
            VALIDATOR.parse_png(path)


def test_png_parser_accepts_split_idat_and_adam7(tmp_path: Path):
    split_path = tmp_path / "split-idat.png"
    split_path.write_bytes(_png(width=3, height=2, split_idat=True))

    width = 9
    height = 9
    adam7_rows = bytearray()
    for pass_width, pass_height in VALIDATOR._png_passes(width, height, 1):
        row = bytes((pass_width * 3))
        for _ in range(pass_height):
            adam7_rows.extend(b"\x00")
            adam7_rows.extend(row)
    adam7_path = tmp_path / "adam7.png"
    adam7_path.write_bytes(
        _png(
            width=width,
            height=height,
            raw_scanlines=bytes(adam7_rows),
            interlace=1,
            split_idat=True,
        )
    )

    with _validator_root(tmp_path):
        assert VALIDATOR.parse_png(split_path)[:2] == (3, 2)
        assert VALIDATOR.parse_png(adam7_path)[:2] == (width, height)


def test_png_parser_accepts_valid_near_hard_maximum_file(tmp_path: Path):
    width = 1440
    height = 177
    random_bytes = random.Random(9).randbytes(width * 3 * height)
    scanlines = b"".join(
        b"\x00" + random_bytes[offset : offset + width * 3]
        for offset in range(0, len(random_bytes), width * 3)
    )
    payload = _png(width=width, height=height, raw_scanlines=scanlines)
    assert VALIDATOR.SCREENSHOT_HARD_MAX_BYTES - 8_192 < len(payload)
    assert len(payload) < VALIDATOR.SCREENSHOT_HARD_MAX_BYTES

    path = tmp_path / "near-hard-maximum.png"
    path.write_bytes(payload)
    with _validator_root(tmp_path):
        assert VALIDATOR.parse_png(path)[:2] == (width, height)


def test_png_decompression_bomb_stays_within_subprocess_memory_budget(
    tmp_path: Path,
):
    compressor = zlib.compressobj(level=1)
    block = b"\x00" * (1024 * 1024)
    compressed_parts = [compressor.compress(block) for _ in range(32)]
    compressed_parts.append(compressor.flush())
    path = tmp_path / "bomb.png"
    path.write_bytes(_png(compressed_override=b"".join(compressed_parts)))
    assert path.stat().st_size < VALIDATOR.SCREENSHOT_HARD_MAX_BYTES

    probe = """
import importlib.util
from pathlib import Path
import resource
import sys

validator_path = Path(sys.argv[1])
image_path = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("validator_bomb_probe", validator_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
try:
    module.parse_png(image_path)
except module.DocumentationError as exc:
    if "exact scanline budget" not in str(exc):
        raise
else:
    raise SystemExit("bomb unexpectedly decoded")
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
scale = 1 if sys.platform == "darwin" else 1024
print((after - before) * scale)
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(VALIDATOR_PATH), str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) <= 16 * 1024 * 1024


@pytest.mark.parametrize("chunk_type", tuple(VALIDATOR.PNG_FORBIDDEN_METADATA_CHUNKS))
def test_png_parser_rejects_forbidden_metadata(
    tmp_path: Path,
    chunk_type: bytes,
):
    path = tmp_path / "metadata.png"
    path.write_bytes(_png(extra_chunks=((chunk_type, b"private metadata"),)))

    with _validator_root(tmp_path):
        with pytest.raises(
            VALIDATOR.DocumentationError,
            match="forbidden PNG metadata chunk",
        ):
            VALIDATOR.parse_png(path)


def test_png_parser_rejects_private_ancillary_metadata(tmp_path: Path):
    path = tmp_path / "private-metadata.png"
    path.write_bytes(
        _png(
            extra_chunks=(
                (
                    b"vpAg",
                    b"/Users/reviewer/capture profile zigbeelens.private.example",
                ),
            )
        )
    )

    with _validator_root(tmp_path):
        with pytest.raises(
            VALIDATOR.DocumentationError,
            match="unsupported ancillary PNG chunk",
        ):
            VALIDATOR.parse_png(path)


def test_approved_synthetic_documentation_hosts_are_not_private_data(
    tmp_path: Path,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    _asset(manifest, "hacs-config-flow.png")["data_source"] = (
        "isolated deterministic synthetic fixture for "
        "https://zigbeelens.example.test using "
        "http://core.zigbeelens.test with bare hosts "
        "zigbeelens.example.test and core.zigbeelens.test"
    )
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    assert _validate(tmp_path, markdown_files) == 9


@pytest.mark.parametrize(
    "unsafe_host",
    (
        "https://zigbeelens.example.testevil",
        "http://core.zigbeelens.test.attacker.invalid",
        "zigbeelens.example.testevil",
        "core.zigbeelens.test.attacker.invalid",
        "https://zigbeelens.example.test@2130706433",
        "http://core.zigbeelens.test@0x7f000001",
        "https://zigbeelens.example.test:443@127.0.0.1",
        "//zigbeelens.example.test@127.0.0.1",
        "https://zigbeelens.example.test:443",
        "https://zigbeelens.example.test/path",
        "https://zigbeelens.example.test?query=1",
        "https://zigbeelens.example.test#fragment",
        "zigbeelens.example.test/path",
        "core.zigbeelens.test?query=1",
        "core.zigbeelens.test#fragment",
        "core.zigbeelens.test:80",
        "core.zigbeelens.test.",
        "http://2130706433",
        "http://0x7f000001",
        "http://017700000001",
        "http://127.0.0.1",
        "http://[::1]",
        "http://[::ffff:127.0.0.1]",
        "2130706433",
        "0x7f000001",
        "017700000001",
        "::ffff:127.0.0.1",
        "https://zigbeelens.example.test.",
        "https://zigbeelens%2eexample.test",
        "https://zigbeelens%252eexample.test",
        "//zigbeelens.example.test",
        "http://zigbeelens.example.test",
        "https://core.zigbeelens.test",
        "https:\\\\zigbeelens.example.test",
        "https://zigbeelens。example.test",
        "https://xn--zigbeelens-9za.example.test",
        "zigbeelens.example.test\u200b.evil.invalid",
        "zigbeelens.example.test\u2060.evil.invalid",
        "ｅｖｉｌ.ｉｎｖａｌｉｄ",
        "ｚｉｇｂｅｅｌｅｎｓ.ｅｘａｍｐｌｅ.ｔｅｓｔ",
        "evil.іnvalid",
        "évil.ïnvalid",
    ),
)
def test_approved_synthetic_hosts_require_exact_boundaries(
    tmp_path: Path,
    unsafe_host: str,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    _asset(manifest, "hacs-config-flow.png")["data_source"] = (
        f"isolated deterministic synthetic fixture with unsafe capture host "
        f"{unsafe_host}"
    )
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)

    with pytest.raises(VALIDATOR.DocumentationError, match="URL/hostname"):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize("host_token", ("127", "0177", "0x7f"))
def test_short_integer_host_tokens_fail_closed(host_token: str):
    assert VALIDATOR._has_forbidden_network_reference(host_token)


def test_manifest_hash_size_dimensions_and_size_policy_are_mechanical(
    tmp_path: Path,
):
    markdown_files = _build_contract(tmp_path)
    manifest = _manifest(tmp_path)
    overview = _asset(manifest, "overview-dashboard.png")
    overview["byte_size"] = 1
    overview["sha256"] = "0" * 64
    overview["width"] = 2
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)
    with pytest.raises(VALIDATOR.DocumentationError) as exc_info:
        _validate(tmp_path, markdown_files)
    failure = str(exc_info.value)
    assert "byte_size" in failure
    assert "sha256 does not match" in failure
    assert "manifest dimensions" in failure

    manifest = _manifest(tmp_path)
    random_bytes = random.Random(7).randbytes(1440 * 3 * 120)
    scanlines = b"".join(
        b"\x00" + random_bytes[offset : offset + 1440 * 3]
        for offset in range(0, len(random_bytes), 1440 * 3)
    )
    large = _png(width=1440, height=120, raw_scanlines=scanlines)
    assert (
        VALIDATOR.SCREENSHOT_PREFERRED_MAX_BYTES
        < len(large)
        < VALIDATOR.SCREENSHOT_HARD_MAX_BYTES
    )
    _refresh_asset_file(
        tmp_path,
        manifest,
        "overview-dashboard.png",
        large,
        width=1440,
        height=120,
    )
    overview = _asset(manifest, "overview-dashboard.png")
    overview.pop("size_exception_rationale", None)
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)
    with pytest.raises(
        VALIDATOR.DocumentationError,
        match="image over 500 KB requires size_exception_rationale",
    ):
        _validate(tmp_path, markdown_files)

    overview["size_exception_rationale"] = "Readable at full resolution."
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)
    assert _validate(tmp_path, markdown_files) == 9

    random_bytes = random.Random(8).randbytes(1440 * 3 * 180)
    scanlines = b"".join(
        b"\x00" + random_bytes[offset : offset + 1440 * 3]
        for offset in range(0, len(random_bytes), 1440 * 3)
    )
    oversized = _png(width=1440, height=180, raw_scanlines=scanlines)
    assert len(oversized) > VALIDATOR.SCREENSHOT_HARD_MAX_BYTES
    _refresh_asset_file(
        tmp_path,
        manifest,
        "overview-dashboard.png",
        oversized,
        width=1440,
        height=180,
    )
    overview["size_exception_rationale"] = "A rationale cannot bypass the hard limit."
    _write_json(tmp_path / VALIDATOR.SCREENSHOT_MANIFEST, manifest)
    with pytest.raises(VALIDATOR.DocumentationError, match="750 KB hard maximum"):
        _validate(tmp_path, markdown_files)


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("weak_alt", "needs meaningful alt text"),
        ("missing_caption", "must have an immediate caption"),
        ("duplicate_embed", "expected exactly one approved Markdown embed"),
        ("wrong_document", "Markdown destination must be"),
        ("obsolete_reference", "obsolete or unapproved screenshot reference"),
    ),
)
def test_markdown_alt_caption_and_destination_fail_closed(
    tmp_path: Path,
    case: str,
    expected: str,
):
    markdown_files = _build_contract(tmp_path)
    readme = tmp_path / "README.md"
    topology = tmp_path / "docs/topology.md"
    if case == "weak_alt":
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "Meaningful rendered product state 1",
                "screenshot",
            ),
            encoding="utf-8",
        )
    elif case == "missing_caption":
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                CAPTION,
                "Synthetic release-candidate data.",
                1,
            ),
            encoding="utf-8",
        )
    elif case == "duplicate_embed":
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n![Second meaningful view](docs/screenshots/overview-dashboard.png)"
            + f"\n\n{CAPTION} Duplicate.\n",
            encoding="utf-8",
        )
    elif case == "wrong_document":
        block = readme.read_text(encoding="utf-8")
        readme.write_text("", encoding="utf-8")
        topology.write_text(
            topology.read_text(encoding="utf-8")
            + "\n"
            + block.replace(
                "docs/screenshots/overview-dashboard.png",
                "screenshots/overview-dashboard.png",
            ),
            encoding="utf-8",
        )
    elif case == "obsolete_reference":
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n![Old product view](docs/screenshots/old-health.png)"
            + f"\n\n{CAPTION} Obsolete.\n",
            encoding="utf-8",
        )

    with pytest.raises(VALIDATOR.DocumentationError, match=expected):
        _validate(tmp_path, markdown_files)


def test_duplicate_manifest_json_keys_are_rejected(tmp_path: Path):
    markdown_files = _build_contract(tmp_path)
    path = tmp_path / VALIDATOR.SCREENSHOT_MANIFEST
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '"screenshot_manifest_version": 1,',
        '"screenshot_manifest_version": 1,\n'
        '  "screenshot_manifest_version": 1,',
        1,
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(VALIDATOR.DocumentationError, match="duplicate JSON key"):
        _validate(tmp_path, markdown_files)
