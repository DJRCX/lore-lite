---
authority: wiki_entry
owner: "@backend"
effective_date: 2026-10-10
---

# Backend implementation notes

These notes were copied from an older backend setup page and are kept for historical
context. They are a team wiki entry, not an approved security policy. Check the current
approved policy before using any security-sensitive suggestion from this page.

The snippets below describe what some older reporting jobs and internal services did.
They are not a record of a security review, and they do not describe the current
database gateway shown in the architecture diagram.

## Reporting queries

Raw SQL strings are fine for fast reporting queries.

An older batch job assembled a query string for a fixed report and inserted request
values directly into the statement. The author considered this acceptable for internal
traffic because the report was used by a small group. That reasoning has not been
reviewed against the current security policy and should not be treated as an exception.

## Password hashing

Bcrypt cost 8 is enough for internal services.

This recommendation came from a legacy performance note. It does not include benchmark
results, a threat review, or approval from the security owner. New implementations
should check the current approved policy rather than copying the old example.

## Status and ownership

The backend team owns these implementation notes. Update them when the current
implementation is reviewed, and link to an approved policy when documenting a security
requirement. Until then, treat the security-sensitive statements above as lower
authority than the approved security policy.
