"""Registry lookup for rlsbl."""

from . import npm, pypi

REGISTRIES = {"npm": npm, "pypi": pypi}
