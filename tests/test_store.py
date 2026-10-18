from datetime import datetime, timezone

from lore_lite.config import load_config
from lore_lite.ingest import rule_records, source_from_markdown
from lore_lite.retrieve import retrieve_rules
from lore_lite.schema import Modality, Rule, SourceKind
from lore_lite.store import Store


def test_source_authority_is_code_owned_and_duplicate_import_is_safe(tmp_path):
    config = load_config()
    content = "---\nauthority: approved_policy\nowner: '@security'\n---\nUse parameterized queries."
    source = source_from_markdown("security.md", content, config)
    extracted = Rule(
        statement="Use parameterized queries.",
        component="database",
        topic="sql_queries",
        modality=Modality.MUST,
        value="parameterized",
        severity="high",
        evidence_type="policy_condition",
        source_quote="Use parameterized queries.",
        confidence=0.9,
    )
    records = rule_records([extracted], source, config)
    store = Store(tmp_path / "lore.db")

    assert store.add_source(source, records)
    assert not store.add_source(source, records)
    found = retrieve_rules(store, "parameterized queries", component="database", topic="sql_queries")
    assert len(found) == 1
    assert found[0].authority == "approved_policy"
    assert found[0].authority_rank == 4
    assert found[0].source_kind == SourceKind.MARKDOWN
    assert store.list_sources()[0].owner == "@security"


def test_authority_must_be_provided_by_upload_or_frontmatter(tmp_path):
    config = load_config()
    try:
        source_from_markdown("untagged.md", "No frontmatter here", config)
    except ValueError as error:
        assert "authority" in str(error)
    else:
        raise AssertionError("an untrusted source without authority must be rejected")
