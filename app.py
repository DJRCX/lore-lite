"""Streamlit review console for LORE Lite's cited project rules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from lore_lite.config import load_config
from lore_lite.gemma import GemmaClient, GemmaConfigurationError
from lore_lite.governance import govern_query, resolve_conflicts
from lore_lite.ingest import rule_records, source_from_image, source_from_markdown
from lore_lite.schema import SourceKind
from lore_lite.store import Store


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "lore.config.yaml"
DEMO_DB = ROOT / "demo" / "lore-demo-final.db"
PRESET_QUESTIONS = [
    "Can I use raw SQL for the reporting query?",
    "Can we use CloudBox for sensitive customer data?",
    "What logging format do we use?",
    "What is the session timeout requirement?",
]
STATE_COLORS = {
    "qualified": "#087443",
    "supported": "#087443",
    "insufficient": "#b42318",
    "conflicting": "#b42318",
    "no_knowledge": "#705400",
}
EVIDENCE_LABELS = {
    "assessment_report": "the vendor security assessment report",
    "data_residency_proof": "proof of where the vendor stores and processes data",
    "policy_condition": "the applicable policy requirement",
}

st.set_page_config(page_title="LORE Lite | Rule review", page_icon="◇", layout="wide")
st.markdown(
    """
    <style>
    :root {
      color-scheme: light;
      --text-color: #111111;
      --background-color: #ffffff;
      --secondary-background-color: #f3f3f3;
      --primary-color: #087443;
    }
    .stApp, [data-testid="stAppViewContainer"], section[data-testid="stMain"] {
      background: #ffffff !important; color: #111111 !important;
    }
    [data-testid="stHeader"] { background: #ffffff; }
    [data-testid="stMain"] :is(p, label, h1, h2, h3, h4, h5, h6, li, summary,
      [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
      [data-testid="stMetricLabel"], [data-testid="stMetricValue"],
      [data-testid="stMetricDelta"]) { color: #111111; }
    [data-testid="stSidebar"] { background: #111111 !important; }
    [data-testid="stSidebar"] :is(p, label, h1, h2, h3, h4, h5, h6, li, span,
      [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"]) {
      color: #ffffff !important; opacity: 1 !important;
    }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
      background: #ffffff !important; color: #111111 !important;
    }
    [data-testid="stSidebar"] input::placeholder,
    [data-testid="stSidebar"] textarea::placeholder { color: #555555 !important; }
    [data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {
      color: #111111 !important;
    }
    [data-baseweb="popover"] [role="listbox"],
    [data-baseweb="popover"] [role="option"],
    [data-baseweb="menu"], [data-baseweb="menu"] * {
      background: #ffffff !important; color: #111111 !important;
    }
    [data-baseweb="popover"] [role="option"]:hover,
    [data-baseweb="popover"] [role="option"][aria-selected="true"] {
      background: #e8f5ed !important; color: #111111 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
      background: #eeeeee !important; border: 1px solid #555555 !important;
    }
    .hero { padding: 1.35rem 1.55rem; background: #111111; color: #ffffff;
      border-radius: 12px; margin: .15rem 0 1.15rem; }
    .hero h1 { margin: 0; color: #ffffff !important; letter-spacing: -.035em; font-size: 2.15rem; }
    .hero p { margin: .35rem 0 0; color: #eeeeee !important; font-size: 1rem; }
    .eyebrow { color: #87e6b4; font-size: .76rem; font-weight: 750;
      letter-spacing: .13em; text-transform: uppercase; }
    .state { display: inline-block; padding: .36rem .7rem; border-radius: 999px;
      color: #ffffff !important; font-weight: 750; font-size: .83rem; letter-spacing: .04em; }
    .rule-card { background: #ffffff; color: #111111; border: 1px solid #777777;
      border-radius: 10px; padding: 1rem 1.1rem; margin: .55rem 0; }
    .rule-card small { color: #333333; }
    div[data-testid="stMetric"] { background: #ffffff; color: #111111;
      border: 1px solid #777777; border-radius: 10px; padding: .8rem 1rem; }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #111111 !important; }
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-baseweb="select"] > div {
      background: #ffffff !important; color: #111111 !important;
      border-color: #555555 !important;
    }
    input::placeholder, textarea::placeholder { color: #555555 !important; opacity: 1; }
    [data-baseweb="select"] *, [role="listbox"] *, [role="option"] {
      color: #111111 !important;
    }
    [data-testid="stTabs"] button,
    [data-testid="stTabs"] button * { color: #222222 !important; }
    [data-testid="stTabs"] button[aria-selected="true"],
    [data-testid="stTabs"] button[aria-selected="true"] * {
      color: #075e38 !important; border-bottom-color: #087443 !important;
    }
    [data-testid="stExpander"],
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] [data-testid="stExpanderHeader"],
    [data-testid="stExpander"] details > summary,
    [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
      background: #f3f3f3 !important; color: #111111 !important;
      border-color: #777777 !important;
    }
    [data-testid="stExpander"] summary *,
    [data-testid="stExpander"] [data-testid="stExpanderHeader"] *,
    [data-testid="stExpander"] details > summary *,
    [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] * {
      color: #111111 !important;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
      background: #ffffff !important; color: #111111 !important;
    }
    [data-testid="stCode"] pre, [data-testid="stCode"] code {
      background: #f1f1f1 !important; color: #111111 !important;
    }
    [data-testid="stAlert"] { color: #111111 !important; border: 1px solid #777777; }
    [data-testid="stAlert"] p { color: #111111 !important; }
    [data-testid="stAlert"] [data-testid="stNotificationContentSuccess"] {
      background: #e8f5ed; color: #064b2b;
    }
    [data-testid="stAlert"] [data-testid="stNotificationContentError"] {
      background: #fff0ef; color: #8f1d14;
    }
    [data-testid="stAlert"] [data-testid="stNotificationContentWarning"] {
      background: #fff5cc; color: #4d3900;
    }
    button, [data-testid="stBaseButton-primary"] {
      color: #111111;
    }
    button[kind="primary"], [data-testid="stBaseButton-primary"],
    div[data-testid="stButton"] button[kind="primary"] {
      background: #087443 !important; border-color: #087443 !important;
      color: #ffffff !important;
    }
    button[kind="primary"] *, [data-testid="stBaseButton-primary"] *,
    div[data-testid="stButton"] button[kind="primary"] * {
      color: #ffffff !important; fill: #ffffff !important;
    }
    button[kind="secondary"], [data-testid="stBaseButton-secondary"],
    div[data-testid="stButton"] button:not([kind="primary"]) {
      background: #eeeeee !important; border: 1px solid #555555 !important;
      color: #111111 !important;
    }
    button[kind="secondary"] *, [data-testid="stBaseButton-secondary"] *,
    div[data-testid="stButton"] button:not([kind="primary"]) * {
      color: #111111 !important;
    }
    :is(button, input, textarea, [role="combobox"], [role="tab"]):focus-visible {
      outline: 3px solid #087443 !important; outline-offset: 2px !important;
      box-shadow: 0 0 0 2px #ffffff !important;
    }
    @media (forced-colors: active) {
      .hero, .state, button { forced-color-adjust: auto; }
      :focus-visible { outline: 3px solid Highlight !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _default_db() -> str:
    return str(DEMO_DB if DEMO_DB.exists() else ROOT / "lore.db")


def _format_rule(rule) -> None:
    st.markdown(
        f"""<div class="rule-card"><b>{rule.statement}</b><br>
        <small>{rule.component} / {rule.topic} · {rule.modality.value} · {rule.authority} (rank {rule.authority_rank})</small><br>
        <small>Source: {rule.source_path} · {rule.source_kind.value} · {rule.provenance} · confidence {rule.confidence:.2f}</small></div>""",
        unsafe_allow_html=True,
    )
    with st.expander("Source quote and identifiers"):
        st.caption(f"Rule ID: {rule.rule_id} · Status: {rule.status.value}")
        st.code(rule.source_quote, language=None)


def _ingest_upload(upload, db_path: Path, authority: str | None, owner: str | None) -> dict:
    config = load_config(CONFIG_PATH)
    suffix = Path(upload.name).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="lore-upload-") as temp_dir:
        path = Path(temp_dir) / Path(upload.name).name
        data = upload.getvalue()
        path.write_bytes(data)
        if suffix in {".md", ".markdown", ".mdown"}:
            content = data.decode("utf-8")
            source = source_from_markdown(path.name, content, config, authority=authority, owner=owner)
        else:
            if not authority:
                raise ValueError("Choose an authority for image sources.")
            source = source_from_image(path.name, data, config, authority=authority, owner=owner)
        store = Store(db_path)
        if store.has_source(source.path, source.content_hash):
            return {"status": "already_ingested", "source": source.path, "rules_added": 0}
        client = GemmaClient()
        batch = client.extract_image(path) if source.kind == SourceKind.IMAGE else client.extract_text(content, source_path=path.name)
        records = rule_records(batch.rules, source, config, provenance=batch.provenance)
        inserted = store.add_source(source, records)
        return {
            "status": "ingested" if inserted else "already_ingested",
            "source": source.path,
            "authority": source.authority,
            "kind": source.kind.value,
            "rules_added": len(records) if inserted else 0,
            "cache_status": batch.cache_status,
            "provenance": batch.provenance,
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
            "transcript": batch.transcript,
        }


st.markdown(
    '<section class="hero"><div class="eyebrow">Governance console · Gemma + deterministic review</div>'
    '<h1>Project rules, with receipts.</h1>'
    '<p>Inspect the source, authority, and evidence behind every decision.</p></section>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Workspace")
    db_text = st.text_input("SQLite database", value=_default_db(), help="The demo database is preloaded when available.")
    db_path = Path(db_text).expanduser()
    config = load_config(CONFIG_PATH)
    st.caption(f"Authorities: {', '.join(config.authority_ladder)}")
    st.divider()
    st.markdown("### Add a source")
    uploads = st.file_uploader(
        "Markdown or diagrams", type=["md", "markdown", "png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        help="Select several Markdown files and images to ingest them in one batch.",
    )
    authority_choice = st.selectbox("Authority override", ["Use Markdown frontmatter", *config.authority_ladder.keys()])
    authority = None if authority_choice == "Use Markdown frontmatter" else authority_choice
    owner = st.text_input("Owner (optional)") or None
    if st.button("Extract and ingest", type="primary", disabled=not uploads, width="stretch"):
        reports = []
        progress = st.progress(0, text="Starting batch…")
        for index, upload in enumerate(uploads, start=1):
            try:
                progress.progress((index - 1) / len(uploads), text=f"Reading {upload.name} ({index}/{len(uploads)})…")
                with st.spinner(f"Extracting {upload.name} and checking its quotes…"):
                    report = _ingest_upload(upload, db_path, authority, owner)
                reports.append({"file": upload.name, "report": report})
            except (ValueError, UnicodeDecodeError, GemmaConfigurationError) as exc:
                reports.append({"file": upload.name, "error": str(exc)})
            except Exception as exc:  # surfaced without exposing credentials
                reports.append({"file": upload.name, "error": f"{type(exc).__name__}: {exc}"})
            progress.progress(index / len(uploads), text=f"Processed {index} of {len(uploads)} files")
        progress.empty()
        st.session_state["last_ingest_batch"] = reports
    for item in st.session_state.get("last_ingest_batch", []):
        st.markdown(f"**{item['file']}**")
        if "error" in item:
            st.error(item["error"])
            continue
        report = item["report"]
        st.success(f"{report['status'].replace('_', ' ').title()} · {report['rules_added']} rules added")
        if "cache_status" in report:
            st.caption(f"Extraction cache: {report['cache_status']} · provenance: {report['provenance']}")
        if report.get("provenance") == "image-ocr":
            st.warning("Gemini timed out, so local OCR read this image. Review the diagram relationships carefully.")
        if report.get("transcript"):
            with st.expander(f"Image transcription · {item['file']}"): st.text(report["transcript"])
        if report.get("rejected_rules"):
            st.warning("Some rules were rejected because their quotes did not match.")
            st.code(json.dumps(report["rejected_rules"], indent=2), language="json")
        if report.get("quarantined_sections"):
            st.error("Some sections were quarantined after invalid model output.")
            st.code(json.dumps(report["quarantined_sections"], indent=2), language="json")

    st.divider()
    if st.button("Reset workspace data", width="stretch", help="Clear sources, rules, evidence, decisions, and current review state in the selected database."):
        st.session_state["confirm_workspace_reset"] = True
    if st.session_state.get("confirm_workspace_reset"):
        st.warning(f"This will permanently clear all sources and review data in `{db_path}`.")
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("Confirm reset", type="primary", width="stretch"):
            counts = Store(db_path).reset_workspace()
            for key in ("last_ingest_batch", "last_outcome", "last_question", "question"):
                st.session_state.pop(key, None)
            st.session_state.pop("confirm_workspace_reset", None)
            st.success(
                f"Workspace cleared: {counts['sources']} sources, {counts['rules']} rules, "
                f"{counts['evidence']} evidence items, and {counts['decisions']} saved decisions."
            )
            st.rerun()
        if cancel_col.button("Cancel", width="stretch"):
            st.session_state.pop("confirm_workspace_reset", None)
            st.rerun()

try:
    store = Store(db_path)
    config = load_config(CONFIG_PATH)
except Exception as exc:
    st.error(f"Could not open the selected database or configuration: {exc}")
    st.stop()

question_col, status_col = st.columns([3, 1])
with question_col:
    question = st.text_input("Ask a project question", placeholder="Can I use raw SQL for the reporting query?")
with status_col:
    st.write("")
    ask_clicked = st.button("Evaluate question", type="primary", width="stretch")

st.caption("Try a demo question")
demo_cols = st.columns(4)
for index, preset in enumerate(PRESET_QUESTIONS):
    if demo_cols[index].button(["Raw SQL", "CloudBox", "Logging", "Session timeout"][index], width="stretch"):
        st.session_state["question"] = preset
        question = preset
        ask_clicked = True

if ask_clicked and question.strip():
    outcome = govern_query(store, config, question.strip())
    st.session_state["last_outcome"] = outcome.envelope.model_dump(mode="json", by_alias=True)
    st.session_state["last_question"] = question.strip()

rules = store.list_rules()
sources = store.list_sources()
resolved, overridden_all, conflicts_all, _ = resolve_conflicts(rules)
metric_cols = st.columns(4)
metric_cols[0].metric("Sources", len(sources))
metric_cols[1].metric("Extracted rules", len(rules))
metric_cols[2].metric("Conflicts", len(conflicts_all))
quarantine_count = sum(
    len(item.get("report", {}).get("quarantined_sections", []))
    for item in st.session_state.get("last_ingest_batch", [])
)
metric_cols[3].metric("Quarantines", quarantine_count)

answer_tab, rules_tab, conflict_tab, sources_tab = st.tabs(["Decision", "Rules", "Conflicts", "Sources"])
with answer_tab:
    envelope = st.session_state.get("last_outcome")
    if envelope:
        state = envelope["state"]
        if state == "qualified":
            st.success("**Follow the approved rule below.** A lower-authority source disagrees, but the approved policy takes precedence. The request is safe to continue only using the cited approach.")
        elif state == "supported":
            st.success("**A verified project rule supports this.** Follow the cited rule and include it when documenting the change.")
        elif state == "insufficient":
            st.error("**There isn’t enough evidence to approve this yet.** The project requires supporting documents before this request can proceed.")
        elif state == "conflicting":
            st.error("**The project’s approved rules disagree. Pause before proceeding.** Ask the policy owner to confirm which requirement applies.")
        else:
            st.warning("**I couldn’t find a verified rule for this question.** Check with the project owner or add an authoritative source; this tool won’t guess a policy.")

        if envelope["missing_evidence"]:
            st.markdown("**What is missing and what to do next**")
            for evidence in envelope["missing_evidence"]:
                clean_evidence = evidence.removesuffix(" (pending)")
                label = EVIDENCE_LABELS.get(clean_evidence, clean_evidence.replace("_", " "))
                status_note = " It has been requested but is still pending." if evidence.endswith(" (pending)") else ""
                st.markdown(f"- Provide {label}.{status_note}")
        if state == "conflicting" and envelope["items"]:
            st.markdown("**The rules that disagree**")
            for item in envelope["items"]:
                st.markdown(f"- {item['statement']} *(from {item['source']}, authority: {item['authority']})*")

        st.markdown("#### Supporting project rules")
        if not envelope["items"]:
            st.info("No verified project rule was found to support an answer.")
        for item in envelope["items"]:
            st.markdown(f"**{item['statement']}**")
            st.caption(f"Source: {item['source']} · Authority: {item['authority']} · Rule ID: `{item['rule_id']}`")
            st.code(item["source_quote"], language=None)
        if envelope["overridden"]:
            st.markdown("#### Why another source wasn’t followed")
            indexed = {rule.rule_id: rule for rule in rules}
            for item in envelope["overridden"]:
                rule = indexed.get(item["rule_id"])
                reason = item["reason"]
                if "overridden by " in reason:
                    authority_name = reason.split("overridden by ", 1)[1].split(" (", 1)[0].replace("_", " ")
                    plain_reason = f"a higher-authority {authority_name} source takes precedence"
                elif " outranks " in reason:
                    authority_name = reason.split(" outranks ", 1)[0].replace("_", " ")
                    plain_reason = f"the {authority_name} source has higher authority"
                elif "newer same-kind source" in reason:
                    plain_reason = "a newer source of the same type takes precedence"
                else:
                    plain_reason = "the governing project rules give it lower priority"
                st.markdown(f"- {rule.statement if rule else item['rule_id']} **was not followed** because {plain_reason}.")
        with st.expander("Technical details and complete result (JSON)"):
            st.markdown(f"**System state:** `{state}` · **Directive:** `{envelope['directive']}` · **Decision ID:** `{envelope['decision_id']}`")
            st.caption("The answer is evaluated deterministically from the local database; this step does not call the model.")
            if envelope["notes"]:
                st.markdown("**Additional notes**")
                for note in envelope["notes"]: st.markdown(f"- {note}")
            st.code(json.dumps(envelope, indent=2), language="json")
    else:
        st.info("Choose a demo question or enter one above to see a cited decision envelope.")

with rules_tab:
    if not rules:
        st.info("No rules stored in this database yet.")
    for rule in rules: _format_rule(rule)

with conflict_tab:
    if not conflicts_all:
        st.info("No rule disagreements are currently stored.")
    for group in conflicts_all:
        label = "Resolved by authority" if group.resolved else "Unresolved · ask user"
        with st.expander(f"{group.component} / {group.topic} · {label}", expanded=not group.resolved):
            if group.reason: st.caption(group.reason)
            for rule in group.rules:
                _format_rule(rule)
            if group.resolved:
                st.success("Lower-ranked disagreement is overridden by the displayed authority rationale.")
            else:
                st.warning("Equal-rank disagreement has no eligible tie-break; the result remains conflicting.")

with sources_tab:
    if not sources:
        st.info("No sources stored yet.")
    for source in sources:
        st.markdown(f"**{source.path}** · {source.kind.value} · `{source.authority}` · owner: {source.owner or '—'}")
        st.caption(f"Imported {source.imported_at.isoformat()} · SHA-256 `{source.content_hash[:16]}…`")
    diagram_path = ROOT / "demo" / "architecture.png"
    if diagram_path.is_file():
        st.markdown("#### Architecture diagram")
        st.caption("Expanded request path, parameter binding, and the prohibited SQL pattern.")
        st.image(str(diagram_path), caption="Secure database request path", width="stretch")
