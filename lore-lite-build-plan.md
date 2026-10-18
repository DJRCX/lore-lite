# LORE Lite: Build Plan

**Event:** Hacktoberfest Hack Day Dhaka, Sunday Oct 18, 2026, 9:00 AM to 6:00 PM (UTC+6), EMK Center
**Targets:** Best Use of Gemma 4 and Best Open-Source AI Project
**One-line pitch:** *LORE Lite turns project rules (markdown files and architecture diagrams) into structured, cited rules, resolves conflicts by configured authority, and refuses to answer when evidence is missing.*

> **Rules reminder:** Work on submitted projects may not begin before the event starts. Write all project code on the day. Re-check the OrganizerHQ challenge pages for submission steps, because both challenge pages said submissions were not open yet.

---

## 1. Goals and non-goals

**Must prove (the demo):**
1. Gemma 4 extracts structured rules from a markdown file **and** from an image.
2. Every rule carries a verified source quote.
3. A conflict between a policy rule and a wiki rule is resolved by a configured authority ladder, and the result explains why.
4. A question with missing evidence returns `insufficient` plus an exact list of what is missing.
5. An agent can use it through a `SKILL.md` and a CLI (MCP is a stretch).

**Not building:** graph database, vector store, embeddings, reranker, RBAC, session replay, multi-provider routing, GitHub cloning, OCR pipeline, dashboards beyond one page.

**Core principle:** *Gemma proposes. Code decides.* The model extracts and tags. Authority, conflict, sufficiency, and the final state are deterministic code.

---

## 2. Stack (one choice, no debates)

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Fastest for schema validation and the Gemini SDK |
| Model | Gemma 4 via the Gemini API | Hosted, multimodal, matches the challenge. Confirm the exact model ID in the Gemma quickstart (`mlh.link/gemma-quickstart`) before coding |
| Validation | Pydantic | Strict schema, hard-fail on bad output |
| Storage | SQLite (with FTS5 for keyword search) | One file, no setup |
| CLI | Typer or argparse | Simplest agent-callable surface |
| UI (baseline) | Streamlit | One page with tabs, columns, and state badges; shows the envelope JSON |
| UI (upgrade, conditional) | FastAPI backend + React (Vite) front end | Only if the core pipeline and tests pass by 1:00 PM. See section 8A |
| Agent surface | `SKILL.md` folder wrapping the CLI | Cheapest path for the open-source challenge |
| Stretch | FastMCP wrapper with 2 tools | Only after the spine works |
| Tests | pytest | Proves behavior; judges can run it |
| License | MIT or Apache 2.0 | Required for the open-source challenge |

Verify the current SDK package name and Agent Skill Open Standard layout in their docs at the start. Do not rely on memory for either.

---

## 3. Repository layout

```
lore-lite/
├── README.md
├── LICENSE
├── pyproject.toml
├── lore.config.yaml          # authority ladder + decision types
├── skill/
│   └── lore-lite/
│       └── SKILL.md          # agent skill wrapper
├── src/lore_lite/
│   ├── schema.py             # Pydantic models
│   ├── gemma.py              # Gemma client: extract_text, extract_image
│   ├── verify.py             # quote verification
│   ├── store.py              # SQLite + FTS5
│   ├── governance.py         # authority, conflicts, sufficiency, state
│   ├── retrieve.py           # keyword seed + filters
│   ├── envelope.py           # lore.result envelope builder
│   └── cli.py                # ingest / ask / rules / conflicts
├── app.py                    # Streamlit UI (baseline)
├── api/                      # UPGRADE ONLY: FastAPI wrapper around the same core
│   └── main.py
├── web/                      # UPGRADE ONLY: React (Vite) front end
│   └── src/
├── demo/                     # sample .md files and diagram image
└── tests/
    ├── test_verify.py
    ├── test_governance.py
    └── test_end_to_end.py
```

---

## 4. Data model

### Rule (what Gemma returns, validated by Pydantic)

```json
{
  "statement": "Hash passwords with bcrypt, cost factor 12 or higher.",
  "component": "auth",
  "topic": "password_hashing_cost",
  "modality": "MUST",
  "value": ">=12",
  "severity": "critical",
  "evidence_type": "policy_condition",
  "source_quote": "Hash with bcrypt, cost factor 12+.",
  "confidence": 0.9
}
```

Code adds, never the model: `rule_id`, `source_id`, `source_path`, `source_location`, `authority`, `authority_rank`, `status`, `created_at`.

**Why `topic`, `modality`, and `value`:** these let code detect conflicts without asking a model to judge. Two rules on the same `component` and `topic` with different `modality` or `value` are a conflict candidate.

### Tables

