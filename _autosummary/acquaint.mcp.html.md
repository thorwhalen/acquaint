# acquaint.mcp

MCP over stdio: the same tools, for Claude Desktop and other local MCP clients.

Run `acquaint-mcp` (install the extra first: `pip install "acquaint[mcp]"`). The
exposed tools are named by `acquaint.tools:<name>` reference, so the core never imports
an MCP library. By default only tools that read locally, append or create are exposed;
renaming, forgetting and syncing are operator actions and stay at the terminal.

The data root is the server’s, never the model’s: `data_dir` is removed from every
tool’s schema, so a model cannot write profiles into whatever directory it is working
in. `remember`’s `reactivate` is removed too: making an inactive identity active
again changes a recorded status, which is the operator’s call. Point the server
elsewhere with `ACQUAINT_DATA_DIR` in the client configuration:

```default
{"mcpServers": {"acquaint": {"command": "acquaint-mcp"}}}
```

### Functions

| [`main`](#acquaint.mcp.main)()                   | Serve the default tools over stdio.                                                      |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`mk_server`](#acquaint.mcp.mk_server)(\*[, effects]) | A FastMCP server over the selected tools, with `HIDDEN_PARAMETERS` hidden (not started). |
| [`refs`](#acquaint.mcp.refs)(\*[, effects])      | `acquaint.tools:<name>` references for the tools whose side effects are in `effects`.    |

### acquaint.mcp.main()

Serve the default tools over stdio.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### acquaint.mcp.mk_server(, effects=('read', 'append', 'create'))

A FastMCP server over the selected tools, with `HIDDEN_PARAMETERS` hidden (not started).

### acquaint.mcp.refs(, effects=('read', 'append', 'create'))

`acquaint.tools:<name>` references for the tools whose side effects are in `effects`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> "acquaint.tools:brief" in refs(), "acquaint.tools:forget" in refs(), "acquaint.tools:sync_status" in refs()
(True, False, False)
```
