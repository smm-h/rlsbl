"""Backward-compatibility shim. Use rlsbl.targets directly."""
from ..targets import TARGETS as REGISTRIES, detect_targets  # noqa: F401
