---
authority: approved_policy
owner: "@security"
effective_date: 2026-10-18
---

# Security and data handling policy

This policy is maintained by the security team and applies to production services that
store passwords, query customer records, or send customer data to an outside provider.
It is the authoritative source for these controls. A service owner should use the
requirements below during design, implementation, review, and release.

## How to use this policy

For each affected change, identify the system and data involved, follow the requirement
for that area, and retain the supporting evidence named below. If another document gives
a different instruction, the approved security policy takes precedence. If required
evidence is missing, pause the approval request until it is attached.

## Password hashing

All user passwords MUST be hashed with bcrypt using cost factor 12 or higher.

The password must never be stored or logged in readable form. Apply the configured
bcrypt work factor when a new password is created, and verify sign-in attempts against
the stored hash using the password library's verification function. Do not lower the
work factor simply to make tests or local development faster; use test-only accounts
and test configuration instead.

## Reporting queries

Reporting queries MUST use parameterized statements, never raw SQL strings.

Bind user-provided values separately from the SQL statement. For example, a query may
use `WHERE customer_id = ?` and pass the customer ID as a bound value. Do not build a
query by concatenating request text into the SQL string. The architecture diagram
`architecture.png` shows the approved path through the database gateway and the
unsafe pattern that must be avoided.

The database gateway validates request fields, selects the intended query, binds the
values, and sends the prepared statement to the database. Database errors should be
handled by the service and should not expose query internals or customer data to the
requester.

## Third-party vendors

Before sensitive customer data is processed by a third-party vendor, an assessment and proof of data residency MUST be recorded.

The requirement applies before a production integration is enabled, including pilots
that use real or copied customer data. Review the data categories, processing purpose,
retention, access controls, and the vendor's storage and processing locations. A sales
statement or an informal approval note is not a substitute for the required records.

## Evidence records

The vendor approval record MUST include an `assessment_report` and a `data_residency_proof`.

Attach both records to the vendor approval request and keep them available for later
review. The assessment report records the security review and its outcome. The data
residency proof identifies the regions in which the vendor will store or process the
covered data. If either item is absent or still pending, the request is not ready for
approval.

## Review checklist

- Confirm the service and data category affected by the change.
- Confirm password storage uses bcrypt at the required work factor.
- Confirm reporting values are bound as parameters, not concatenated into SQL.
- Confirm both vendor evidence records are attached before sensitive data is sent.
- Record the source policy and implementation evidence in the change review.
