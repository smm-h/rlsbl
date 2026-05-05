"""Release target protocol -- the formal interface all targets must implement."""

from typing import Protocol, Literal, runtime_checkable


@runtime_checkable
class ReleaseTarget(Protocol):
    """Protocol defining a release target.

    Targets handle version management, scaffolding templates, and optionally
    build/publish steps for a specific ecosystem (npm, pypi, go, codehome, docs, etc.)
    """

    @property
    def name(self) -> str:
        """Unique identifier for this target (e.g. 'npm', 'pypi', 'codehome')."""
        ...

    @property
    def scope(self) -> Literal["root", "subdir"]:
        """Whether this target operates on the whole repo or a subdirectory."""
        ...

    def detect(self, dir_path: str) -> bool:
        """Check if this target is present/applicable in the given directory."""
        ...

    def read_version(self, dir_path: str) -> str:
        """Read the current version from the target's manifest file."""
        ...

    def write_version(self, dir_path: str, version: str) -> None:
        """Write a new version to the target's manifest file (atomic)."""
        ...

    def version_file(self) -> str | None:
        """Filename that holds the version (e.g. 'package.json'), or None if inherited."""
        ...

    def tag_format(self, name: str | None, version: str) -> str:
        """Format the git tag for a release.

        name is the scoped component name (for subdir targets), version is the new version.
        Root targets typically ignore name and return f'v{version}'.
        Subdir targets return f'{name}@v{version}'.
        """
        ...

    # --- Optional: Scaffold support ---

    def template_dir(self) -> str | None:
        """Absolute path to target-specific template directory, or None."""
        return None

    def shared_template_dir(self) -> str | None:
        """Absolute path to shared template directory, or None."""
        return None

    def template_vars(self, dir_path: str) -> dict[str, str]:
        """Extract template placeholder values from the project."""
        return {}

    def template_mappings(self) -> list[dict[str, str]]:
        """Target-specific template-to-output-path mappings."""
        return []

    def shared_template_mappings(self) -> list[dict[str, str]]:
        """Shared template-to-output-path mappings."""
        return []

    def check_project_exists(self, dir_path: str) -> bool:
        """Check if the target's project file exists (alias for detect)."""
        return self.detect(dir_path)

    def get_project_init_hint(self) -> str:
        """Human-readable hint for initializing a project for this target."""
        return ""

    # --- Optional: Build and publish ---

    def build(self, dir_path: str, version: str) -> None:
        """Pre-publish build step (e.g. generate docs). No-op by default."""
        pass

    def publish(self, dir_path: str, version: str) -> None:
        """Post-push publish/deploy step. No-op by default."""
        pass
