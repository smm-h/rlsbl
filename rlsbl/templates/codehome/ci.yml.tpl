name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Validate plugin.json
        run: python -c "import json; d=json.load(open('plugin.json')); assert all(d.get(f) for f in ('name','version','description')), 'Missing required fields'"
