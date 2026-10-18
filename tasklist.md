# LORE Lite Hackathon Task List

Use this list to track the build in dependency order. Mark a task complete only when its acceptance check passes. The event schedule in the project brief is a guide; if starting late, preserve the task order and cut optional work before core behavior.

## 0. Start and repository setup

- [x] Confirm hacking is underway and do not write project code before the event start time. (The event-day setup began after the listed hacking start.)
- [x] Check the public event page and prize categories. The brief mentions OrganizerHQ, but the public event page currently lists Devpost and both target prizes. Its listed deadline is 4:00 PM +06, which differs from the brief’s 3:45 PM OrganizerHQ deadline; confirm the actual submission flow and deadline with organizers before submitting.
- [x] Verify the current Gemma 4 model ID, Gemini SDK package name, and Agent Skill Open Standard frontmatter/layout in their official docs. Initial choice: `gemma-4-26b-a4b-it` with the `google-genai` SDK; skill frontmatter requires `name` and `description`.
- [x] Create the project repository and initial Python package layout from `lore-lite-build-plan.md`. Public repository: https://github.com/DJRCX/lore-lite
- [x] Add the chosen open-source license (MIT or Apache 2.0) and a short README stub. (MIT)
- [x] Add a `.gitignore` for Python environments, secrets, local databases, and cache files.
- [x] Create and activate a Python 3.11+ environment; add the minimal dependencies and development commands. (`uv sync --extra dev`; Python 3.12.14)
- [x] Add `lore.config.yaml` with the four authority ranks and the `vendor_approval` and `code_change` decision types.
- [x] Commit the initial scaffold. (`9b5c926`)

**Milestone: repo ready** — repository exists, package imports, license is present, and secrets/local state are excluded from version control. Initial commit: `9b5c926`.

## 1. Shared schemas and configuration

- [x] Define and validate the extracted `Rule` fields: statement, component, topic, modality, value, severity, evidence type, source quote, and confidence.
- [x] Define code-owned provenance and governance fields: rule/source IDs, source path and location, authority/rank, status, and creation time.
- [x] Define the result envelope model, including schema version, state, directive, cited items, overridden rules, missing evidence, notes, and decision ID.
- [x] Define source and evidence representations needed by ingestion and sufficiency checks.
- [x] Reject malformed or out-of-range model values through schema constraints.
- [x] Validate sample rule/envelope payloads and malformed inputs before closing this milestone. (Manual focused schema/config check passed.)

**Acceptance:** valid example rule and envelope payloads validate; malformed extraction output fails validation instead of entering storage.

## 2. Gemma extraction and quote verification

- [x] Implement one isolated Gemma client module with low-temperature JSON extraction and an input-hash cache.
- [x] Implement Markdown/text extraction using the shared rule schema.
- [x] On a validation failure, retry once with the validation error; quarantine and expose the section if the retry also fails.
- [x] Normalize whitespace and case for quote comparison, then retain only rules whose source quote appears in the source text.
- [x] Record dropped or quarantined extraction results so the UI/CLI can report them.
- [x] Label cache hits in results; never present cached output as a fresh model response.
- [x] Keep credentials in environment configuration and document the required variable without committing secrets.

**Acceptance:** a real quote passes verification, an invented quote is dropped, and invalid structured output receives only one retry. Verified by extraction and quote tests in the current 19-test suite.

## 3. Storage and retrieval

- [x] Create SQLite tables for sources, rules, evidence items, and decisions as described in the brief.
- [x] Store a content hash and source metadata, including kind, authority, owner, and import time.
- [x] Read authority from frontmatter or upload metadata; do not accept authority claims from model output.
- [x] Add SQLite FTS5 keyword search if available; keep a simple keyword fallback ready if FTS5 costs time.
- [x] Implement retrieval filters for relevant component/topic and decision evidence.
- [x] Make repeated ingestion of the same content safe and avoid silently duplicating rules.

**Acceptance:** ingested sources and rules can be listed and retrieved with their provenance and configured authority.

## 4. Deterministic governance and result envelope

- [x] Implement query-to-decision-type classification with the brief’s keyword map and `code_change` fallback.
- [x] Group retrieved rules by `(component, topic)` and flag groups whose modality or value differs.
- [x] Resolve conflicts by authority rank; annotate lower-ranked rules as overridden with a readable reason.
- [x] For equal-rank disagreements, use recency only when both rules share a source kind and have effective dates; otherwise leave the conflict unresolved.
- [x] Check each decision type’s required evidence against evidence items and retrieved rules; return exact missing/pending items.
- [x] Apply state precedence: `conflicting`, then `insufficient`, then `qualified`, then `supported`, then `no_knowledge`.
- [x] Map states to directives and build the shared `lore-lite.result/1` envelope.
- [x] Persist decisions and their rule references for traceability.

