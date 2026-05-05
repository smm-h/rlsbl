"""Loading and validating .rlsbl/docs.toml configuration."""

import os
import tomllib


# Required top-level sections and their required keys
_REQUIRED = {
    "source": ["type", "paths"],
    "output": ["dir"],
    "deploy": ["provider"],
}

# Valid values for constrained fields
_VALID_SOURCE_TYPES = ("python",)
_VALID_PROVIDERS = ("cloudflare-pages", "github-pages")


class DocsConfigError(ValueError):
    """Raised when docs.toml has invalid or missing fields."""

    pass


def load_docs_config(dir_path):
    """Load .rlsbl/docs.toml, return config dict or None if not found.

    Expected format:
        [source]
        type = "python"
        paths = ["src/", "rlsbl/"]

        [output]
        dir = "docs/_build"

        [deploy]
        provider = "cloudflare-pages"  or "github-pages"
        project = "my-docs"            (required for cloudflare-pages)
        domain = "docs.example.com"    (optional custom domain)

    Returns parsed dict on success, None if file doesn't exist.
    Raises DocsConfigError on validation failure.
    """
    config_path = os.path.join(dir_path, ".rlsbl", "docs.toml")
    if not os.path.exists(config_path):
        return None

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    _validate(data, config_path)
    return data


def _validate(data, config_path):
    """Validate required sections and fields in the parsed config."""
    for section, keys in _REQUIRED.items():
        if section not in data:
            raise DocsConfigError(
                f"Missing required section [{section}] in {config_path}"
            )
        for key in keys:
            if key not in data[section]:
                raise DocsConfigError(
                    f"Missing required key '{key}' in [{section}] in {config_path}"
                )

    # Validate source.type
    source_type = data["source"]["type"]
    if source_type not in _VALID_SOURCE_TYPES:
        raise DocsConfigError(
            f"Invalid source.type '{source_type}' in {config_path}; "
            f"must be one of: {', '.join(_VALID_SOURCE_TYPES)}"
        )

    # Validate source.paths is a non-empty list
    paths = data["source"]["paths"]
    if not isinstance(paths, list) or len(paths) == 0:
        raise DocsConfigError(
            f"source.paths must be a non-empty list in {config_path}"
        )

    # Validate deploy.provider
    provider = data["deploy"]["provider"]
    if provider not in _VALID_PROVIDERS:
        raise DocsConfigError(
            f"Invalid deploy.provider '{provider}' in {config_path}; "
            f"must be one of: {', '.join(_VALID_PROVIDERS)}"
        )

    # Cloudflare requires a project name
    if provider == "cloudflare-pages" and "project" not in data["deploy"]:
        raise DocsConfigError(
            f"deploy.project is required when provider is 'cloudflare-pages' "
            f"in {config_path}"
        )
