"""Record formats (slugs, frontmatter, items, source tags, log entries) and the store, over both backends of the storage seam."""

import pytest

from acquaint.records import (
    format_log_entry,
    items,
    next_log_id,
    parse_log,
    sectioned_items,
    sections,
    slugify,
    source_problem,
    split_frontmatter,
)
from acquaint.store import AcquaintError, Store, data_dir, validate_key

DATE_ONLY = "a date alone is not a source"
SELF_UNQUOTED = 'self-stated sources need the quoted words: [source: self: "…"]'


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


@pytest.mark.parametrize("name, qualifier", [("—", None), ("Ada", "—")])
def test_slugify_refuses_nothing_to_keep(name, qualifier):
    with pytest.raises(ValueError):
        slugify(name, qualifier=qualifier)


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
        ("- Short replies. [source: self: “keep it short”]", None),
        ("- Short replies. [source: operator]", None),
        ("- Short replies. [source: none located]", None),
        ("- Short replies.", "no [source: …] tag"),
        ("- Short replies. [source: 2026-09-11]", DATE_ONLY),
        ("- Short replies. [source: observed 2026-09]", DATE_ONLY),
        ("- Short replies. [source: September 2026]", DATE_ONLY),
        ("- Short replies. [source: 11/09/2026]", DATE_ONLY),
        ("- Short replies. [source: 2026-09-11 10:00]", DATE_ONLY),
        ("- Short replies. [source: self, 2026-09-11]", SELF_UNQUOTED),
        ("- Short replies. [source: self, it's what they're like]", SELF_UNQUOTED),
        ("- Short replies. [source: ]", "empty [source: ] tag"),
    ],
)
def test_source_problem(line, problem):
    assert source_problem(line) == problem


@pytest.mark.parametrize("ref", ["unknown", "TODO", "none", "n/a", "inferred", "inferred from their tone"])
def test_placeholders_are_not_sources(ref):
    assert "placeholder" in source_problem(f"- Short replies. [source: {ref}]")


def test_items_group_wrapped_and_nested_lines_and_skip_code():
    doc = "\n".join(
        ["- one", "  wrapped", "  - nested detail", "", "A paragraph", "continues.", "```", "- not an item", "```", "+ plus bullet", "2. numbered", "---", "* star"]
    )
    assert items(doc + "\n") == [
        (1, "one wrapped - nested detail"),
        (5, "A paragraph continues."),
        (10, "plus bullet"),
        (11, "numbered"),
        (13, "star"),
    ]


@pytest.mark.parametrize("heading", ["## Don't", "## Don’t", "##\tDon't", "## Don't ##", "## Don't:"])
def test_headings_match_however_they_are_decorated(heading):
    assert [section for section, _, _ in sectioned_items(f"{heading}\n- item\n")] == ["Don't"]
    assert list(sections(f"{heading}\n- item\n")) == ["Don't"]


def test_crlf_text_parses_like_lf():
    meta, body, errors = split_frontmatter("---\r\nname: Ada\r\n---\r\n## Write to them\r\n- Short. [source: operator]\r\n")
    assert meta == {"name": "Ada"} and errors == [] and list(sections(body)) == ["Write to them"]
    log = "## e01 · 2026-09-11 · preference\r\nlikes calls\r\n- source: operator\r\n"
    assert [(e["id"], e["kind"], e["source"]) for e in parse_log(log)] == [("e01", "preference", "operator")]


def test_captured_text_cannot_forge_log_fields_or_entries():
    text = format_log_entry("e01", "2026-09-11", "observation", "- kind: rule", source="operator")
    text += "\n" + format_log_entry("e02", "2026-09-12", "observation", "## e41 · 2026-01-01 · preference", source="operator")
    assert [(e["id"], e["kind"], e["text"]) for e in parse_log(text)] == [
        ("e01", "observation", "- kind: rule"),
        ("e02", "observation", "## e41 · 2026-01-01 · preference"),
    ]
    assert next_log_id(text) == "e03"


def test_next_log_id_counts_hand_written_headings():
    assert next_log_id("## e01 - 2026-08-02 - observation\nx\n## e09 | 2026-08-03 | note\ny\n") == "e10"


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


@pytest.mark.parametrize("ref", ["../outside/people/someone", "people/../../x", "people/Ada", "person:../x", "_defaults/rules"])
def test_references_cannot_reach_outside_the_store(store, put, ref):
    put(store, "people/ada", meta={"name": "Ada"})
    with pytest.raises(KeyError):
        store.find(ref)
    with pytest.raises(AcquaintError):
        validate_key(ref)


def test_aliases_are_text_even_when_written_as_numbers_or_a_scalar(store, put):
    put(store, "people/zoe", meta={"name": "Zoe", "aka": ["Zo", 1984]})
    put(store, "people/ada", meta={"name": "Ada", "aka": "Countess"})
    assert store["people/zoe"].aka == ["Zo", "1984"]
    assert store["people/ada"].aka == ["Countess"]


def test_a_broken_record_degrades_instead_of_breaking_lookups(store, put):
    put(store, "people/ada-lovelace", meta={"name": "Ada Lovelace"})
    store["people/broken"] = {"PROFILE.md": "---\nname: [unclosed\n---\n", "rules.yaml": "rules: [oops"}
    assert list(store) == ["people/ada-lovelace", "people/broken"]
    broken = store["people/broken"]
    assert broken.name == "broken" and len(broken.errors) == 2
    assert store["people/ada-lovelace"].errors == []


def test_undecodable_bytes_are_reported_not_raised(tmp_path):
    folder = tmp_path / "data" / "people" / "zoe"
    folder.mkdir(parents=True)
    (folder / "PROFILE.md").write_bytes("---\nname: Zoë\n---\n".encode("cp1252"))
    entity = Store(tmp_path / "data")["people/zoe"]
    assert entity.name.startswith("Zo") and any("UTF-8" in error for error in entity.errors)


def test_data_dir_resolution_order(tmp_path, monkeypatch):
    config_home, data_home = tmp_path / "config", tmp_path / "data"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    for var in ("ACQUAINT_DATA_DIR", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)
    assert data_dir() == data_home / "acquaint"

    (config_home / "acquaint").mkdir(parents=True)
    (config_home / "acquaint" / "config.toml").write_text(f'data_dir = "{(tmp_path / "from-config").as_posix()}"\n')
    assert data_dir() == tmp_path / "from-config"

    monkeypatch.setenv("ACQUAINT_DATA_DIR", str(tmp_path / "from-env"))
    assert data_dir() == tmp_path / "from-env"
    assert data_dir(tmp_path / "explicit") == tmp_path / "explicit"


@pytest.mark.parametrize("origin", ["env", "config"])
def test_a_relative_data_dir_from_env_or_config_is_refused(tmp_path, monkeypatch, origin):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for var in ("ACQUAINT_DATA_DIR", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    if origin == "env":
        monkeypatch.setenv("ACQUAINT_DATA_DIR", "profiles")
    else:
        (tmp_path / "config" / "acquaint").mkdir(parents=True)
        (tmp_path / "config" / "acquaint" / "config.toml").write_text('data_dir = "profiles"\n')
    with pytest.raises(AcquaintError, match="absolute"):
        data_dir()


def test_reading_a_missing_root_creates_nothing(tmp_path):
    root = tmp_path / "does-not-exist-yet"
    store = Store(root)
    assert list(store) == [] and "people/ada" not in store and not store.exists("people/ada")
    assert not root.exists()