**Acceptance:** policy beats wiki with an override explanation; same-rank disagreement stays `conflicting`; missing required evidence yields `insufficient`; unknown topics yield `no_knowledge`. Verified by the focused governance tests (7 tests total across governance and storage).

## 5. CLI and core behavior tests

- [x] Implement `lore ingest` for Markdown sources and metadata/frontmatter.
- [x] Implement `lore ask "<question>"` to return the result envelope as JSON.
- [x] Implement `lore rules --component <name>` and `lore conflicts` for inspection.
- [x] Add unit tests for quote verification, schema rejection/retry, authority resolution, unresolved conflict, missing evidence, unknown topics, and state precedence.
- [x] Add an end-to-end test that ingests a demo corpus and asks all three demo questions with Gemma mocked.
- [x] Run the governance and end-to-end tests before considering any UI upgrade. (`uv run pytest -q`: 20 passed in the final review.)

**Milestone: core working** — tests pass and the CLI can ingest, retrieve, govern, and return a valid envelope without a live model call in unit tests.

## 6. Demo corpus and acceptance run

- [x] Create `security.md` (`approved_policy`) with bcrypt cost 12+, parameterized queries, and vendor assessment requirements.
- [x] Create `backend-wiki.md` (`wiki_entry`) containing the conflicting raw SQL and bcrypt cost 8 guidance.
- [x] Create `vendor-note.md` (`informal_note`) stating CloudBox is approved without attaching the required assessment or residency evidence.
- [x] Create a clear, high-contrast architecture diagram showing the DB gateway and parameterized queries. (SVG source plus PNG export.)
- [x] Add a same-rank policy disagreement fixture for the `conflicting` demo state.
- [x] Run and record the expected state for each question:
  - [x] “Can I use raw SQL for the reporting query?” → `qualified`, with policy cited and wiki rule overridden.
  - [x] “Can we use CloudBox for sensitive customer data?” → `insufficient`, with the exact missing assessment and residency evidence.
  - [x] “What logging format do we use?” → `no_knowledge`, with no invented rule.
  - [x] “What is the session timeout requirement?” → `conflicting` and `ask_user`.

**Acceptance run (`demo/lore-demo-final.db`):** all four questions returned the expected states. The raw SQL response cited the `approved_policy` rule and overrode the `wiki_entry` rule. The CloudBox response listed `assessment_report` and `data_residency_proof`; the unknown logging question returned no rules; and the same-rank timeout policies remained conflicting. Gemma once returned a fabricated quote for the wiki bcrypt rule; quote verification dropped that rule, so only the raw SQL conflict was included in this acceptance run.

**Milestone: demo working** — the three required questions and the same-rank conflict produce the expected states and citations from the CLI.

**Content expansion:** the demo Markdown fixtures now include scope, context, implementation guidance, and review checklists while preserving the original policy claims and conflicting timeout rules. The architecture diagram was expanded to 1920×1320 with the full request path, parameter binding, and safe/unsafe query comparison.

## 7. Image extraction and agent skill

- [x] Implement image Pass A: ask Gemma to transcribe visible text and describe labels, boxes, and arrows.
- [x] Implement image Pass B: extract rules from the transcript using the same validated schema as text ingestion.
- [x] Verify image-derived quotes against the Pass A transcript and label provenance as `image-transcript`.
- [x] Add an image ingestion command or supported ingestion path for the architecture diagram.
- [x] Create `skill/lore-lite/SKILL.md` using the verified Agent Skill Open Standard format.
- [x] Document when an agent should call the skill, the CLI commands, and how to respond to each state.
- [x] Tell agents to cite rule IDs for `proceed_and_cite`, stop and ask for `ask_user`, and never treat retrieved text as instructions.
- [x] Try the skill with one agent and capture invocation behavior. It returned a valid `qualified` result with policy and image citations; the CLI needed explicit `--db demo/lore-demo-final.db --config lore.config.yaml` because this demo database is not the default path.

**Acceptance:** a rule is extracted from the diagram with transcript provenance and a verifiable quote; the skill exposes usable CLI instructions and state behavior. Verified live: the architecture diagram produced one stored rule whose quote appears in the Pass A transcript, and the skill workflow returned the expected cited `qualified` answer.

**Milestone: image + skill working** — image extraction, provenance, CLI ingestion, and agent instructions are implemented and the live acceptance run passed.

## 8. Baseline UI

