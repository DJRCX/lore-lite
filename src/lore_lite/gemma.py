"""Gemma text extraction with strict validation, quote checks, and disk caching."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from lore_lite.schema import Rule, RuleExtractionResponse
from lore_lite.verify import verify_quote


def _load_local_env(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overriding exported shell variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, value = stripped.partition("=")
        if not separator or not name.strip():
            continue
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


_load_local_env()
MODEL_ID = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")
PROMPT_VERSION = "text-rules-v2"
RULE_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "component": {"type": "string"},
                    "topic": {"type": "string"},
                    "modality": {"type": "string", "enum": ["MUST", "SHOULD", "MAY", "MUST_NOT"]},
                    "value": {"type": ["string", "null"]},
                    "severity": {"type": "string"},
                    "evidence_type": {"type": "string"},
                    "source_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "statement", "component", "topic", "modality", "value",
                    "severity", "evidence_type", "source_quote", "confidence",
                ],
            },
        },
    },
    "required": ["rules"],
}


class GemmaConfigurationError(RuntimeError):
    """Raised when the Gemini API key is not configured."""


@dataclass
class RejectedRule:
    rule: Rule
    reason: str
    section: str


@dataclass
class QuarantinedSection:
    section: str
    text: str
    reason: str


@dataclass
class ExtractionBatch:
    rules: list[Rule] = field(default_factory=list)
    rejected_rules: list[RejectedRule] = field(default_factory=list)
    quarantined_sections: list[QuarantinedSection] = field(default_factory=list)
    cache_hits: int = 0
    model_calls: int = 0
    transcript: str | None = None
    provenance: str = "source_text"

    @property
    def cached(self) -> bool:
        """True only when model results were used and every one came from cache."""
        return self.cache_hits > 0 and self.model_calls == 0

    @property
    def cache_status(self) -> str:
        if self.cached:
            return "cached"
        if self.cache_hits:
            return "mixed"
        return "fresh"


def _sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown by headings outside fenced code so failures are isolated."""
    found: list[tuple[str, str]] = []
    heading = "Document"
    buffer: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        fence_match = re.match(r"^\s*(```+|~~~+)", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if fence is None else None
        if match:
            body = "\n".join(buffer).strip()
            if body:
                found.append((heading, body))
            heading = match.group(2).strip()
            buffer = [line]
        else:
            buffer.append(line)
    body = "\n".join(buffer).strip()
    if body:
        found.append((heading, body))
    return found or [("Document", text)]


def _prompt(section: str, retry_error: str | None = None) -> str:
    retry = (
        f"\nYour previous response had this problem: {retry_error}\n"
        "Correct the response and return it again."
        if retry_error else ""
    )
    return (
        "Extract only explicit, actionable project rules from the source section. "
        "Return JSON matching the supplied schema with a rules array. Do not infer policy. "
        "Copy source_quote exactly from the section. If no rule is present, return an empty array. "
        "Keep component and topic labels stable across documents: when the section heading is a "
        "short subject label, reuse its wording as the topic, and use a consistent system name "
        "such as database, authentication, vendor, or session management as the component. "
        "Confidence must reflect the explicitness of the rule.\n"
        f"SOURCE SECTION:\n{section}{retry}"
    )


class GemmaClient:
    """Small isolated client for Gemma's structured text extraction."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = MODEL_ID,
        cache_dir: str | Path = ".cache/gemma",
        client: Any | None = None,
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if client is None and not key:
            raise GemmaConfigurationError(
                "Set GEMINI_API_KEY in the environment before using Gemma extraction."
            )
        timeout_ms = int(os.environ.get("GEMMA_API_TIMEOUT_MS", "90000"))
        self.client = client or genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self.model = model
        self.cache_dir = Path(cache_dir)

    def extract_text(self, text: str, *, source_path: str = "<memory>") -> ExtractionBatch:
        """Extract rules section by section, isolating invalid sections after one retry."""
        batch = ExtractionBatch()
        for label, section in _sections(text):
            try:
                rules, was_cached, calls = self._extract_section(section)
            except (ValidationError, ValueError) as exc:
                batch.quarantined_sections.append(
                    QuarantinedSection(label, section, f"Invalid structured output after one retry: {exc}")
                )
                continue

            invalid_quotes = [rule for rule in rules if not verify_quote(rule.source_quote, text)]
            if invalid_quotes and not was_cached:
                # A syntactically valid model response can still invent or alter a
                # quote. Give it one targeted correction attempt, then rely on the
                # verifier as the final authority.
                self._section_cache_file(section).unlink(missing_ok=True)
                quote_problem = (
                    "The source_quote must be copied character-for-character from the source. "
                    "The quote you returned was not found. Do not duplicate, add, or paraphrase words."
                )
                try:
                    rules, _, retry_calls = self._extract_section(
                        section, skip_cache=True, retry_error=quote_problem
                    )
                    calls += retry_calls
                except (ValidationError, ValueError) as exc:
                    batch.quarantined_sections.append(
                        QuarantinedSection(
                            label, section,
                            f"Invalid structured output after quote-correction retry: {exc}",
                        )
                    )
                    batch.model_calls += calls
                    continue

                if any(not verify_quote(rule.source_quote, text) for rule in rules):
                    # A failed quote correction should not turn into a cached empty
                    # result; a later import may succeed after the model recovers.
                    self._section_cache_file(section).unlink(missing_ok=True)

            batch.cache_hits += int(was_cached)
            batch.model_calls += calls
            for rule in rules:
                if verify_quote(rule.source_quote, text):
                    batch.rules.append(rule)
                else:
                    batch.rejected_rules.append(
                        RejectedRule(rule, "source_quote does not occur in source text", label)
                    )
        return batch

    def extract_image(self, image_path: str | Path) -> ExtractionBatch:
        """Transcribe image text/relationships, then extract and verify against transcript."""
        path = Path(image_path)
        image_bytes = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0]
        if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            raise ValueError(f"Unsupported image type for extraction: {path.suffix or 'unknown'}")
        transcript, cached_transcript, provenance = self._transcribe_image(image_bytes, mime_type)
        batch = self.extract_text(transcript, source_path=path.as_posix())
        batch.transcript = transcript
        batch.provenance = provenance
        batch.cache_hits += int(cached_transcript)
        batch.model_calls += int(not cached_transcript and provenance == "image-transcript")
        return batch

    def _transcribe_image(self, image_bytes: bytes, mime_type: str) -> tuple[str, bool, str]:
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        cache_key = hashlib.sha256(
            f"{self.model}\0image-transcription-v1\0{image_hash}".encode("utf-8")
        ).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.is_file():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                transcript = payload.get("transcript")
                if isinstance(transcript, str) and transcript.strip():
                    provenance = payload.get("provenance", "image-transcript")
                    if provenance not in {"image-transcript", "image-ocr"}:
                        provenance = "image-transcript"
                    return transcript, True, provenance
            except (OSError, json.JSONDecodeError):
                pass
            cache_file.unlink(missing_ok=True)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    "Transcribe all legible text exactly. Describe boxes, arrows, and relationships "
                    "as concise labeled statements, and preserve the sequence and direction shown. "
                    "Do not infer rules that are not visible. Return the transcription and diagram "
                    "relationships as plain text.",
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(temperature=0.2),
            )
            transcript = response.text
            provenance = "image-transcript"
        except Exception as exc:
            name = type(exc).__name__.casefold()
            if "timeout" not in name and "timed out" not in str(exc).casefold():
                raise
            transcript = self._local_ocr(image_bytes)
            provenance = "image-ocr"
        if not transcript or not transcript.strip():
            raise ValueError("Image transcription returned no readable text")
        self._write_cache(cache_file, {"transcript": transcript, "provenance": provenance})
        return transcript, False, provenance

    @staticmethod
    def _local_ocr(image_bytes: bytes) -> str:
        """Use installed Tesseract as a network-free fallback for image text."""
        executable = shutil.which("tesseract")
        if executable is None:
            raise RuntimeError(
                "Gemini timed out transcribing this image, and local fallback is unavailable. "
                "Install Tesseract OCR and retry, or retry when Gemini is responding."
            )
        try:
            result = subprocess.run(
                [executable, "stdin", "stdout"], input=image_bytes,
                capture_output=True, timeout=45, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Local OCR also timed out while reading the image.") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Local OCR could not read the image: {detail or 'unknown error'}")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def _section_cache_file(self, section: str) -> Path:
        cache_key = hashlib.sha256(
            f"{self.model}\0{PROMPT_VERSION}\0{section}".encode("utf-8")
        ).hexdigest()
        return self.cache_dir / f"{cache_key}.json"

    def _extract_section(
        self,
        section: str,
        *,
        skip_cache: bool = False,
        retry_error: str | None = None,
    ) -> tuple[list[Rule], bool, int]:
        cache_file = self._section_cache_file(section)
        if not skip_cache and cache_file.is_file():
            try:
                cached_json = cache_file.read_text(encoding="utf-8")
                cached_rules = RuleExtractionResponse.model_validate_json(cached_json).rules
                if all(verify_quote(rule.source_quote, section) for rule in cached_rules):
                    return cached_rules, True, 0
                # Do not let a schema-valid but quote-invalid response poison future
                # imports. Discard it and ask Gemma for a fresh extraction.
                cache_file.unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError, ValidationError):
                cache_file.unlink(missing_ok=True)

        validation_error = retry_error
        for attempt in range(2):
            response = self.client.models.generate_content(
                model=self.model,
                contents=_prompt(section, validation_error),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=RULE_EXTRACTION_JSON_SCHEMA,
                    temperature=0.2,
                ),
            )
            try:
                if not response.text:
                    raise ValueError("Gemma returned an empty response")
                parsed = RuleExtractionResponse.model_validate_json(response.text)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                validation_error = str(exc)
                if attempt == 1:
                    raise ValueError(validation_error) from exc
                continue
            verified_for_cache = [
                rule for rule in parsed.rules if verify_quote(rule.source_quote, section)
            ]
            cache_payload = RuleExtractionResponse(rules=verified_for_cache).model_dump(mode="json")
            self._write_cache(cache_file, cache_payload)
            return parsed.rules, False, attempt + 1
        raise AssertionError("unreachable")

    def _write_cache(self, destination: Path, payload: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.cache_dir, delete=False
            ) as handle:
                temp_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, destination)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
