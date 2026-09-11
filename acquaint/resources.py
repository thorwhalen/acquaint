"""Files shipped inside the package: record templates, the policy tripwires, purpose reminders, the tells catalogue, skills.

Read through ``importlib.resources`` so they work from a wheel, a zip or a checkout.
Shipped data is part of the code: if it does not parse, that is a bug, and it raises.
"""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

from acquaint.records import load_yaml

__all__ = ["data_path", "data_text", "data_yaml"]


def data_path(*parts: str) -> Traversable:
    """A path inside ``acquaint/data/``."""
    path = files("acquaint").joinpath("data")
    for part in parts:
        path = path.joinpath(part)
    return path


@cache
def data_text(name: str) -> str:
    """The text of a shipped data file, e.g. ``data_text("templates/POLICY.md")``."""
    return data_path(*name.split("/")).read_text(encoding="utf-8")


@cache
def data_yaml(name: str) -> Any:
    """A shipped YAML file, parsed. Raises ``ValueError`` if it does not parse."""
    data, errors = load_yaml(data_text(name))
    if errors:
        raise ValueError(f"shipped data file {name} is broken: {errors[0]}")
    return data
