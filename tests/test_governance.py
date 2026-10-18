from datetime import date, datetime, timezone

from lore_lite.config import load_config
from lore_lite.governance import govern_query
from lore_lite.schema import (
    DecisionTypeConfig,
    LoreConfig,
    Modality,
    Rule,
    RuleRecord,
    RuleStatus,
    SourceKind,
    SourceRecord,
)
from lore_lite.store import Store


def _insert_rule(store: Store, *, source_name: str, authority: str, rank: int,
                 statement: str, value: str, quote: str, effective_date: date | None = None,
                 evidence_type: str = "policy_condition") -> RuleRecord:
    source_id = source_name
    source = SourceRecord(
        id=source_id,
        path=f"{source_name}.md",
        kind=SourceKind.MARKDOWN,
        content_hash=(source_id.encode().hex() * 64)[:64],
        authority=authority,
        imported_at=datetime.now(timezone.utc),
        effective_date=effective_date,
    )
    rule = RuleRecord(
        statement=statement,
        component="database",
        topic="sql_queries",
        modality=Modality.MUST if value == "parameterized" else Modality.MAY,
        value=value,
        severity="high",
        evidence_type=evidence_type,
        source_quote=quote,
        confidence=0.9,
        rule_id=f"{source_name}-rule",
        source_id=source.id,
        source_path=source.path,
        source_location=None,
        authority=authority,
        authority_rank=rank,
        source_kind=source.kind,
        effective_date=effective_date,
        status=RuleStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    assert store.add_source(source, [rule])
    return rule


def test_policy_overrides_wiki_and_is_qualified(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy", authority="approved_policy", rank=4,
                 statement="Use parameterized queries.", value="parameterized",
                 quote="Parameterized queries are required.")
    _insert_rule(store, source_name="wiki", authority="wiki_entry", rank=2,
                 statement="Raw SQL is fine for reports.", value="raw_sql",
                 quote="Raw SQL strings are fine for reporting.")

    result = govern_query(store, load_config(), "Can I use raw SQL for reporting?")

    assert result.envelope.state.value == "qualified"
    assert [item.authority for item in result.envelope.items] == ["approved_policy"]
    assert [item.rule_id for item in result.envelope.overridden] == ["wiki-rule"]
    assert store.get_decision(result.envelope.decision_id) is not None


def test_equal_rank_disagreement_remains_conflicting(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy-a", authority="approved_policy", rank=4,
                 statement="Use parameterized queries.", value="parameterized",
                 quote="Parameterized queries are required.")
    _insert_rule(store, source_name="policy-b", authority="approved_policy", rank=4,
                 statement="Raw SQL is allowed.", value="raw_sql",
                 quote="Raw SQL is allowed for reports.")

    result = govern_query(store, load_config(), "Can I use SQL for reports?")

    assert result.envelope.state.value == "conflicting"
    assert result.envelope.directive.value == "ask_user"
    assert result.envelope.notes


def test_vendor_question_lists_missing_evidence(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy", authority="approved_policy", rank=4,
                 statement="Vendors need an assessment.", value="required",
                 quote="Vendors need an assessment before processing customer data.")

    result = govern_query(store, load_config(), "Can we approve a vendor for sensitive customer data?")

    assert result.envelope.state.value == "insufficient"
    assert result.envelope.missing_evidence == ["assessment_report", "data_residency_proof"]


def test_rule_requiring_assessment_does_not_count_as_assessment_evidence(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy", authority="approved_policy", rank=4,
                 statement="An assessment report is required.", value="required",
                 quote="An assessment report is required.", evidence_type="assessment_report")

    result = govern_query(store, load_config(), "Can we approve a vendor for sensitive customer data?")

    assert result.envelope.state.value == "insufficient"
    assert "assessment_report" in result.envelope.missing_evidence


def test_unknown_topic_returns_no_knowledge(tmp_path):
    result = govern_query(Store(tmp_path / "lore.db"), load_config(), "What logging format do we use?")
    assert result.envelope.state.value == "no_knowledge"
    assert result.envelope.items == []


def test_eligible_same_kind_recency_resolves_equal_rank(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy-old", authority="approved_policy", rank=4,
                 statement="Use raw SQL.", value="raw_sql", quote="Use raw SQL for reports.",
                 effective_date=date(2026, 1, 1))
    _insert_rule(store, source_name="policy-new", authority="approved_policy", rank=4,
                 statement="Use parameterized SQL.", value="parameterized",
                 quote="Use parameterized SQL for reports.", effective_date=date(2026, 2, 1))

    result = govern_query(store, load_config(), "Which SQL reports can I run?")

    assert result.envelope.state.value == "qualified"
    assert [item.rule_id for item in result.envelope.items] == ["policy-new-rule"]
    assert [item.rule_id for item in result.envelope.overridden] == ["policy-old-rule"]


def test_conflicting_state_precedes_missing_evidence(tmp_path):
    store = Store(tmp_path / "lore.db")
    _insert_rule(store, source_name="policy-a", authority="approved_policy", rank=4,
                 statement="Use parameterized queries.", value="parameterized",
                 quote="Parameterized queries are required.")
    _insert_rule(store, source_name="policy-b", authority="approved_policy", rank=4,
                 statement="Raw SQL is allowed.", value="raw_sql",
                 quote="Raw SQL is allowed for reports.")
    config = LoreConfig(
        authority_ladder={"approved_policy": 4},
        decision_types={"code_change": DecisionTypeConfig(required_evidence=["assessment_report"])},
    )

    result = govern_query(store, config, "Can I use raw SQL for reports?")

    assert result.envelope.state.value == "conflicting"
    assert result.envelope.missing_evidence == ["assessment_report"]