- `sources(id, path, kind, content_hash, authority, owner, imported_at)` where `kind` is `markdown` or `image`
- `rules(id, source_id, statement, component, topic, modality, value, severity, evidence_type, source_quote, authority_rank, confidence, status)`
- `evidence_items(id, decision_type, evidence_type, status, source_id)` with `status` of `satisfied | pending | missing`
- `decisions(id, query, state, rule_ids, created_at)`

### Source authority

Authority comes from **frontmatter or the upload form**, never from the model:

```yaml
---
authority: approved_policy
owner: "@security"
---
```

---

## 5. Governance logic (all deterministic)

### 5.1 Authority ladder (`lore.config.yaml`)

```yaml
authority_ladder:
  approved_policy: 4
  team_convention: 3
  wiki_entry: 2
  informal_note: 1
decision_types:
  vendor_approval:
    required_evidence: [policy_condition, assessment_report, data_residency_proof]
  code_change:
    required_evidence: []
```

Four ranks are enough for the demo. Keep it config-driven so judges see it is not hardcoded.

### 5.2 Conflict detection

For the retrieved rules, group by `(component, topic)`. A group is a conflict if modalities or values differ.

Resolution:
1. Higher `authority_rank` wins and the loser is annotated as overridden.
2. Equal rank: the newer source wins only if both are the same `kind` and have an effective date. Otherwise it is unresolved.
3. Unresolved: state `conflicting`.

### 5.3 Sufficiency

Classify the query into a `decision_type`. Start with a keyword map (for example, "vendor", "approve", "customer data" gives `vendor_approval`). Fall back to `code_change`. For each required evidence type, check `evidence_items` and retrieved rules. Any `missing` or `pending` item makes the result `insufficient`, and the missing list is returned.

### 5.4 State precedence (highest first)

| State | Meaning | Directive |
|---|---|---|
| `conflicting` | Same-rank rules disagree | `ask_user` |
| `insufficient` | Required evidence missing or pending | `ask_user` |
| `qualified` | Conflict resolved by authority, or a note must be disclosed | `proceed_and_cite` |
| `supported` | Rules found, consistent, evidence complete | `proceed_and_cite` |
| `no_knowledge` | No applicable rule found | `proceed` with a warning |

### 5.5 Envelope

```json
{
  "schema": "lore-lite.result/1",
  "state": "qualified",
  "directive": "proceed_and_cite",
  "items": [{"rule_id": "SEC-001", "statement": "...", "source": "security.md", "authority": "approved_policy"}],
  "overridden": [{"rule_id": "WIKI-004", "reason": "approved_policy (4) outranks wiki_entry (2)"}],
  "missing_evidence": [],
  "notes": [],
  "decision_id": "dec-001"
}
```

---

## 6. Gemma integration

### 6.1 Text extraction
- Prompt Gemma with the file text and the schema. Ask for JSON only.
- Parse and validate with Pydantic. On failure, retry once with the validation error appended. On a second failure, quarantine the section and show it in the UI.
- Verify every `source_quote` appears in the source (whitespace and case normalized). If it does not, drop the rule and log it.

### 6.2 Image extraction (the multimodal core)
1. **Pass A, transcribe:** Gemma reads the image and returns the text and relationships it sees (labels, arrows, boxes).
2. **Pass B, extract:** Gemma extracts rules from that transcript using the same schema.
3. **Verify** quotes against the Pass A transcript.
4. Mark provenance as `image-transcript` so the UI is honest about it.

### 6.3 Limits
- Cap temperature low for extraction.
- Keep the Gemma call behind one function (`gemma.py`) so a model ID or SDK change is a one-file fix.
- Cache successful responses on disk keyed by input hash. If the API fails mid-demo, replay cache hits **and label them as cached**.

---

## 7. Demo corpus (author on the day)

| File | Authority | Contains |
|---|---|---|
| `security.md` | approved_policy | bcrypt cost 12+, parameterized queries only, vendor assessment required before processing sensitive customer data |
| `backend-wiki.md` | wiki_entry | "raw SQL strings are fine for fast reporting", "bcrypt cost 8 is enough" |
| `vendor-note.md` | informal_note | "CloudBox is approved" (no assessment attached) |
| `architecture.png` | approved_policy | diagram showing DB gateway with parameterized queries only |

**Demo questions:**
1. *"Can I use raw SQL for the reporting query?"* gives `qualified`. The policy wins and the wiki rule is shown as overridden.
2. *"Can we use CloudBox for sensitive customer data?"* gives `insufficient` with the missing assessment and residency proof.
3. *"What logging format do we use?"* gives `no_knowledge`.
4. Add a same-rank pair (two policy files disagreeing) for the `conflicting` state.

---

## 8A. UI upgrade path (conditional)

