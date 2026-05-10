#!/usr/bin/env bash
# Post-release hook for private repositories.
# Builds artifacts and uploads them to the GitHub Release.
# Environment: RLSBL_VERSION is set to the released version.

set -euo pipefail

version="$RLSBL_VERSION"
echo "Post-release (private): v$version"

# Detect project type and build artifacts
if [ -f "pyproject.toml" ]; then
    echo "Building Python package..."
    rm -rf dist/
    uv build
elif [ -f "package.json" ]; then
    echo "Packing npm package..."
    rm -rf dist/
    mkdir -p dist
    npm pack --pack-destination ./dist/
elif [ -f "go.mod" ]; then
    echo "Building Go binary..."
    mkdir -p dist/
    go build -o ./dist/
else
    echo "Warning: no recognized project file found, skipping build."
    exit 0
fi

# Upload artifacts to GitHub Release
if ls dist/* 1>/dev/null 2>&1; then
    echo "Uploading artifacts to GitHub Release v$version..."
    gh release upload "v$version" ./dist/* --clobber
    echo "Artifacts uploaded successfully."
else
    echo "Warning: no artifacts found in dist/ to upload."
fi
