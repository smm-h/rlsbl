"""Registry lookup for rlsbl.

Delegates to rlsbl.targets for the instance-based REGISTRIES dict.
Old module imports (go, npm, pypi) are preserved for backward compatibility
with code that calls bare functions like npm.read_version() or patches
module-level symbols like rlsbl.registries.pypi.run.
"""

from ..targets import TARGETS as REGISTRIES, detect_targets  # noqa: F401

# Re-export old registry modules for code that does:
#   from rlsbl.registries import npm, pypi, go
# These are MODULE objects with bare functions, not target instances.
from . import go, npm, pypi  # noqa: F401