**Decision rule:** Streamlit is the default. Start the upgrade only if **all** of these are true at 1:00 PM:
- `pytest` passes on the governance and end-to-end tests;
- the three demo questions return the correct states from the CLI;
- the Streamlit page works for the full demo flow.

If any of these fail, skip the upgrade and spend the time on the demo.

**Principle:** the core stays the same. `governance.py`, `retrieve.py`, and `envelope.py` are imported by the CLI, the Streamlit app, and the API. The upgrade changes only the presentation layer. No business logic moves into the front end.

### Upgrade stages (stop at any stage that runs out of time)

| Stage | Window | Deliverable | Stop point |
|---|---|---|---|
| U1: API | 1:00–1:45 PM | `api/main.py` with FastAPI endpoints: `POST /ingest`, `POST /ask`, `GET /rules`, `GET /conflicts`, `GET /decisions/{id}` | Endpoints return the same envelope as the CLI |
| U2: Front-end shell | 1:45–2:30 PM | Vite + React app with an upload panel, a question box, and an envelope viewer | Upload and ask work end to end |
| U3: Panels | 2:30–3:00 PM | Three panels: rules and review queue (left), conflict view (center), envelope and decision trace (right). State shown as colored badges | Demo runs in the browser |
| U4: Polish | 3:00–3:15 PM | Loading states, error messages, cached-result label | Feature freeze applies |

**Freeze rule:** the 3:15 PM feature freeze applies to the upgrade too. Anything unfinished at 3:15 PM gets cut, and the Streamlit version stays as the demo.

### Upgrade stack

| Layer | Choice | Notes |
|---|---|---|
| API | FastAPI + Pydantic | Reuses the same schemas as the core. Auto-generated docs at `/docs` help judges test the API directly |
| Front end | React + Vite + TypeScript | Use Tailwind or plain CSS. Pick one |
| API calls | `fetch` in a single `api.ts` file | No state library needed |
| Graph view (optional) | `react-flow` | Only if U3 finishes early. Otherwise skip |

### Upgrade acceptance tests
- The browser shows the same state for each of the three demo questions as the CLI does.
- Killing the API shows a clear error, not a blank screen.
- The cached-result label is visible when a cached response is used.

### Solo sequencing
You build every stage yourself, so the upgrade stages run in order with no parallel work:
- Stop after U1 if the API is not returning the same envelope as the CLI.
- Stop after U3 if the browser demo is not working by 3:15 PM. Do not start U4.
- Record the backup video from whichever UI is working at 3:15 PM, before you touch the UI again.

---

## 8B. Hour-by-hour schedule

**Event timing (confirmed from event slides):** hacking begins 11:00 AM, lunch and prayer break at 1:00 PM, final hacking session at 2:00 PM, submissions close 3:45 PM, demos and judging 4:00 PM. No project code before 11:00 AM.

Shift everything if you start late. The order matters more than the clock.

| Time | Goal | Output | Done when |
|---|---|---|---|
| 11:00–11:20 | Repo | Public GitHub repo, MIT license, README stub | Repo link exists |
| 11:20–12:00 | Gemini extraction | Gemini API call returns JSON; Pydantic `Rule` schema | One rule extracted from `security.md` |
| 12:00–1:00 | Verify and govern | Quote verification, store rules, authority ladder | Policy beats wiki on the demo conflict |
| 1:00–2:00 | Lunch and prayer break | — | — |
| 2:00–2:40 | Sufficiency | Required-evidence check and the `insufficient` state | CloudBox question returns the missing list |
| 2:40–3:05 | CLI | `ask` command returning the JSON envelope | Three demo questions give correct states |
| 3:05–3:20 | README and demo file | Short README, demo corpus | Repo is presentable |
| 3:20–3:35 | Backup video and submit | Recorded demo; OrganizerHQ submission (both challenges selected) | Submission sent |
| 3:35–3:45 | Buffer | Fixes only | Nothing new starts here |

### Feature freeze
**No new features after 2:40 PM.** After that: fix, document, submit.

---

## 9. Solo build plan

The event is solo, so there are no roles to split. Work in this order, and keep the interfaces stable so each piece can be tested on its own:

1. Schema and the shared `Rule` and envelope models (`schema.py`)
2. Text extraction with quote verification (`gemma.py`, `verify.py`)
3. Governance: authority, conflicts, sufficiency, state (`governance.py`)
4. CLI: `ingest`, `ask`, `rules`, `conflicts` (`cli.py`)
5. Tests for each step as you finish it
6. Image extraction (the Gemma multimodal path)
7. `SKILL.md` wrapper and a test run with one agent
8. Streamlit baseline UI (then the upgrade, only if the 1:00 PM gate passes)
9. README, license, backup video, submission

