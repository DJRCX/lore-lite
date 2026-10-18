"""Keyword retrieval and provenance-safe rule filters."""

from __future__ import annotations

import re
import sqlite3
import json

from lore_lite.schema import RuleRecord
from lore_lite.store import Store

_STOP_WORDS = {
    "a", "an", "and", "are", "can", "do", "for", "how", "i", "in", "is",
    "it", "of", "on", "or", "the", "to", "we", "what", "when", "where",
    "which", "who", "why", "with", "use", "using",
}


def _tokens(query: str) -> list[str]:
    return list(dict.fromkeys(
        token for token in re.findall(r"[\w-]+", query.casefold())
        if token not in _STOP_WORDS
    ))


def retrieve_rules(
    store: Store,
    query: str,
    *,
    component: str | None = None,
    topic: str | None = None,
    evidence_types: set[str] | None = None,
    limit: int = 100,
) -> list[RuleRecord]:
    """Search rule text, then apply exact component/topic/evidence filters."""
    tokens = _tokens(query)
    rows: list[dict[str, object]]
    if tokens:
        with store.connect() as db:
            rows = _search(db, tokens, store.fts_available, limit)
        rules = [RuleRecord.model_validate_json(json.dumps(row)) for row in rows]
    else:
        rules = store.list_rules()
    if component:
        rules = [r for r in rules if r.component.casefold() == component.casefold()]
    if topic:
        rules = [r for r in rules if r.topic.casefold() == topic.casefold()]
    if evidence_types is not None:
        wanted = {value.casefold() for value in evidence_types}
        rules = [r for r in rules if r.evidence_type.casefold() in wanted]
    return rules[:limit]


def _search(
    db: sqlite3.Connection, tokens: list[str], fts_available: bool, limit: int
) -> list[dict[str, object]]:
    if fts_available:
        expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        try:
            rows = db.execute(
                "SELECT r.* FROM rules_fts f JOIN rules r ON r.rule_id=f.rule_id "
                "WHERE rules_fts MATCH ? LIMIT ?", (expression, limit)
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            pass
    clauses = []
    params: list[object] = []
    for token in tokens:
        like = f"%{token}%"
        clauses.append("(statement LIKE ? COLLATE NOCASE OR component LIKE ? COLLATE NOCASE "
                       "OR topic LIKE ? COLLATE NOCASE OR source_quote LIKE ? COLLATE NOCASE "
                       "OR evidence_type LIKE ? COLLATE NOCASE)")
        params.extend([like] * 5)
    rows = db.execute(
        f"SELECT * FROM rules WHERE {' OR '.join(clauses)} ORDER BY authority_rank DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]