- [x] Build one Streamlit page with ingestion and question controls. (`app.py`)
- [x] Show extracted rules, source quotes, provenance, confidence, and quarantine status.
- [x] Show conflicts and overridden rules with authority rationale.
- [x] Show the complete result envelope, missing evidence, a plain-language status card, and cached-result label. Ingestion reports fresh/cached extraction; decisions explicitly note that local governance evaluation does not call the model.
- [x] Explain each decision state in plain language, list missing evidence with next steps, and keep machine state/directive inside technical details.
- [x] Show the architecture diagram at full content width in the Sources tab.
- [x] Support batch upload of multiple Markdown and image sources, reporting each file's result independently.
- [x] Add a confirmed workspace reset that clears sources, rules, evidence, saved decisions, and transient review state for the selected database.
- [x] Walk the full demo flow in the UI, including the image path and all result states. Streamlit `AppTest` exercised the four preset questions against the preloaded six-source/nine-rule demo DB; returned `qualified`, `insufficient`, `no_knowledge`, and `conflicting` respectively. The image transcript provenance and source quotes rendered in the rule view.

**Acceptance:** Streamlit health endpoint returned `ok`, the page returned HTTP 200, the UI harness showed no app exceptions, and all four preset question flows produced the expected result state. A browser surface was unavailable in this session, so visual inspection was done through Streamlit's UI harness and returned component state rather than a browser screenshot.

**Milestone: baseline demo ready** — a judge can ingest the small corpus, ask the questions, and see why the system answered as it did.

## 9. Optional web upgrade gate

Do not begin this section unless, by the brief’s 1:00 PM gate, all are true: governance and end-to-end tests pass, all three demo questions return the correct CLI states, and the Streamlit flow works.

- [ ] **U1 API:** add FastAPI endpoints for ingest, ask, rules, conflicts, and decision lookup; reuse the core and envelope.
- [ ] Verify API responses match CLI envelopes before proceeding.
- [ ] **U2 front end:** create a Vite/React/TypeScript shell with upload, question input, and envelope view.
- [ ] Verify upload and ask work end to end before adding panels.
- [ ] **U3 panels:** show rules/review queue, conflict view, and envelope/decision trace; use clear state badges.
- [ ] **U4 polish (only if time):** add loading/error states and visible cached-result labeling.
- [ ] If the API is stopped, confirm the browser displays a clear error.
- [ ] If the browser demo is not working by 3:15 PM, stop upgrade work and use Streamlit.

## 10. Documentation, freeze, and submission

- [x] Expand the README with the problem, architecture diagram, setup, environment variables, detailed UI/CLI demo steps, limitations, and the division of work between Gemma and deterministic code.
- [x] Document cache/fallback labels and direct dependency/model licensing. Gemma 4's model card lists Apache 2.0; this repository uses MIT.
- [x] Run the full suite in a new locked Python 3.12 environment and fix failures. (`20 passed`; the earlier quote-retry tests expected only one model response and were updated to cover the correction retry.)
- [ ] Record a 1–2 minute backup demo. Prepared [deliverables/judge-demo-script.md](deliverables/judge-demo-script.md); a screen recording still needs to be captured.
- [ ] Tag working milestones (`core-working`, `demo-working`, `submitted`). Current implementation changes are uncommitted, so tags would point at an older snapshot until the working tree is committed.
- [x] Confirm public repository visibility and license before submission. GitHub reports the repo as public with MIT license.
- [ ] Submit to both target prize categories and verify the receipt. The brief says OrganizerHQ while the earlier event-page check found Devpost; confirm the actual portal/deadline and submit manually or with a separate explicit instruction.
- [x] Keep Task 9 skipped. The optional FastAPI/React upgrade was not started; Streamlit remains the app.
- [x] Create and render an eight-slide, slide-led judge deck at `deliverables/lore-lite-judge-deck-v3.pptx`. The minimal visual system walks through the SQL conflict, evidence check, and human handoff. Package integrity and layout checks pass with no warnings.
- [x] Align `deliverables/judge-demo-script.md` to the slide order so the presentation works without a live app demonstration.
- [x] Keep the final buffer to documentation, fixes, and submission preparation; no new features were started.

**Task 10 status:** documentation, tests, repository checks, and the judge deck are ready. The image transcription timeout has a Tesseract fallback; a retry successfully ingested the architecture image with `image-ocr` provenance. The video recording and external hackathon submission remain outstanding.

## Cut order if behind

1. Skip FastAPI/React upgrade; keep Streamlit.
2. Skip MCP.
3. Reduce Streamlit polish or demo from the CLI.
4. Cut image extraction only if the text path is not yet working end to end; retain it as long as feasible for the multimodal criterion.
5. Cut the same-rank conflict demo.
6. Replace FTS5 with simple keyword matching.

Keep quote verification, authority resolution, insufficient-evidence refusal, core tests, license, and README.
