# Configuration reference

## .rlsbl/config.json

Project-level configuration file. Created by `rlsbl config init` or `rlsbl scaffold`.

:-: table-config path=".rlsbl/config.json"

### Key reference

| Key | Type | Description |
| --- | ---- | ----------- |
| targets | array | List of target names to use (overrides auto-detection) |
| tag | bool | Enable/disable ecosystem tagging (default: true) |

Configuration precedence for tagging: CLI flag (`--no-tag`) > project config > user config (`~/.rlsbl/config.json`) > default (true).

:-: ref path="rlsbl.config"

## .rlsbl-monorepo/workspace.toml

Monorepo workspace definition. See the [monorepo guide](monorepo.md) for details.

:-: table-config path=".rlsbl-monorepo/workspace.toml"

## selfdoc.json

When present, enables the `docs` release target. See the [selfdoc documentation](https://github.com/smm-h/selfdoc) for the full schema.

:-: table-schema path="selfdoc.json"
