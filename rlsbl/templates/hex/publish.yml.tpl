name: Publish

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: erlef/setup-beam@v1
        with:
          otp-version: "26"
          elixir-version: "1.16"
      - run: mix deps.get
      - run: mix hex.publish --yes
        env:
          HEX_API_KEY: ${{ secrets.HEX_API_KEY }}
