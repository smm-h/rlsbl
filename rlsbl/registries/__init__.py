"""Registry lookup for rlsbl."""

from . import go, npm, pypi

REGISTRIES = {"npm": npm, "pypi": pypi, "go": go}
