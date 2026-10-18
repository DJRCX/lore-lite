import json

from typer.testing import CliRunner

from lore_lite import cli
from lore_lite.gemma import ExtractionBatch
from lore_lite.schema import Modality, Rule


runner = CliRunner()


class _FakeGemma:
    def __init__(self, **kwargs):
        pass

    def extract_text(self, content: str, *, source_path: str):
        if "informal_note" in content:
            return ExtractionBatch(rules=[Rule(
                statement="CloudBox is approved.",
                component="vendor",
                topic="vendor_approval",
                modality=Modality.MAY,
                value="approved",
                severity="medium",
                evidence_type="informal_note",
                source_quote="CloudBox is approved.",
                confidence=0.9,
            )])
        if source_path.endswith("vendor-policy.md"):
            return ExtractionBatch(rules=[Rule(
                statement="Vendors need an assessment before sensitive customer data processing.",
                component="vendor",
                topic="vendor_approval",
                modality=Modality.MUST,
                value="assessment_required",
                severity="high",
                evidence_type="policy_condition",
                source_quote="Vendors need an assessment before sensitive customer data processing.",
                confidence=0.9,
            )])
        quote = "Parameterized queries are required for reports." if "approved_policy" in content else "Raw SQL strings are fine for reporting."
        return ExtractionBatch(rules=[Rule(
            statement="Use parameterized queries." if "approved_policy" in content else "Raw SQL is fine for reporting.",
            component="database",
            topic="sql_queries",
            modality=Modality.MUST if "approved_policy" in content else Modality.MAY,
            value="parameterized" if "approved_policy" in content else "raw_sql",
            severity="high",
            evidence_type="policy_condition",
            source_quote=quote,
            confidence=0.9,
        )])


def test_cli_mocked_end_to_end_ingest_ask_rules_and_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "GemmaClient", _FakeGemma)
    database = tmp_path / "lore.db"
    policy = tmp_path / "security.md"
    wiki = tmp_path / "wiki.md"
    vendor_policy = tmp_path / "vendor-policy.md"
    vendor_note = tmp_path / "vendor-note.md"
    policy.write_text("---\nauthority: approved_policy\n---\nParameterized queries are required for reports.", encoding="utf-8")
    wiki.write_text("---\nauthority: wiki_entry\n---\nRaw SQL strings are fine for reporting.", encoding="utf-8")
    vendor_policy.write_text("---\nauthority: approved_policy\n---\nVendors need an assessment before sensitive customer data processing.", encoding="utf-8")
    vendor_note.write_text("---\nauthority: informal_note\n---\nCloudBox is approved.", encoding="utf-8")

    for source in (policy, wiki, vendor_policy, vendor_note):
        result = runner.invoke(cli.app, ["ingest", str(source), "--db", str(database)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["rules_added"] == 1

    ask = runner.invoke(cli.app, ["ask", "Can I use raw SQL for reporting?", "--db", str(database)])
    assert ask.exit_code == 0, ask.output
    answer = json.loads(ask.output)
    assert answer["state"] == "qualified"
    assert answer["items"][0]["authority"] == "approved_policy"
    assert answer["overridden"][0]["rule_id"]

    vendor = runner.invoke(cli.app, ["ask", "Can we use CloudBox for sensitive customer data?", "--db", str(database)])
    assert vendor.exit_code == 0, vendor.output
    vendor_answer = json.loads(vendor.output)
    assert vendor_answer["state"] == "insufficient"
    assert vendor_answer["missing_evidence"] == ["assessment_report", "data_residency_proof"]

    unknown = runner.invoke(cli.app, ["ask", "What logging format do we use?", "--db", str(database)])
    assert unknown.exit_code == 0, unknown.output
    assert json.loads(unknown.output)["state"] == "no_knowledge"

    listed = runner.invoke(cli.app, ["rules", "--component", "database", "--db", str(database)])
    assert listed.exit_code == 0, listed.output
    assert len(json.loads(listed.output)) == 2
    conflicts = runner.invoke(cli.app, ["conflicts", "--db", str(database)])
    assert conflicts.exit_code == 0, conflicts.output
    assert json.loads(conflicts.output)[0]["resolved"] is True


def test_cli_image_ingest_requires_authority_and_saves_image_provenance(tmp_path, monkeypatch):
    class _ImageGemma:
        def __init__(self, **kwargs):
            pass

        def extract_image(self, image_path):
            return ExtractionBatch(
                rules=[Rule(
                    statement="Reporting queries use parameterized statements.",
                    component="database",
                    topic="sql_queries",
                    modality=Modality.MUST,
                    value="parameterized",
                    severity="high",
                    evidence_type="policy_condition",
                    source_quote="Reporting queries MUST use parameterized statements.",
                    confidence=0.9,
                )],
                provenance="image-transcript",
            )

    monkeypatch.setattr(cli, "GemmaClient", _ImageGemma)
    image = tmp_path / "diagram.png"
    image.write_bytes(b"mock image")
    database = tmp_path / "lore.db"

    missing_authority = runner.invoke(cli.app, ["ingest", str(image), "--db", str(database)])
    assert missing_authority.exit_code != 0

    result = runner.invoke(cli.app, [
        "ingest", str(image), "--authority", "approved_policy", "--db", str(database)
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["provenance"] == "image-transcript"
