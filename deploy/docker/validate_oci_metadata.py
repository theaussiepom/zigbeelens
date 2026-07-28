#!/usr/bin/env python3
"""Fail closed unless Docker metadata carries the release identity exactly."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

OCI_VERSION_LABEL = "org.opencontainers.image.version"
OCI_REVISION_LABEL = "org.opencontainers.image.revision"
OCI_SOURCE_LABEL = "org.opencontainers.image.source"

_STRICT_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class MetadataValidationError(ValueError):
    """The metadata-action JSON did not prove the expected image identity."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataValidationError(
                "metadata JSON contains a duplicate object key"
            )
        result[key] = value
    return result


def _parse_metadata(metadata_json: str) -> Mapping[str, Any]:
    if not metadata_json:
        raise MetadataValidationError("metadata JSON is missing")
    try:
        payload = json.loads(
            metadata_json,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except MetadataValidationError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise MetadataValidationError("metadata JSON is invalid") from exc
    if not isinstance(payload, Mapping):
        raise MetadataValidationError("metadata JSON must be an object")
    return payload


def _validate_expected_identity(
    *,
    expected_version: str,
    expected_revision: str,
    expected_source: str,
) -> None:
    if _STRICT_SEMVER.fullmatch(expected_version) is None:
        raise MetadataValidationError("expected image version must be strict SemVer")
    if _FULL_GIT_SHA.fullmatch(expected_revision) is None:
        raise MetadataValidationError(
            "expected image revision must be a full 40-character Git SHA"
        )

    source = urlsplit(expected_source)
    path_parts = [part for part in source.path.split("/") if part]
    if (
        source.scheme != "https"
        or source.netloc != "github.com"
        or len(path_parts) != 2
        or source.path != f"/{'/'.join(path_parts)}"
        or source.query
        or source.fragment
        or _CONTROL_CHARACTERS.search(expected_source)
        or any(character.isspace() for character in expected_source)
    ):
        raise MetadataValidationError(
            "expected image source must be an exact GitHub repository URL"
        )


def _validated_label_lines(
    metadata: Mapping[str, Any],
    *,
    expected_version: str,
    expected_revision: str,
    expected_source: str,
) -> tuple[str, ...]:
    _validate_expected_identity(
        expected_version=expected_version,
        expected_revision=expected_revision,
        expected_source=expected_source,
    )

    tags = metadata.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or any(
            not isinstance(tag, str) or not tag or _CONTROL_CHARACTERS.search(tag)
            for tag in tags
        )
    ):
        raise MetadataValidationError(
            "metadata tags must be a nonempty list of safe strings"
        )

    labels = metadata.get("labels")
    if not isinstance(labels, Mapping):
        raise MetadataValidationError("metadata labels object is missing")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or _CONTROL_CHARACTERS.search(key)
        or _CONTROL_CHARACTERS.search(value)
        for key, value in labels.items()
    ):
        raise MetadataValidationError(
            "metadata labels must contain only safe string keys and values"
        )

    required = {
        OCI_VERSION_LABEL: expected_version,
        OCI_REVISION_LABEL: expected_revision,
        OCI_SOURCE_LABEL: expected_source,
    }
    for key, expected in required.items():
        if labels.get(key) != expected:
            raise MetadataValidationError(
                f"metadata label {key} does not match the expected identity"
            )

    return tuple(f"{key}={labels[key]}" for key in sorted(labels))


def validated_labels_from_json(
    metadata_json: str,
    *,
    expected_version: str,
    expected_revision: str,
    expected_source: str,
) -> tuple[str, ...]:
    """Return Buildx label lines only after validating metadata-action JSON."""

    return _validated_label_lines(
        _parse_metadata(metadata_json),
        expected_version=expected_version,
        expected_revision=expected_revision,
        expected_source=expected_source,
    )


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MetadataValidationError(f"required environment {name} is missing")
    return value


def _write_github_output(path: Path, label_lines: tuple[str, ...]) -> None:
    delimiter = "ZIGBEELENS_VALIDATED_OCI_LABELS"
    rendered = "\n".join(label_lines)
    if any(line == delimiter for line in rendered.splitlines()):
        raise MetadataValidationError("validated labels conflict with delimiter")
    with path.open("a", encoding="utf-8") as output:
        output.write(f"labels<<{delimiter}\n")
        output.write(rendered)
        output.write(f"\n{delimiter}\n")


def main() -> None:
    """Validate action output and expose only validated labels to Buildx."""

    label_lines = validated_labels_from_json(
        _required_environment("DOCKER_METADATA_OUTPUT_JSON"),
        expected_version=_required_environment("EXPECTED_OCI_VERSION"),
        expected_revision=_required_environment("EXPECTED_OCI_REVISION"),
        expected_source=_required_environment("EXPECTED_OCI_SOURCE"),
    )
    output_path = Path(_required_environment("GITHUB_OUTPUT"))
    _write_github_output(output_path, label_lines)
    print(f"Validated {len(label_lines)} OCI image labels.")


if __name__ == "__main__":
    try:
        main()
    except MetadataValidationError as exc:
        raise SystemExit(f"OCI metadata validation failed: {exc}") from exc
