Seams: (1) record store `Store(files=)` = dol TextFiles under the data root · (2) sync remote `sync_init(remote_url=)` = the private GitHub repo's SSH URL · (3) command runner `run=` in `acquaint.sync` = subprocess · (4) tells catalogue `catalog=` in `acquaint.deslop` = shipped YAML.
Surfaces built: CLI (`cw` over `acquaint.tools`), shipped skills + agents (`acquaint/data/`), MCP over stdio (`py2mcp` string refs, `[mcp]` extra). Asked, not built: remote MCP / HTTP.
Rationale and the provisional defaults: the "v0.1 architecture: seams and surfaces" Discussion.

# acquaint — dev map

## Seam table (decided before the first commit)

| # | Seam | v0.1 default (no new dependency) | Replacement you can point at |
|---|---|---|---|
| 1 | where records live: `Store(files=)` | `dol.TextFiles` under the data root (`ACQUAINT_DATA_DIR` → `~/.config/acquaint/config.toml` → `~/.local/share/acquaint`) | any `MutableMapping[str, str]`: a `dict` (tests), `sshdol` / `s3dol` stores |
| 2 | the sync remote: `sync_init(remote_url=)` | the private GitHub repo's SSH URL, read from `gh` | a `gcrypt::` URL (git-remote-gcrypt; needs guard support first, issue #13); a local bare repo reached through `insteadOf` (tests) |
| 3 | how `git` / `gh` run: `run=` in `acquaint.sync` | `subprocess.run` | the scripted fake runner in the sync tests |
| 4 | the tells catalogue: `catalog=` in `acquaint.deslop` | `acquaint/data/deslop/tells.yaml` | an over-representation list computed from the operator's own writing, or the Vale `signs-of-ai-writing` rules |

```
Surfaces for v0.1: CLI + shipped skills/agents + MCP stdio (py2mcp string refs); remote MCP / HTTP asked, not built
NOT seams: layout and file names, slug rule, the [source: …], [label: …] and [sealed-from: …] tag grammar, the trust.yaml shape, the tier and label vocabularies, PROFILE section names, reach precedence order, catalogue file schema, CLI rendering, the pre-push hook body, commit-message format, config file format
```

## Rules for working in this repo

- **No real person's data, anywhere**: code, tests, fixtures, docs, examples, issues, commit messages, PR text. Use fictional people (`ada-lovelace`, `example-org`) and `example.org` addresses. `tests/test_no_personal_data.py` enforces the mechanical part; the rest is on you.
- `acquaint/tools.py` is the SSOT. Every surface (CLI, MCP, skills) is generated from or written against that one list. Never author a second list of operations.
- Dependency-injection parameters (`files=`, `run=`, `catalog=`) live in the core modules. `tools.py` takes flat, serializable arguments only, so the CLI and MCP adapters stay one-liners.
- Importing `acquaint` must not import `cw`, `py2mcp` or `fastmcp` (a test checks this).
- Profile data never lives in this repository. The default data root is outside it, and tests use a temporary one.
