"""Every surface comes from the one tool list, the core imports no surface library, and no surface acts on a guess."""

import asyncio
import inspect
import json
import os
import subprocess
import sys

import pytest

from acquaint import tools
from acquaint.mcp import refs
from acquaint.store import AcquaintError

TOOL_NAMES = [
    "who", "resolve", "check", "reach", "brief", "remember", "lint", "new", "rename",
    "forget", "sync_init", "sync_push", "sync_pull", "sync_status", "style_lint",
]
SURFACE_LIBS = {"argh", "cw", "click", "typer", "fastapi", "starlette", "uvicorn", "flask", "mcp", "fastmcp", "qh", "uf", "py2mcp"}
EFFECTS = {"read", "append", "create", "rewrite", "destructive", "external-read", "external"}


def _python(code):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ), check=True).stdout


def test_importing_the_core_pulls_in_no_surface_library():
    loaded = json.loads(_python("import sys, json, acquaint; print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))"))
    assert not set(loaded) & SURFACE_LIBS


def test_the_tool_list_is_complete_and_classified():
    names = [t.__name__ for t in tools.TOOLS]
    assert sorted(names) == sorted(TOOL_NAMES) and len(names) == len(set(names))
    assert set(tools.SIDE_EFFECTS) == set(names) and set(tools.SIDE_EFFECTS.values()) <= EFFECTS


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
        tools.forget("ada-lovelace", data_dir=data),
        tools.sync_status(data_dir=data),
        tools.sync_init(repo="example/profiles", dry_run=True, data_dir=data),
    ]
    for result in results:
        assert {"ok", "summary"} <= set(result), result
        json.dumps(result)


def test_no_tool_acts_on_a_partial_name(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Joanna Smith", data_dir=data)
    looked_up = tools.who("ann", field="email", data_dir=data)
    assert looked_up["ok"] is False and [c["id"] for c in looked_up["candidates"]] == ["joanna-smith"]
    for call in (
        lambda: tools.brief("ann", data_dir=data),
        lambda: tools.remember("ann", "likes calls", source="operator", data_dir=data),
        lambda: tools.forget("Joanna", confirm=True, data_dir=data),
        lambda: tools.rename("Joanna", "jo-smith", data_dir=data),
    ):
        with pytest.raises(AcquaintError):
            call()
    assert tools.who("joanna-smith", data_dir=data)["ok"], "nothing was changed"


def test_resolve_is_ok_only_for_an_active_identity_on_a_named_platform(tmp_path):
    data = str(tmp_path)
    tools.new("person", "Ada Lovelace", data_dir=data)
    tools.remember("ada-lovelace", "github:octocat", kind="identity", source="operator", data_dir=data)
    assert tools.resolve("github:octocat", data_dir=data)["ok"]
    assert not tools.resolve("@octocat", data_dir=data)["ok"]
    assert not tools.resolve("Ada", data_dir=data)["ok"]


def test_mcp_exposes_only_local_reading_appending_and_creating_tools():
    exposed = [ref.split(":", 1)[1] for ref in refs()]
    assert exposed == [n for n in (t.__name__ for t in tools.TOOLS) if tools.SIDE_EFFECTS[n] in {"read", "append", "create"}]
    assert not {"forget", "rename", "sync_init", "sync_push", "sync_pull", "sync_status"} & set(exposed)


def test_mcp_server_registers_those_tools_without_data_dir():
    pytest.importorskip("py2mcp")
    from acquaint.mcp import mk_server

    registered = asyncio.run(mk_server().list_tools())
    assert sorted(t.name for t in registered) == sorted(ref.split(":", 1)[1] for ref in refs())
    for tool in registered:
        assert "data_dir" not in (tool.parameters or {}).get("properties", {}), tool.name
