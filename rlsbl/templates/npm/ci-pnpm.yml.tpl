name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        # engines.node: >= {{npm.minRequiredNode}}
        node-version: [20, 22, 24]
    steps:
      - uses: actions/checkout@v6
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v6
        with:
          node-version: ${{ matrix.node-version }}
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
      - run: pnpm audit --audit-level=moderate || true
