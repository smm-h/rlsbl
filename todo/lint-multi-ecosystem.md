# Library lint: Go and npm ecosystem support

Status: Proposed
Priority: Medium

## Context

The library lint module (rlsbl/lint.py) currently only supports Python via AST analysis. The original design called for Go and npm support as well.

## Go lint rules for libraries

- No `func main()` in library packages (entry point check)
- No `net/http` server imports (cobra, urfave/cli) — detect via import path scanning in .go files
- No `fmt.Println` / `os.Stdout.Write` (stdout check)
- Parse: use regex or go/ast (would require shelling out to a Go tool, or regex-based scanning of .go files)

## npm lint rules for libraries

- No `"bin"` field in package.json (entry point check)
- No framework imports: express, koa, hono, commander, yargs — detect via package.json dependencies and import scanning
- No `console.log` in source files (stdout check)
- Parse: regex-based scanning of .js/.ts files, or use a JS AST parser (would add a dependency)

## Design notes

The simplest approach for both: regex-based scanning of source files for forbidden patterns, similar to how the Python linter uses AST but adapted for each language's syntax. Go has clean import blocks that are easy to parse with regex. JS/TS imports are more varied (require, import, dynamic import).

The `.rlsbl/lint.toml` ignore list already works for any ecosystem — just add the module name to ignore.

## Effort

Medium. Go is straightforward (clean syntax). npm/JS is messier (multiple import styles, TypeScript variants).
