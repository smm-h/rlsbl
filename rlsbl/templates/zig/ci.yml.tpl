name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      # minimum_zig_version: {{zig.minRequiredZig}}
      - uses: mlugg/setup-zig@v1
        with:
          version: {{zig.minRequiredZig}}
      - run: zig build
      - run: zig build test
