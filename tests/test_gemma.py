import json
from types import SimpleNamespace

from lore_lite.gemma import GemmaClient, _load_local_env


def _rule(quote: str) -> dict[str, object]:
    return {
        "statement": "Use parameterized queries.",
        "component": "database",
        "topic": "sql_queries",
        "modality": "MUST",
        "value": "parameterized",
        "severity": "high",
        "evidence_type": "policy_condition",
        "source_quote": quote,
        "confidence": 0.95,
    }


class _FakeModels:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.responses.pop(0))


def test_invalid_structured_output_retries_once_then_verifies_quote(tmp_path):
    models = _FakeModels(["{invalid", json.dumps({"rules": [_rule("Use parameterized queries.")]})])
    client = GemmaClient(client=SimpleNamespace(models=models), cache_dir=tmp_path / "cache")

    batch = client.extract_text("Use parameterized queries.")

    assert len(models.calls) == 2
    assert "previous response had this problem" in models.calls[1]["contents"]
    assert len(batch.rules) == 1
    assert not batch.quarantined_sections


def test_invalid_output_after_retry_is_quarantined(tmp_path):
    models = _FakeModels(["bad", "still bad"])
    client = GemmaClient(client=SimpleNamespace(models=models), cache_dir=tmp_path / "cache")

    batch = client.extract_text("# Policy\nSome source text")

    assert len(models.calls) == 2
    assert len(batch.quarantined_sections) == 1
    assert batch.quarantined_sections[0].section == "Policy"


def test_invented_quote_gets_one_correction_retry_then_success_is_cached(tmp_path):
    models = _FakeModels([
        json.dumps({"rules": [_rule("Invented source quote.")]}),
        json.dumps({"rules": [_rule("use parameterized queries")]})
    ])
    client = GemmaClient(client=SimpleNamespace(models=models), cache_dir=tmp_path / "cache")

    first = client.extract_text("The source says use parameterized queries.")
    second = client.extract_text("The source says use parameterized queries.")

    assert len(first.rules) == 1
    assert not first.rejected_rules
    assert first.rules[0].source_quote == "use parameterized queries"
    assert first.cache_status == "fresh"
    assert second.cache_status == "cached"
    assert len(models.calls) == 2


def test_invented_quote_stays_rejected_after_correction_retry(tmp_path):
    models = _FakeModels([
        json.dumps({"rules": [_rule("Invented source quote.")]}),
        json.dumps({"rules": [_rule("Still invented.")]})
    ])
    client = GemmaClient(client=SimpleNamespace(models=models), cache_dir=tmp_path / "cache")

    batch = client.extract_text("The source says use parameterized queries.")

    assert not batch.rules
    assert len(batch.rejected_rules) == 1
    assert batch.cache_status == "fresh"
    assert len(models.calls) == 2
    assert "source_quote must be copied character-for-character" in models.calls[1]["contents"]


def test_local_env_loads_key_without_overriding_shell_value(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('GEMINI_API_KEY="local-secret"\nGEMMA_MODEL=local-model\n', encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMMA_MODEL", "shell-model")

    _load_local_env(env_file)

    assert __import__("os").environ["GEMINI_API_KEY"] == "local-secret"
    assert __import__("os").environ["GEMMA_MODEL"] == "shell-model"
