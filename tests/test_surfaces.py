"""Every surface comes from the one tool list, and the core imports no surface library."""

import asyncio
import inspect
import json
import os
import subprocess
import sys

import pytest

from acquaint import tools
from acquaint.mcp import refs

TOOL_NAMES = [
    "who", "resolve", "check", "reach", "brief", "remember", "lint", "new", "rename",
    "forget", "sync_init", "sync_push", "sync_pull", "sync_status", "style_lint",
]
SURFACE_LIBS = {"argh", "cw", "click", "typer", "fastapi", "starlette", "uvicorn", "flask", "mcp", "fastmcp", "qh", "uf", "py2mcp"}


def _python(code, **env):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**os.environ, **env}, check=True).stdout


def test_importing_the_core_pulls_in_no_surface_library():
    loaded = json.loads(_python("import sys, json, acquaint; print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))"))
    assert not set(loaded) & SURFACE_LIBS


def test_the_tool_list_is_complete_and_classified():
    names = [t.__name__ for t in tools.TOOLS]
    assert sorted(names) == sorted(TOOL_NAMES) and len(names) == len(set(names))
    assert set(tools.SIDE_EFFECTS) == set(names)


def test_tools_take_flat_serialisable_arguments():
    allowed = {"str", "str | None", "bool"}
    for tool in tools.TOOLS:
        assert (tool.__doc__ or "").strip(), f"{tool.__name__} needs a docstring: it is the CLI help and the MCP description"
        for param in inspect.signature(tool).parameters.values():
            assert param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY), (tool.__name__, param.name)
            assert param.annotation in allowed, (tool.__name__, param.name, param.annotation)


def test_the_cli_offers_every_tool():
    help_text = subprocess.run([sys.executable, "-m", "acquaint", "--help"], capture_output=True, text=True).stdout
    sync_help = subprocess.run([sys.executable, "-m", "acquaint", "sync", "--help"], capture_output=True, text=True).stdout
    for name in TOOL_NAMES:
        if name.startswith("sync_"):
            assert name.removeprefix("sync_") in sync_help, name
        else:
            assert name.replace("_", "-") in help_text, name


def test_results_are_json_ready(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    results = [
        tools.remember("ada-lovelace", "prefers email", source="operator", data_dir=data),
        tools.who("ada", data_dir=data),
        tools.who("ada", field="aka", data_dir=data),
        tools.resolve("Lovelace", data_dir=data),
        tools.check("Ada or Lovelace", data_dir=data),
        tools.reach("ada", purpose="ask", data_dir=data),
        tools.brief("ada", purpose="ask", data_dir=data),
        tools.lint(data_dir=data),
        tools.style_lint("Great question!", recipient="ada", data_dir=data),
        tools.forget("ada", data_dir=data),
        tools.sync_status(data_dir=data),
        tools.sync_init(repo="example/profiles", dry_run=True, data_dir=data),
    ]
    for result in results:
        assert {"ok", "summary"} <= set(result), result
        json.dumps(result)


def test_mcp_exposes_only_reading_appending_and_creating_tools():
    exposed = [ref.split(":", 1)[1] for ref in refs()]
    assert exposed == [n for n in (t.__name__ for t in tools.TOOLS) if tools.SIDE_EFFECTS[n] in {"read", "append", "create"}]
    assert not {"forget", "rename", "sync_init", "sync_push", "sync_pull"} & set(exposed)


def test_mcp_server_registers_those_tools():
    pytest.importorskip("py2mcp")
    from acquaint.mcp import mk_server

    registered = sorted(t.name for t in asyncio.run(mk_server().list_tools()))
    assert registered == sorted(ref.split(":", 1)[1] for ref in refs())
