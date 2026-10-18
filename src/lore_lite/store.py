"""SQLite persistence for sources, extracted rules, evidence, and decisions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from lore_lite.schema import DecisionRecord, EvidenceItem, RuleRecord, SourceRecord


class Store:
    """Small SQLite repository with optional FTS5-backed rule search."""

    def __init__(self, path: str | Path = "lore.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = False
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    owner TEXT,
                    imported_at TEXT NOT NULL,
                    effective_date TEXT,
                    UNIQUE(path, content_hash)
                );
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    statement TEXT NOT NULL,
                    component TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    value TEXT,
                    severity TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_quote TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_path TEXT NOT NULL,
                    source_location TEXT,
                    authority TEXT NOT NULL,
                    authority_rank INTEGER NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'markdown',
                    effective_date TEXT,
                    provenance TEXT NOT NULL DEFAULT 'source_text',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rules_component_topic ON rules(component, topic);
                CREATE INDEX IF NOT EXISTS idx_rules_source ON rules(source_id);
                CREATE TABLE IF NOT EXISTS evidence_items (
                    id TEXT PRIMARY KEY,
                    decision_type TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_decision_type ON evidence_items(decision_type);
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    state TEXT NOT NULL,
                    rule_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5("
                    "rule_id UNINDEXED, statement, component, topic, source_quote, evidence_type)"
                )
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False
            columns = {row["name"] for row in db.execute("PRAGMA table_info(rules)")}
            if "source_kind" not in columns:
                db.execute("ALTER TABLE rules ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'markdown'")
            if "effective_date" not in columns:
                db.execute("ALTER TABLE rules ADD COLUMN effective_date TEXT")
            if "provenance" not in columns:
                db.execute("ALTER TABLE rules ADD COLUMN provenance TEXT NOT NULL DEFAULT 'source_text'")

    def add_source(self, source: SourceRecord, rules: Iterable[RuleRecord] = ()) -> bool:
        """Insert a source and its rules once; return False for repeated content."""
        rule_list = list(rules)
        for rule in rule_list:
            if rule.source_id != source.id:
                raise ValueError(f"Rule {rule.rule_id} does not belong to source {source.id}")
            if rule.source_path != source.path or rule.authority != source.authority:
                raise ValueError("Rule provenance must match the code-owned source metadata")
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM sources WHERE path = ? AND content_hash = ?",
                (source.path, source.content_hash),
            ).fetchone()
            if existing:
                return False
            db.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source.id, source.path, source.kind.value, source.content_hash,
                 source.authority, source.owner, source.imported_at.isoformat(),
                 source.effective_date.isoformat() if source.effective_date else None),
            )
            for rule in rule_list:
                db.execute(
                    "INSERT INTO rules (rule_id, source_id, statement, component, topic, modality, value, "
                    "severity, evidence_type, source_quote, confidence, source_path, source_location, "
                    "authority, authority_rank, source_kind, effective_date, provenance, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rule.rule_id, rule.source_id, rule.statement, rule.component, rule.topic,
                     rule.modality.value, rule.value, rule.severity, rule.evidence_type,
                     rule.source_quote, rule.confidence, rule.source_path, rule.source_location,
                     rule.authority, rule.authority_rank, rule.source_kind.value,
                     rule.effective_date.isoformat() if rule.effective_date else None,
                     rule.provenance, rule.status.value,
                     rule.created_at.isoformat()),
                )
                if self.fts_available:
                    db.execute(
                        "INSERT INTO rules_fts VALUES (?, ?, ?, ?, ?, ?)",
                        (rule.rule_id, rule.statement, rule.component, rule.topic,
                         rule.source_quote, rule.evidence_type),
                    )
        return True

    def has_source(self, path: str, content_hash: str) -> bool:
        """Check for an already imported path/content pair before costly extraction."""
        with self.connect() as db:
            return db.execute(
                "SELECT 1 FROM sources WHERE path = ? AND content_hash = ?",
                (path, content_hash),
            ).fetchone() is not None

    def reset_workspace(self) -> dict[str, int]:
        """Remove all imported and review data from this database, preserving its schema."""
        with self.connect() as db:
            counts = {
                "sources": db.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "rules": db.execute("SELECT COUNT(*) FROM rules").fetchone()[0],
                "evidence": db.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0],
                "decisions": db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
            }
            db.execute("DELETE FROM evidence_items")
            db.execute("DELETE FROM decisions")
            if self.fts_available:
                db.execute("DELETE FROM rules_fts")
            db.execute("DELETE FROM sources")
        return counts

    def list_sources(self) -> list[SourceRecord]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM sources ORDER BY imported_at, path").fetchall()
        return [SourceRecord.model_validate_json(json.dumps(dict(row))) for row in rows]

    def list_rules(self, *, component: str | None = None) -> list[RuleRecord]:
        sql = "SELECT * FROM rules"
        params: tuple[str, ...] = ()
        if component:
            sql += " WHERE component = ? COLLATE NOCASE"
            params = (component,)
        sql += " ORDER BY source_path, source_location, rule_id"
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [RuleRecord.model_validate_json(json.dumps(dict(row))) for row in rows]

    def add_evidence(self, evidence: EvidenceItem) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO evidence_items VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET decision_type=excluded.decision_type, "
                "evidence_type=excluded.evidence_type, status=excluded.status, source_id=excluded.source_id",
                (evidence.id, evidence.decision_type, evidence.evidence_type,
                 evidence.status.value, evidence.source_id),
            )

    def list_evidence(self, *, decision_type: str | None = None) -> list[EvidenceItem]:
        sql = "SELECT * FROM evidence_items"
        params: tuple[str, ...] = ()
        if decision_type:
            sql += " WHERE decision_type = ? COLLATE NOCASE"
            params = (decision_type,)
        sql += " ORDER BY decision_type, evidence_type, id"
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [EvidenceItem.model_validate_json(json.dumps(dict(row))) for row in rows]

    def save_decision(self, decision: DecisionRecord) -> None:
        payload = decision.model_dump(mode="json")
        with self.connect() as db:
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET query=excluded.query, state=excluded.state, "
                "rule_ids=excluded.rule_ids, created_at=excluded.created_at",
                (decision.id, decision.query, decision.state.value,
                 json.dumps(payload["rule_ids"]), decision.created_at.isoformat()),
            )

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if row is None:
            return None
        values = dict(row)
        values["rule_ids"] = json.loads(values["rule_ids"])
        return DecisionRecord.model_validate_json(json.dumps(values))
