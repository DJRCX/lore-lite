"""Deterministic query classification, authority resolution, and sufficiency."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from lore_lite.retrieve import retrieve_rules
from lore_lite.schema import (
    DecisionRecord,
    Directive,
    EvidenceStatus,
    LoreConfig,
    OverriddenRule,
    ResultEnvelope,
    ResultItem,
    ResultState,
    RuleRecord,
)
from lore_lite.store import Store


@dataclass
class ConflictGroup:
    component: str
    topic: str
    rules: list[RuleRecord]
    resolved: bool
    reason: str | None = None


@dataclass
class GovernanceOutcome:
    envelope: ResultEnvelope
    decision_type: str
    retrieved_rules: list[RuleRecord] = field(default_factory=list)
    conflicts: list[ConflictGroup] = field(default_factory=list)


_VENDOR_TERMS = re.compile(r"\b(vendor|third.party|cloudbox|provider|procurement)\b|customer\s+data|sensitive\s+data", re.I)


def classify_decision_type(query: str, config: LoreConfig) -> str:
    """Classify vendor approval questions; use the configured code-change fallback."""
    if "vendor_approval" in config.decision_types and _VENDOR_TERMS.search(query):
        return "vendor_approval"
    if "code_change" in config.decision_types:
        return "code_change"
    return next(iter(config.decision_types))


def resolve_conflicts(rules: list[RuleRecord]) -> tuple[list[RuleRecord], list[OverriddenRule], list[ConflictGroup], bool]:
    """Resolve disagreements by rank, then eligible same-kind effective-date recency."""
    groups: dict[tuple[str, str], list[RuleRecord]] = {}
    for rule in rules:
        groups.setdefault((rule.component.casefold(), rule.topic.casefold()), []).append(rule)

    kept: list[RuleRecord] = []
    overridden: list[OverriddenRule] = []
    conflicts: list[ConflictGroup] = []
    unresolved = False
    for members in groups.values():
        signatures = {(r.modality, r.value) for r in members}
        if len(signatures) <= 1:
            kept.extend(members)
            continue
        component, topic = members[0].component, members[0].topic
        ordered = sorted(members, key=lambda r: r.authority_rank, reverse=True)
        highest_rank = ordered[0].authority_rank
        top = [r for r in ordered if r.authority_rank == highest_rank]
        winner: RuleRecord | None = None
        reason: str | None = None
        if len(top) == 1:
            winner = top[0]
            reason = f"{winner.authority} ({winner.authority_rank}) outranks the other source(s)"
        elif len({(r.modality, r.value) for r in top}) == 1:
            winner = top[0]
            reason = f"top-ranked rules agree; lower-ranked source(s) are overridden by {winner.authority} ({highest_rank})"
        elif (
            len({r.source_kind for r in top}) == 1
            and all(r.effective_date is not None for r in top)
            and len({r.effective_date for r in top}) == len(top)
        ):
            winner = max(top, key=lambda r: r.effective_date)  # type: ignore[arg-type]
            reason = f"newer same-kind source dated {winner.effective_date} takes precedence"

        if winner is None:
            unresolved = True
            kept.extend(members)
            conflicts.append(ConflictGroup(component, topic, members, False, "equal-rank disagreement has no eligible recency tie-break"))
            continue

        kept.append(winner)
        for loser in members:
            if loser.rule_id != winner.rule_id:
                overridden.append(OverriddenRule(rule_id=loser.rule_id, reason=reason or "overridden by deterministic authority resolution"))
        conflicts.append(ConflictGroup(component, topic, members, True, reason))

    return kept, overridden, conflicts, unresolved


def govern_query(store: Store, config: LoreConfig, query: str) -> GovernanceOutcome:
    """Retrieve candidates, apply deterministic governance, and persist the decision."""
    decision_type = classify_decision_type(query, config)
    rules = retrieve_rules(store, query)
    winning_rules, overridden, conflicts, has_unresolved = resolve_conflicts(rules)

    requirements = config.decision_types[decision_type].required_evidence
    evidence = store.list_evidence(decision_type=decision_type)
    evidence_by_type: dict[str, list[EvidenceStatus]] = {}
    for item in evidence:
        evidence_by_type.setdefault(item.evidence_type.casefold(), []).append(item.status)
    rule_evidence = {r.evidence_type.casefold() for r in rules}
    approved_policy_rank = config.authority_ladder.get("approved_policy", float("inf"))
    missing_evidence: list[str] = []
    for required in requirements:
        statuses = evidence_by_type.get(required.casefold(), [])
        # A rule can state that evidence is required; it is not itself proof that
        # the assessment or document exists. Only attached evidence records satisfy it.
        if EvidenceStatus.SATISFIED in statuses or (
            required.casefold() == "policy_condition"
            and (
                required.casefold() in rule_evidence
                or any(rule.authority_rank >= approved_policy_rank for rule in rules)
            )
        ):
            continue
        if EvidenceStatus.PENDING in statuses:
            missing_evidence.append(f"{required} (pending)")
        else:
            missing_evidence.append(required)

    if has_unresolved:
        state = ResultState.CONFLICTING
    elif missing_evidence:
        state = ResultState.INSUFFICIENT
    elif overridden:
        state = ResultState.QUALIFIED
    elif winning_rules:
        state = ResultState.SUPPORTED
    else:
        state = ResultState.NO_KNOWLEDGE

    directive = {
        ResultState.CONFLICTING: Directive.ASK_USER,
        ResultState.INSUFFICIENT: Directive.ASK_USER,
        ResultState.QUALIFIED: Directive.PROCEED_AND_CITE,
        ResultState.SUPPORTED: Directive.PROCEED_AND_CITE,
        ResultState.NO_KNOWLEDGE: Directive.PROCEED,
    }[state]
    decision_id = uuid4().hex
    envelope = ResultEnvelope(
        state=state,
        directive=directive,
        items=[
            ResultItem(
                rule_id=rule.rule_id,
                statement=rule.statement,
                source=rule.source_path,
                authority=rule.authority,
                source_quote=rule.source_quote,
                provenance=rule.provenance,
            )
            for rule in winning_rules
        ],
        overridden=overridden,
        missing_evidence=missing_evidence,
        notes=[
            f"Unresolved conflict for {group.component}/{group.topic}: {group.reason}"
            for group in conflicts if not group.resolved
        ],
        decision_id=decision_id,
    )
    store.save_decision(
        DecisionRecord(
            id=decision_id,
            query=query,
            state=state,
            rule_ids=[r.rule_id for r in winning_rules],
            created_at=datetime.now(timezone.utc),
        )
    )
    return GovernanceOutcome(envelope, decision_type, rules, conflicts)
