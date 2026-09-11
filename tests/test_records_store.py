"""Record formats (slugs, frontmatter, source tags, log entries) and the store, over both backends of the storage seam."""

import pytest

from acquaint.records import (
    format_log_entry,
    parse_log,
    slugify,
    source_problem,
    split_frontmatter,
)
from acquaint.store import AcquaintError, Store, data_dir


@pytest.mark.parametrize(
    "name, qualifier, expected",
    [
        ("Ada Lovelace", None, "ada-lovelace"),
        ("  Zoë  O'Example ", None, "zoe-o-example"),
        ("John Smith", "Example Org", "john-smith--example-org"),
    ],
)
def test_slugify(name, qualifier, expected):
    assert slugify(name, qualifier=qualifier) == expected


def test_slugify_refuses_a_name_with_nothing_to_keep():
    with pytest.raises(ValueError):
        slugify("—")


def test_frontmatter_keeps_dates_as_typed_and_degrades_on_bad_yaml():
    meta, body, errors = split_frontmatter("---\nupdated: 2026-09-11\n---\n## Who\n")
    assert meta == {"updated": "2026-09-11"} and errors == [] and body.startswith("## Who")
    meta, body, errors = split_frontmatter("---\nname: [unclosed\n---\nbody\n")
    assert meta == {} and errors and body == "body\n"


@pytest.mark.parametrize(
    "line, problem",
    [
        ("- Short replies. [source: https://example.org/thread/1]", None),
        ("- Short replies. [source: log/2026-09.md#e03]", None),
        ('- Short replies. [source: self: "keep it short"]', None),
        ("- Short replies. [source: operator]", None),
        ("- Short replies. [source: none located]", None),
        ("- Short replies.", "no [source: …] tag"),
        ("- Short replies. [source: 2026-09-11]", "a date alone is not a source"),
        ("- Short replies. [source: observed 2026-09]", "a date alone is not a source"),
        ("- Short replies. [source: self, 2026-09-11]", 'self-stated sources need the quoted words: [source: self: "…"]'),
        ("- Short replies. [source: ]", "empty [source: ] tag"),
    ],
)
def test_source_problem(line, problem):
    assert source_problem(line) == problem


def test_log_entries_round_trip():
    text = format_log_entry("e01", "2026-09-11", "observation", "first", source="operator")
    text += "\n" + format_log_entry("e02", "2026-09-12", "preference", "second\nline", source="https://example.org/x")
    assert [(e["id"], e["kind"], e["text"], e["source"]) for e in parse_log(text)] == [
        ("e01", "observation", "first", "operator"),
        ("e02", "preference", "second line", "https://example.org/x"),
    ]


def test_store_is_a_mutable_mapping_of_entities(store, put):
    put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace", "aka": ["Ada"]}, files={"log/2026-09.md": "## e01 · 2026-09-11 · observation\nhi\n"})
    put(store, "projects/engine", meta={"name": "Engine"})
    assert list(store) == ["people/ada-lovelace", "projects/engine"]
    entity = store["people/ada-lovelace"]
    assert sorted(entity) == ["PROFILE.md", "log/2026-09.md"]
    assert (entity.kind, entity.ref, entity.name) == ("person", "person:ada-lovelace", "Ada Lovelace")
    assert "people/ada-lovelace/log/2026-09.md" in store.files, "keys are '/'-separated on every platform"
    del store["projects/engine"]
    assert list(store) == ["people/ada-lovelace"]
    with pytest.raises(KeyError):
        store["projects/engine"]


def test_find_accepts_bare_ids_refs_and_keys(store, put):
    put(store, "people/sam", meta={"name": "Sam"})
    put(store, "projects/atlas", meta={"name": "Atlas"})
    put(store, "orgs/atlas", meta={"name": "Atlas Org"})
    assert store.find("sam") == store.find("person:sam") == store.find("people/sam") == "people/sam"
    assert store.find("project:atlas") == "projects/atlas"
    with pytest.raises(AcquaintError, match="more than one"):
        store.find("atlas")
    with pytest.raises(KeyError):
        store.find("nobody")


def test_a_broken_record_degrades_instead_of_breaking_lookups(store, put):
    put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace"})
    store["people/broken"] = {"PROFILE.md": "---\nname: [unclosed\n---\n", "rules.yaml": "rules: [oops"}
    assert list(store) == ["people/ada-lovelace", "people/broken"]
    broken = store["people/broken"]
    assert broken.name == "broken" and len(broken.errors) == 2
    assert store["people/ada-lovelace"].errors == []


def test_data_dir_resolution_order(tmp_path, monkeypatch):
    config_home, data_home = tmp_path / "config", tmp_path / "data"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.delenv("ACQUAINT_DATA_DIR", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert data_dir() == data_home / "acquaint"

    (config_home / "acquaint").mkdir(parents=True)
    (config_home / "acquaint" / "config.toml").write_text(f'data_dir = "{(tmp_path / "from-config").as_posix()}"\n')
    assert data_dir() == tmp_path / "from-config"

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(tmp_path / "from-env"))
    assert data_dir() == tmp_path / "from-env"
    assert data_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_a_store_on_a_missing_root_is_empty_until_written(tmp_path):
    store = Store(tmp_path / "does-not-exist-yet")
    assert list(store) == []
