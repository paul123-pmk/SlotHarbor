# SlotHarbor design

## Purpose
A small studio, workshop or research team needs to reserve shared resources without
colliding with another booking or a maintenance window. This is a new standalone
application, not a stock ledger. Accounts belong to one workspace.

## Scope and architecture
Python 3.11+, FastAPI, SQLite and server-rendered Jinja pages with a small JavaScript
form client. Resources have their own IANA timezone, opening window, weekdays,
capacity, approval policy and trailing cleanup buffer. No payment, email, external
calendar sync, multi-tenant hosting or public registration is included.

`db.py` owns connections and schema; `accounts.py` owns credentials and sessions;
`catalog.py` owns resources; `planning.py` owns reservations and maintenance;
`times.py` owns local-to-UTC conversion; `exports.py` owns CSV and iCalendar;
`web.py` connects HTTP to these services; `cli.py` owns local administration.

## Invariants
Booking and maintenance conflict detection and insertion happen in a single
BEGIN IMMEDIATE transaction. All intervals are half-open. A booking occupies its
start through its end plus the resource's trailing buffer, captured at creation.
Pending reservations hold their slots. Cancelled or rejected reservations do not.
Resources are indivisible, not pooled seats; capacity is a party-size limit.

Recurring bookings use local wall-clock dates, not fixed UTC week lengths. A series
contains 1–26 occurrences, spaced by one or seven days. The entire series succeeds
or none of it does. Missing local times are rejected. Repeated local times require
an explicit fold, independently for start and end. A reservation must fit within
one local date and that resource's opening hours, with a maximum 12-hour duration.
Maintenance may span days, up to 30 days, and may not overlap held reservations.

All reservation-creation requests use a user-scoped idempotency key. Reusing a key for a different
normalized request is a conflict; exact replay returns the original rows, even
after cancellation. Individual status changes use expected_version to reject stale
forms. Coordinator approval is mandatory where the resource requires it, including
for an administrator's own request. Confirmation of a past reservation is rejected.

Members can book, inspect the team's calendar, and cancel their own reservations.
Coordinators also manage resources, blocks and approvals. Administrators additionally
manage accounts. The last active administrator cannot be disabled. Deactivation
revokes sessions immediately. Titles are team-visible; do not enter confidential
personal details. Credentials, local databases and backups are never tracked.

## Operational choices
Use opaque random server-side sessions, hashed at rest; synchronizer CSRF tokens;
constant-time password verification; database-backed login throttling; strict host
validation; bounded JSON requests; HTML escaping and restrictive browser headers.
Listen on loopback by default. HTTPS, backups and dependency review are prerequisites
for any deployment beyond a trusted local environment.

## Success criteria
Exercise overlap boundaries, concurrent requests, rollback, idempotency, DST gaps
and folds, recurrence, permission checks, session revocation, exports and browser
flows. Verify a fresh clone of the actual Git bundle. Report measured test and size
results without inventing historical commits, reviewers, users or deployments.
