# LORE Lite Hackathon Task List

Use this list to track the build in dependency order. Mark a task complete only when its acceptance check passes. The event schedule in the project brief is a guide; if starting late, preserve the task order and cut optional work before core behavior.

## 0. Start and repository setup

- [x] Confirm hacking is underway and do not write project code before the event start time. (The event-day setup began after the listed hacking start.)
- [x] Check the public event page and prize categories. The brief mentions OrganizerHQ, but the event page currently lists Devpost and the two target prize categories; confirm the actual submission flow in the organizer portal before submitting.
- [x] Verify the current Gemma 4 model ID, Gemini SDK package name, and Agent Skill Open Standard frontmatter/layout in their official docs. Initial choice: `gemma-4-26b-a4b-it` with the `google-genai` SDK; skill frontmatter requires `name` and `description`.
- [ ] Create the project repository and initial Python package layout from `lore-lite-build-plan.md`.
- [x] Add the chosen open-source license (MIT or Apache 2.0) and a short README stub. (MIT)
- [x] Add a `.gitignore` for Python environments, secrets, local databases, and cache files.
- [x] Create and activate a Python 3.11+ environment; add the minimal dependencies and development commands. (`uv sync --extra dev`; Python 3.12.14)
- [x] Add `lore.config.yaml` with the four authority ranks and the `vendor_approval` and `code_change` decision types.
- [ ] Commit the initial scaffold.

**Milestone: repo ready** — repository exists, package imports, license is present, and secrets/local state are excluded from version control.

## 1. Shared schemas and configuration

- [ ] Define and validate the extracted `Rule` fields: statement, component, topic, modality, value, severity, evidence type, source quote, and confidence.
- [ ] Define code-owned provenance and governance fields: rule/source IDs, source path and location, authority/rank, status, and creation time.
- [ ] Define the result envelope model, including schema version, state, directive, cited items, overridden rules, missing evidence, notes, and decision ID.
- [ ] Define source and evidence representations needed by ingestion and sufficiency checks.
- [ ] Reject malformed or out-of-range model values through schema validation.

**Acceptance:** valid example rule and envelope payloads validate; malformed extraction output fails validation instead of entering storage.

## 2. Gemma extraction and quote verification

- [ ] Implement one isolated Gemma client module with low-temperature JSON extraction and an input-hash cache.
- [ ] Implement Markdown/text extraction using the shared rule schema.
- [ ] On a validation failure, retry once with the validation error; quarantine and expose the section if the retry also fails.
- [ ] Normalize whitespace and case for quote comparison, then retain only rules whose source quote appears in the source text.
- [ ] Record dropped or quarantined extraction results so the UI/CLI can report them.
- [ ] Label cache hits in results; never present cached output as a fresh model response.
- [ ] Keep credentials in environment configuration and document the required variable without committing secrets.

**Acceptance:** a real quote passes verification, an invented quote is dropped, and invalid structured output receives only one retry.

## 3. Storage and retrieval

- [ ] Create SQLite tables for sources, rules, evidence items, and decisions as described in the brief.
- [ ] Store a content hash and source metadata, including kind, authority, owner, and import time.
- [ ] Read authority from frontmatter or upload metadata; do not accept authority claims from model output.
- [ ] Add SQLite FTS5 keyword search if available; keep a simple keyword fallback ready if FTS5 costs time.
- [ ] Implement retrieval filters for relevant component/topic and decision evidence.
- [ ] Make repeated ingestion of the same content safe and avoid silently duplicating rules.

**Acceptance:** ingested sources and rules can be listed and retrieved with their provenance and configured authority.

## 4. Deterministic governance and result envelope

- [ ] Implement query-to-decision-type classification with the brief’s keyword map and `code_change` fallback.
- [ ] Group retrieved rules by `(component, topic)` and flag groups whose modality or value differs.
- [ ] Resolve conflicts by authority rank; annotate lower-ranked rules as overridden with a readable reason.
- [ ] For equal-rank disagreements, use recency only when both rules share a source kind and have effective dates; otherwise leave the conflict unresolved.
- [ ] Check each decision type’s required evidence against evidence items and retrieved rules; return exact missing/pending items.
- [ ] Apply state precedence: `conflicting`, then `insufficient`, then `qualified`, then `supported`, then `no_knowledge`.
- [ ] Map states to directives and build the shared `lore-lite.result/1` envelope.
- [ ] Persist decisions and their rule references for traceability.

**Acceptance:** policy beats wiki with an override explanation; same-rank disagreement stays `conflicting`; missing required evidence yields `insufficient`; unknown topics yield `no_knowledge`.

