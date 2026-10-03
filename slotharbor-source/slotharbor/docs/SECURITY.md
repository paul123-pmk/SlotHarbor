# Security boundary and review notes

## Intended use

This release targets one trusted team and a small local SQLite deployment. It does
not implement tenant isolation, public signup, SSO, MFA, password reset email,
field-level confidentiality or a tamper-proof external audit sink. A coordinator
can see the same team-visible reservation titles as a member.

## Implemented controls

Passwords use a random per-password salt and scrypt (N=16,384, r=8, p=1, 32-byte
output). The application never ships a default account or password. Production
password policy and resource-cost settings still need review for the deployment.

Session cookies hold an opaque random token; the database holds its SHA-256 digest,
an expiry and a separate CSRF token. Every mutation checks the synchronizer token.
Login rotates the anonymous session, logout revokes it, and account deactivation
or password recovery revokes all sessions for the account. Cookies are HttpOnly and
SameSite=Strict; Secure is enabled explicitly for HTTPS installations.

Sign-in failures are counted persistently by normalized account and source buckets.
An account is blocked after eight failures in a 15-minute window; a source after
40 failures. This can be abused to inconvenience an account, so Internet-facing
services need stronger edge protection and recovery/monitoring design.

Request bodies are bounded at 64 KiB before parsing. Unknown JSON fields are
rejected, including forged role fields on activation requests. Access is checked
again inside write transactions. CSRF tokens containing unsupported characters
fail closed, not with an internal comparison error. HTML pages require a session
before fetching private record IDs.

Jinja HTML escaping is retained. Browser headers restrict scripts, styles and
frames. The application does not render arbitrary HTML, accept uploaded files,
execute user expressions or fetch supplied external URLs. CSV exports prefix
formula-like cells. iCalendar text is escaped and folded at UTF-8 character boundaries.

## Storage and audit limitations

SQLite is not encrypted by this application. Local database/backup permissions
must be restricted by the operator. Anyone with direct write access to the database
or application directory is outside the application's security boundary. Audit
triggers reject application-level UPDATE/DELETE, but do not defend against a machine
administrator altering the file or schema.

Rows for expired sign-in sessions are cleaned when a new session is created. Login
attempt buckets are cleaned during authentication. There is no separate cleanup
worker, retention scheduler or archival facility.

## Checks still needed before a networked deployment

Review and update dependency pins, run an authenticated browser end-to-end suite
on the target host, run a vulnerability audit and scan the complete Git history
with an established secret scanner. Review proxy, TLS, host, filesystem and backup
settings. Test the recovery procedure on a spare database, not the live one.
The delivery verification report distinguishes executed checks from unexecuted ones.
