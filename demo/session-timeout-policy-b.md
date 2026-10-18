---
authority: approved_policy
owner: "@security"
---

# Session timeout

This approved security policy applies to signed-in users of the production web
application. An inactivity period begins after the user's last meaningful interaction
with the application; a background tab by itself does not refresh the session.

User sessions MUST expire after 30 minutes of inactivity.

When the inactivity limit is reached, the server should invalidate the session and
require the user to authenticate again before accessing protected pages. This policy
fixture intentionally has no effective date so that an equal-authority disagreement
cannot be resolved by recency alone.
