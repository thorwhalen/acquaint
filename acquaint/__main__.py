# PYTHON_ARGCOMPLETE_OK
"""``acquaint`` on the command line: ``cw`` over :data:`acquaint.tools.TOOLS`, with ``sync_*`` as a ``sync`` group.

``--json`` anywhere prints the tool's result dict instead of text; ``-`` as the text
of ``check`` or ``style-lint`` reads it from stdin.
"""

import functools
import json
import sys

import cw

from acquaint import tools
from acquaint.render import render


def _command(func):
    @functools.wraps(func)
    def command(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (tools.AcquaintError, ValueError) as error:
            raise cw.CommandError(str(error)) from error

    return command


def _egress(as_json):
    def egress(result, *, out, err):
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False), file=out)
            return 0 if result.get("ok", True) else 1
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
    commands = {f.__name__.replace("_", "-"): _command(f) for f in tools.TOOLS if not f.__name__.startswith("sync_")}
    commands["sync"] = {f.__name__.removeprefix("sync_"): _command(f) for f in tools.TOOLS if f.__name__.startswith("sync_")}
    stdin = {"text": {"codec": lambda text: sys.stdin.read() if text == "-" else text}}
    config = {"check": stdin, "style-lint": stdin}
    args = [a for a in argv if a != "--json"]
    raise SystemExit(cw.dispatch(commands, args, prog="acquaint", convention=cw.MODERN, egress=_egress(as_json), config=config))


if __name__ == "__main__":
    main()
