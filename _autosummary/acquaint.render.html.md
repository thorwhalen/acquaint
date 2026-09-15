# acquaint.render

Turning a tool’s result into terminal output: `(stdout, stderr, exit code)`.

Used by the CLI only. The rules, in order: a one-field lookup prints just the value
(one line per item, so it pipes); otherwise the long `text` if there is one; otherwise
the `summary`. A result with `ok: False` exits 1 and puts its summary on stderr.
A result whose `outcome` is in `EXIT_CODES` exits with that code instead, so a
script can tell it apart from both success and failure (2 stays the usage error). An
outcome name means the same thing in every tool that uses it.

```pycon
>>> render({"ok": True, "value": ["Ada", "Lovelace"], "summary": "…"})
('Ada\nLovelace', '', 0)
>>> render({"ok": False, "summary": "no match for 'x'"})
('', "no match for 'x'", 1)
>>> render({"ok": False, "outcome": "no_address", "text": "1. pager  [self]", "summary": "no pager address"})
('1. pager  [self]', 'no pager address', 3)
```

### Functions

| [`exit_code`](#acquaint.render.exit_code)(result)   | The exit code for one tool result: its `outcome`'s code if it has one, else 0 if `ok`, else 1.   |
|----------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| [`render`](#acquaint.render.render)(result)      | `(stdout, stderr, exit_code)` for one tool result.                                               |

### acquaint.render.exit_code(result)

The exit code for one tool result: its `outcome`’s code if it has one, else 0 if `ok`, else 1.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### acquaint.render.render(result)

`(stdout, stderr, exit_code)` for one tool result.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`int`](https://docs.python.org/3/builtins/functions.html#int)]
