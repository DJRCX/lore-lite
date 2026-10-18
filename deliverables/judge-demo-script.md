# LORE Lite judge presentation script

**Length:** about 2 minutes. Present from the slides only. No live app walkthrough is needed.

## Slide 1 · Project rules, with receipts

“LORE Lite helps AI coding agents follow project rules and show where those rules came from. When the evidence cannot settle a question, it makes that clear too.”

## Slide 2 · One question, two instructions

“Imagine an agent is asked whether it can use raw SQL. The approved security policy says reporting queries must use parameterized statements. An older backend wiki says raw SQL is fine. A simple search can find both statements, but the agent still needs a trustworthy way to decide what to do.”

Point to the two source labels and their authority ranks.

## Slide 3 · The workflow

“LORE Lite takes project Markdown and diagrams as sources. Gemma extracts candidate rules. The application checks each citation against the source, then evaluates questions using configured authority and evidence rules.”

Move across the four numbered steps as you explain them.

## Slide 4 · Authority comes from the source

“Gemma helps read the documents, but it does not decide which author or document has more authority. LORE Lite verifies the quote and gets the source rank from trusted metadata. Deterministic code uses that rank to resolve disagreements.”

## Slide 5 · Resolved guidance

“For the raw SQL question, LORE Lite returns a qualified result: use parameterized statements. It cites the approved policy at rank four and shows the wiki entry at rank two as overridden. The answer includes the reason, so a developer or agent can check it.”

## Slide 6 · Missing evidence

“Now consider CloudBox and sensitive customer data. The policy requires an assessment report and proof of data residency. The informal note saying CloudBox is approved does not provide those records, so LORE Lite names what is missing and gives the reviewer a clear next step.”

## Slide 7 · Human review and unknowns

“The session timeout policies have equal authority, but one requires fifteen minutes and the other thirty. LORE Lite leaves that decision to a person. For the logging question, there is no matching source, so it reports that gap instead of inventing a rule.”

## Slide 8 · The agent instruction

“Every result comes with an action. When the rules support an answer, the agent proceeds and cites them. When evidence is missing or rules conflict, it asks a person. When no source answers the question, it says so. LORE Lite makes project guidance usable while keeping its evidence visible.”

## Delivery notes

- Keep the deck on screen and use the slide text as visual evidence. No app, terminal, or live model call is required.
- Pause briefly on slides 5–7 so judges can read the source names and outcomes.
- The demo examples come from the project files in `demo/`. The deck uses the authority ranks configured in `lore.config.yaml`.
