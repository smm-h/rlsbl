"""Shared platform models for npm binary wrapper packages.

Provides the data structures and helpers needed by scaffold generators
that produce npm wrapper packages around native binaries (Go, Rust, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class PlatformSpec:
    """Partial platform descriptor (target-agnostic).

    Contains only the npm/OS/CPU identifiers -- no archive or binary
    details, since those depend on the build target (Go, Rust, etc.).
    """

    npm_platform: str
    os_constraint: str
    cpu_constraint: str


@dataclass
class PlatformArtifact:
    """Fully resolved platform artifact ready for package generation.

    Combines platform identifiers with target-specific archive and
    binary information.
    """

    npm_platform: str
    os_constraint: str
    cpu_constraint: str
    asset_pattern: str
    extract_cmd: str | None
    binary_name: str


DEFAULT_PLATFORMS: list[PlatformSpec] = [
    PlatformSpec("linux-x64", "linux", "x64"),
    PlatformSpec("linux-arm64", "linux", "arm64"),
    PlatformSpec("darwin-x64", "darwin", "x64"),
    PlatformSpec("darwin-arm64", "darwin", "arm64"),
    PlatformSpec("win32-x64", "win32", "x64"),
    PlatformSpec("win32-arm64", "win32", "arm64"),
]


def load_platform_config(config: dict) -> list[PlatformSpec]:
    """Return platform specs, optionally filtered by config.

    If ``config`` contains ``npm_wrapper.platforms`` (a list of
    npm_platform strings like ``["linux-x64", "darwin-arm64"]``),
    only matching entries from DEFAULT_PLATFORMS are returned.
    Otherwise all DEFAULT_PLATFORMS are returned.
    """
    wrapper_cfg = config.get("npm_wrapper", {})
    platforms_filter = wrapper_cfg.get("platforms")

    if platforms_filter is None:
        return list(DEFAULT_PLATFORMS)

    allowed = set(platforms_filter)
    return [spec for spec in DEFAULT_PLATFORMS if spec.npm_platform in allowed]


def build_artifacts(
    specs: list[PlatformSpec],
    name: str,
    archive_fn: Callable[[PlatformSpec, str], tuple[str, str | None, str]],
) -> list[PlatformArtifact]:
    """Combine platform specs with target-specific archive details.

    ``archive_fn(spec, name)`` must return a tuple of
    ``(asset_pattern, extract_cmd, binary_name)`` for each platform.
    """
    artifacts: list[PlatformArtifact] = []
    for spec in specs:
        asset_pattern, extract_cmd, binary_name = archive_fn(spec, name)
        artifacts.append(
            PlatformArtifact(
                npm_platform=spec.npm_platform,
                os_constraint=spec.os_constraint,
                cpu_constraint=spec.cpu_constraint,
                asset_pattern=asset_pattern,
                extract_cmd=extract_cmd,
                binary_name=binary_name,
            )
        )
    return artifacts
