"""Source metadata parsing and code-owned rule provenance construction."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from lore_lite.schema import LoreConfig, Rule, RuleRecord, RuleStatus, SourceKind, SourceRecord


def source_from_markdown(
    path: str | Path,
    content: str,
    config: LoreConfig,
    *,
    authority: str | None = None,
    owner: str | None = None,
) -> SourceRecord:
    """Create source metadata using explicit upload values or Markdown frontmatter."""
    frontmatter = _frontmatter(content)
    selected_authority = authority or frontmatter.get("authority")
    if not isinstance(selected_authority, str) or selected_authority not in config.authority_ladder:
        raise ValueError(
            "Source authority must be provided by upload metadata or Markdown frontmatter "
            f"and match a configured authority: {', '.join(config.authority_ladder)}"
        )
    selected_owner = owner if owner is not None else frontmatter.get("owner")
    if selected_owner is not None and not isinstance(selected_owner, str):
        raise ValueError("Source owner metadata must be a string")
    effective_date = frontmatter.get("effective_date")
    if effective_date is not None:
        try:
            effective_date = date.fromisoformat(str(effective_date))
        except ValueError as exc:
            raise ValueError("effective_date frontmatter must use YYYY-MM-DD") from exc
    path_text = Path(path).as_posix()
    return SourceRecord(
        id=uuid4().hex,
        path=path_text,
        kind=SourceKind.MARKDOWN,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        authority=selected_authority,
        owner=selected_owner,
        imported_at=datetime.now(timezone.utc),
        effective_date=effective_date,
    )


def rule_records(
    rules: list[Rule], source: SourceRecord, config: LoreConfig,
    *, provenance: str = "source_text",
) -> list[RuleRecord]:
    """Attach trusted source metadata to extracted rules; model output cannot set authority."""
    rank = config.authority_ladder.get(source.authority)
    if rank is None:
        raise ValueError(f"Unknown source authority: {source.authority}")
    return [
        RuleRecord(
            **rule.model_dump(mode="python"),
            rule_id=uuid4().hex,
            source_id=source.id,
            source_path=source.path,
            source_location=provenance if provenance in {"image-transcript", "image-ocr"} else None,
            authority=source.authority,
            authority_rank=rank,
            source_kind=source.kind,
            effective_date=source.effective_date,
            provenance=provenance,
            status=RuleStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        for rule in rules
    ]


def source_from_image(
    path: str | Path,
    image_bytes: bytes,
    config: LoreConfig,
    *,
    authority: str,
    owner: str | None = None,
) -> SourceRecord:
    """Create image metadata using trusted upload fields; images have no frontmatter."""
    if authority not in config.authority_ladder:
        raise ValueError(
            "Image authority must match a configured authority: "
            + ", ".join(config.authority_ladder)
        )
    return SourceRecord(
        id=uuid4().hex,
        path=Path(path).as_posix(),
        kind=SourceKind.IMAGE,
        content_hash=hashlib.sha256(image_bytes).hexdigest(),
        authority=authority,
        owner=owner,
        imported_at=datetime.now(timezone.utc),
    )


def _frontmatter(content: str) -> dict[str, object]:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", content, re.DOTALL)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Markdown frontmatter must be a YAML mapping")
    return data
