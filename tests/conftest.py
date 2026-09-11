"""Shared fixtures: a store on both backends of the storage seam, and a helper to write a record."""

import pytest

from acquaint.records import join_frontmatter
from acquaint.store import Store

TODAY = "2026-09-11"


def _put(store, key, *, meta=None, body="", files=None):
    slug = key.split("/", 1)[1]
    store[key] = {"PROFILE.md": join_frontmatter({"id": slug, **(meta or {})}, body), **(files or {})}
    return store[key]


@pytest.fixture
def put():
    """``put(store, "people/ada-lovelace", meta={...}, body="## Who\\n…", files={"rules.yaml": "…"})``."""
    return _put


@pytest.fixture(params=["dict", "files"])
def store(request, tmp_path):
    """The same tests run over a plain ``dict`` and over the default ``dol`` files store."""
    return Store(files={}) if request.param == "dict" else Store(tmp_path / "data")
