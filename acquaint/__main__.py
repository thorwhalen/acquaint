# PYTHON_ARGCOMPLETE_OK
"""``acquaint`` on the command line: ``cw`` over :data:`acquaint.tools.TOOLS`, with ``sync_*`` as a ``sync`` group.

``--json`` anywhere prints the tool's result dict instead of text; ``-`` as the text
of ``check`` or ``style-lint`` reads it from stdin. The exit status is the same either
way (:func:`acquaint.render.exit_code`).
"""

import functools
import json
import sys
from pathlib import Path

import cw

from acquaint import tools
from acquaint.render import exit_code, render


def _command(func):
    @functools.wraps(func)
    def command(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (tools.AcquaintError, ValueError) as error:
            raise cw.CommandError(str(error)) from error

    return command


def _audience_json(value):
    """``--audience-json``: ``-`` reads stdin, text starting with ``{`` is the record itself, anything else is a file."""
    if value in (None, ""):
        return None
    if value == "-":
        return sys.stdin.read()
    if value.lstrip().startswith("{"):
        return value
    try:
        return Path(value).read_text(encoding="utf-8")
    except OSError as error:
        raise tools.AcquaintError(
            f"--audience-json {value}: {error.strerror or error}"
        ) from error


def _egress(as_json):
    def egress(result, *, out, err):
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False), file=out)
            return exit_code(result)
        stdout, stderr, code = render(result)
        print(stderr, file=err) if stderr else None
        print(stdout, file=out) if stdout else None
        return code

    return egress


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # a cp1252 pipe must not crash on "·" or "→"
        getattr(stream, "reconfigure", lambda **_: None)(errors="backslashreplace")
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    commands = {
        f.__name__.replace("_", "-"): _command(f)
        for f in tools.TOOLS
        if not f.__name__.startswith("sync_")
    }
    commands["sync"] = {
        f.__name__.removeprefix("sync_"): _command(f)
        for f in tools.TOOLS
        if f.__name__.startswith("sync_")
    }
    stdin = {"text": {"codec": lambda text: sys.stdin.read() if text == "-" else text}}
    disclosure = {
        "projects": {
            "flags": ["--project"],
            "action": "extend",
            "nargs": "+",
            "dest": "projects",
        },
        "audience": {
            "flags": ["--audience-json"],
            "dest": "audience",
            "codec": _audience_json,
        },
    }
    brief = {"audience": disclosure["audience"]}
    config = {
        "check": stdin,
        "style-lint": stdin,
        "disclosure": disclosure,
        "brief": brief,
    }
    args = [a for a in argv if a != "--json"]
    try:
        code = cw.dispatch(
            commands,
            args,
            prog="acquaint",
            convention=cw.MODERN,
            egress=_egress(as_json),
            config=config,
        )
    except (
        tools.AcquaintError
    ) as error:  # raised while decoding an argument, before any tool runs
        print(f"acquaint: {error}", file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