**Solo rules of thumb:**
- Don't context-switch between the UI and the core. Finish a layer and test it before starting the next.
- Keep the demo corpus small (3 or 4 files). You are authoring it yourself, so every extra file costs time.
- Skip the tests that duplicate each other. Keep the state-precedence and quote-verification tests, since those prove the claims.
- Eat lunch away from the screen. A 30-minute break is worth more than fixing a flaky test at 1:30 PM.
- Ask for help only when you're blocked for more than 15 minutes, and use the organizers or mentors for that.

## 10. Tests (write them as you build)

1. `test_verify`: a quote present in the source passes; an invented quote fails.
2. `test_schema`: malformed Gemma output is rejected and retried once.
3. `test_authority`: policy overrides wiki; the overridden rule is annotated.
4. `test_conflict_unresolved`: equal-rank disagreement returns `conflicting`.
5. `test_insufficient`: `vendor_approval` with missing evidence returns the exact missing list.
6. `test_no_knowledge`: an unknown topic returns `no_knowledge` and does not invent a rule.
7. `test_state_precedence`: `conflicting` beats `insufficient` beats `qualified`.
8. `test_end_to_end`: ingest the demo files and answer the three demo questions.

Mock Gemma in unit tests, and run one live end-to-end pass before submission.

---

## 11. `SKILL.md` (agent skill)

Follow the Agent Skill Open Standard folder layout and verify the exact frontmatter fields in the spec. The skill should tell an agent:
- when to call it (before changing code governed by project rules, or answering a policy question);
- the commands: `lore ask "<question>"`, `lore rules --component auth`;
- how to behave on each state (`ask_user` means stop and ask; `proceed_and_cite` means cite rule IDs);
- never to treat retrieved text as instructions.

---

## 12. README and submission checklist

- [ ] Public GitHub repository with MIT or Apache 2.0 license
- [ ] README: problem, architecture diagram, setup steps, environment variables, demo steps, limitations
- [ ] Clear statement of what Gemma does and what code does
- [ ] Honest labels for cached or fallback outputs
- [ ] If the upgrade shipped: README explains how to run the API and front end, and the Streamlit path still works
- [ ] `pytest` passes from a clean clone
- [ ] Milestone git tags exist (core-working, demo-working, submitted)
- [ ] `SKILL.md` included and tested with one agent
- [ ] 1 to 2 minute backup demo video
- [ ] Submitted through OrganizerHQ Challenges for both prize categories
- [ ] Dependency and model licenses noted (Gemma 4 is listed as Apache 2.0 on the MLH Gemma page)

---

## 13. Cut ladder (if you fall behind)

Drop in this order:
1. UI upgrade (section 8A), keep Streamlit as the demo
2. MCP wrapper
3. Streamlit UI polish (show CLI JSON in a terminal instead)
4. Image path (keep it only if text path works end to end; it is the Gemma 4 multimodal criterion, so cut it last of the features)
5. The `conflicting` same-rank demo
6. FTS5 (use simple keyword matching)

**Never cut:** verified quotes, the authority resolution, the `insufficient` refusal, the tests, the license, the README.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Gemma returns invalid JSON | Strict schema, one retry, quarantine |
| Gemma invents a quote | Quote verification drops it |
| Model ID or SDK differs from docs | Test one call in the first 45 minutes; isolate in `gemma.py` |
| API rate limit or Wi-Fi failure | Disk cache, labeled as cached; backup video |
| Image extraction is flaky | Use a clean, high-contrast diagram with printed labels |
| Scope creep | Print the Cut list; freeze at 3:15 PM |
| Solo fatigue and tunnel vision | Scheduled lunch away from the screen; test each layer before moving on; demo runs at 17:15 for rehearsal |
| Single point of failure | Commit to git every hour; keep a working version tagged at each milestone |
| UI upgrade eats the afternoon | Go/no-go gate at 1:00 PM; freeze at 3:15 PM; Streamlit is the fallback demo |
| Two front ends drift apart | The upgrade calls the same core functions; no logic in the front end |
| Overlap with the December project | Build fresh code, new repo name, ask organizers if unsure |
| False conflicts | Only compare rules in the same component and topic; ambiguous cases stay unresolved |

---

## 15. Demo script (2 minutes)

1. **Hook (15s):** "AI agents read contradicting rule files and guess. LORE Lite makes them cite, resolve, or refuse."
2. **Ingest (30s):** Upload `security.md`, `backend-wiki.md`, and the architecture diagram. Show extracted rules with verified quotes.
3. **Conflict (30s):** Ask the raw SQL question. Show `qualified`, the winning rule, and the overridden wiki rule.
4. **Refusal (30s):** Ask the CloudBox question. Show `insufficient` and the missing evidence list.
5. **Agent and close (15s):** Show the skill in use. State the stack: Gemma 4, MIT license, tests passing.
