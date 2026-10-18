import json
from types import SimpleNamespace

from lore_lite.gemma import GemmaClient
from lore_lite.ingest import rule_records, source_from_image
from lore_lite.schema import DecisionTypeConfig, LoreConfig
from lore_lite.store import Store


def _rule(quote: str) -> dict[str, object]:
    return {
        "statement": "Reporting queries use parameterized statements.",
        "component": "database",
        "topic": "sql_queries",
        "modality": "MUST",
        "value": "parameterized",
        "severity": "high",
        "evidence_type": "policy_condition",
        "source_quote": quote,
        "confidence": 0.9,
    }


class _FakeModels:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.responses.pop(0))


def test_image_transcription_then_extraction_verifies_transcript_quote(tmp_path):
    transcript = "Application -> Database gateway. Reporting queries MUST use parameterized statements."
    models = _FakeModels([transcript, json.dumps({"rules": [_rule("Reporting queries MUST use parameterized statements.")]})])
    image = tmp_path / "diagram.png"
    image.write_bytes(b"fake image bytes for mocked client")
    client = GemmaClient(client=SimpleNamespace(models=models), cache_dir=tmp_path / "cache")

    batch = client.extract_image(image)

    assert len(models.calls) == 2
    assert batch.transcript == transcript
    assert batch.provenance == "image-transcript"
    assert len(batch.rules) == 1
    assert not batch.rejected_rules
    assert models.calls[0]["contents"][1].inline_data.mime_type == "image/png"


def test_image_rule_persistence_labels_image_transcript_provenance(tmp_path):
    config = LoreConfig(
        authority_ladder={"approved_policy": 4},
        decision_types={"code_change": DecisionTypeConfig()},
    )
    image_bytes = b"fake image bytes"
    source = source_from_image(
        "architecture.png", image_bytes, config, authority="approved_policy"
    )
    from lore_lite.schema import Rule

    rule = Rule.model_validate_json(
        json.dumps(_rule("Reporting queries MUST use parameterized statements."))
    )
    records = rule_records([rule], source, config, provenance="image-transcript")
    store = Store(tmp_path / "lore.db")
    assert store.add_source(source, records)

    saved = store.list_rules()[0]
    assert saved.source_kind.value == "image"
    assert saved.provenance == "image-transcript"
    assert saved.source_location == "image-transcript"
