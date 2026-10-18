"""Command-line interface for importing and querying LORE Lite rules."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from lore_lite.config import load_config
from lore_lite.gemma import GemmaClient, GemmaConfigurationError
from lore_lite.governance import govern_query, resolve_conflicts
from lore_lite.ingest import rule_records, source_from_image, source_from_markdown
from lore_lite.schema import SourceKind
from lore_lite.store import Store

app = typer.Typer(help="Extract and query cited project rules.", no_args_is_help=True)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.command()
def ingest(
    source_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    authority: str | None = typer.Option(None, "--authority", help="Trusted source rank; overrides frontmatter."),
    owner: str | None = typer.Option(None, "--owner", help="Source owner metadata."),
    db_path: Path = typer.Option(Path("lore.db"), "--db", help="SQLite database path."),
    config_path: Path = typer.Option(Path("lore.config.yaml"), "--config", help="Governance YAML path."),
) -> None:
    """Extract and store rules from a Markdown file."""
    config = load_config(config_path)
    suffix = source_path.suffix.casefold()
    image_types = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    markdown_types = {".md", ".markdown", ".mdown"}
    if suffix in image_types:
        if authority is None:
            raise typer.BadParameter("Image sources require --authority metadata", param_hint="--authority")
        image_bytes = source_path.read_bytes()
        try:
            source = source_from_image(source_path, image_bytes, config, authority=authority, owner=owner)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--authority") from exc
        content = None
    elif suffix in markdown_types:
        content = source_path.read_text(encoding="utf-8")
        try:
            source = source_from_markdown(
                source_path, content, config, authority=authority, owner=owner
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--authority") from exc
        image_bytes = None
    else:
        raise typer.BadParameter("Supported sources: Markdown, PNG, JPEG, WEBP, and GIF", param_hint="source_path")
    store = Store(db_path)
    if store.has_source(source.path, source.content_hash):
        _emit({"status": "already_ingested", "source": source.path, "rules_added": 0})
        return
    try:
        extractor = GemmaClient()
    except GemmaConfigurationError as exc:
        raise typer.BadParameter(str(exc), param_hint="GEMINI_API_KEY") from exc
    try:
        batch = (
            extractor.extract_image(source_path)
            if source.kind == SourceKind.IMAGE
            else extractor.extract_text(content or "", source_path=source.path)
        )
    except Exception as exc:
        # The Google SDK may surface a network timeout as an httpx exception.
        # Keep this common transient failure actionable instead of dumping its traceback.
        exception_name = type(exc).__name__.casefold()
        if "timeout" in exception_name or "timed out" in str(exc).casefold():
            timeout_ms = int(os.environ.get("GEMMA_API_TIMEOUT_MS", "90000"))
            timeout_seconds = timeout_ms / 1000
            raise typer.BadParameter(
                f"Gemini did not respond within {timeout_seconds:g} seconds. "
                "This source was not stored. Retry later or check the network and Gemini API availability."
            ) from exc
        if isinstance(exc, RuntimeError) and str(exc).startswith((
            "Gemini timed out transcribing this image,",
            "Local OCR",
        )):
            raise typer.BadParameter(str(exc)) from exc
        raise
    records = rule_records(batch.rules, source, config, provenance=batch.provenance)
    inserted = store.add_source(source, records)
    _emit({
        "status": "ingested" if inserted else "already_ingested",
        "source": source.path,
        "authority": source.authority,
        "kind": source.kind.value,
        "rules_added": len(records) if inserted else 0,
        "cache_status": batch.cache_status,
        "provenance": batch.provenance,
        "notice": (
            "Gemini image transcription timed out; local OCR was used. Review diagram relationships carefully."
            if batch.provenance == "image-ocr" else None
        ),
        "rejected_rules": [
            {
                "statement": item.rule.statement,
                "source_quote": item.rule.source_quote,
                "section": item.section,
                "reason": item.reason,
            }
            for item in batch.rejected_rules
        ],
        "quarantined_sections": [
            {"section": item.section, "reason": item.reason}
            for item in batch.quarantined_sections
        ],
    })


@app.command()
def ask(
    query: str = typer.Argument(..., help="Question to evaluate against imported rules."),
    db_path: Path = typer.Option(Path("lore.db"), "--db", help="SQLite database path."),
    config_path: Path = typer.Option(Path("lore.config.yaml"), "--config", help="Governance YAML path."),
) -> None:
    """Return the deterministic decision envelope as JSON."""
    outcome = govern_query(Store(db_path), load_config(config_path), query)
    _emit(outcome.envelope.model_dump(mode="json", by_alias=True))


@app.command("rules")
def rules_command(
    component: str | None = typer.Option(None, "--component", help="Filter by component."),
    db_path: Path = typer.Option(Path("lore.db"), "--db", help="SQLite database path."),
) -> None:
    """List stored rules, optionally filtered by component."""
    rules = Store(db_path).list_rules(component=component)
    _emit([rule.model_dump(mode="json") for rule in rules])


@app.command()
def conflicts(
    db_path: Path = typer.Option(Path("lore.db"), "--db", help="SQLite database path."),
) -> None:
    """List detected disagreements and their deterministic resolution status."""
    _, _, groups, _ = resolve_conflicts(Store(db_path).list_rules())
    _emit([
        {
            "component": group.component,
            "topic": group.topic,
            "resolved": group.resolved,
            "reason": group.reason,
            "rules": [
                {"rule_id": rule.rule_id, "authority": rule.authority,
                 "authority_rank": rule.authority_rank, "statement": rule.statement}
                for rule in group.rules
            ],
        }
        for group in groups
    ])


if __name__ == "__main__":
    app()