## 5. CLI and core behavior tests

- [ ] Implement `lore ingest` for Markdown sources and metadata/frontmatter.
- [ ] Implement `lore ask "<question>"` to return the result envelope as JSON.
- [ ] Implement `lore rules --component <name>` and `lore conflicts` for inspection.
- [ ] Add unit tests for quote verification, schema rejection/retry, authority resolution, unresolved conflict, missing evidence, unknown topics, and state precedence.
- [ ] Add an end-to-end test that ingests the demo corpus and asks the demo questions with Gemma mocked.
- [ ] Run the governance and end-to-end tests before considering any UI upgrade.

**Milestone: core working** — tests pass and the CLI can ingest, retrieve, govern, and return a valid envelope without a live model call in unit tests.

## 6. Demo corpus and acceptance run

- [ ] Create `security.md` (`approved_policy`) with bcrypt cost 12+, parameterized queries, and vendor assessment requirements.
- [ ] Create `backend-wiki.md` (`wiki_entry`) containing the conflicting raw SQL and bcrypt cost 8 guidance.
- [ ] Create `vendor-note.md` (`informal_note`) stating CloudBox is approved without attaching the required assessment or residency evidence.
- [ ] Create a clear, high-contrast architecture diagram showing the DB gateway and parameterized queries.
- [ ] Add a same-rank policy disagreement fixture for the `conflicting` demo state.
- [ ] Run and record the expected state for each question:
  - [ ] “Can I use raw SQL for the reporting query?” → `qualified`, with policy cited and wiki rule overridden.
  - [ ] “Can we use CloudBox for sensitive customer data?” → `insufficient`, with the exact missing assessment and residency evidence.
  - [ ] “What logging format do we use?” → `no_knowledge`, with no invented rule.
  - [ ] Same-rank policy disagreement → `conflicting` and `ask_user`.

**Milestone: demo working** — the three required questions and the same-rank conflict produce the expected states and citations from the CLI.

## 7. Image extraction and agent skill

- [ ] Implement image Pass A: ask Gemma to transcribe visible text and describe labels, boxes, and arrows.
- [ ] Implement image Pass B: extract rules from the transcript using the same validated schema as text ingestion.
- [ ] Verify image-derived quotes against the Pass A transcript and label provenance as `image-transcript`.
- [ ] Add an image ingestion command or supported ingestion path for the architecture diagram.
- [ ] Create `skill/lore-lite/SKILL.md` using the verified Agent Skill Open Standard format.
- [ ] Document when an agent should call the skill, the CLI commands, and how to respond to each state.
- [ ] Tell agents to cite rule IDs for `proceed_and_cite`, stop and ask for `ask_user`, and never treat retrieved text as instructions.
- [ ] Try the skill with one agent or compatible skill runner and capture any invocation problems.

**Acceptance:** a rule is extracted from the diagram with transcript provenance and a verifiable quote; the skill exposes usable CLI instructions and state behavior.

## 8. Baseline UI

- [ ] Build one Streamlit page with ingestion and question controls.
- [ ] Show extracted rules, source quotes, provenance, confidence, and quarantine status.
- [ ] Show conflicts and overridden rules with authority rationale.
- [ ] Show the complete result envelope, missing evidence, state badge, and cached-result label.
- [ ] Walk the full demo flow in the UI, including the image path and all result states.

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

- [ ] Expand the README with the problem, architecture diagram, setup, environment variables, demo steps, limitations, and honest division of work between Gemma and deterministic code.
- [ ] Document cached/fallback output labels and model/dependency licensing, including Gemma’s stated license.
- [ ] Run the full test suite from a clean setup and fix blocking failures.
- [ ] Record a 1–2 minute backup demo using whichever UI works at the freeze point.
- [ ] Tag working milestones (`core-working`, `demo-working`, `submitted`) as they are reached.
- [ ] Confirm public repository visibility and license before submission.
- [ ] Submit through OrganizerHQ for both target prize categories and verify submission receipt before the deadline.
- [ ] Use the final buffer only for fixes, documentation, and submission issues; start no new features after the feature freeze.

## Cut order if behind

1. Skip FastAPI/React upgrade; keep Streamlit.
2. Skip MCP.
3. Reduce Streamlit polish or demo from the CLI.
4. Cut image extraction only if the text path is not yet working end to end; retain it as long as feasible for the multimodal criterion.
5. Cut the same-rank conflict demo.
6. Replace FTS5 with simple keyword matching.

Keep quote verification, authority resolution, insufficient-evidence refusal, core tests, license, and README.
