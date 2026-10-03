# SlotHarbor

**Shared resources. One clear schedule.**

SlotHarbor gives a small studio, workshop or research team a private place to
reserve rooms and equipment, review requests, and plan downtime. It runs locally
with Python and SQLite. There is no external account, hosted service, payment
integration or JavaScript build step.

## What works

The resource directory defines local opening hours, weekdays, capacity, approval
requirements and cleanup time. Reservations check those policies and reject
collisions with existing sessions or maintenance. Pending requests hold their
slots until a coordinator approves, rejects or cancels them.

Daily and weekly recurring reservations keep the same **local wall-clock time**
across clock changes. A request creates every occurrence or none. Nonexistent
local times are rejected; ambiguous times require a first/second occurrence choice.
A duplicated network request returns its original reservation rather than booking
twice. Stale status-change forms are rejected instead of overwriting a newer decision.

Members book and cancel their own occurrences. Coordinators also maintain the
resource directory and review requests. Administrators manage accounts. Account
deactivation and local password recovery revoke existing sessions.

The workspace includes a seven-day overview, a reservation register, per-resource
demand summaries, an activity log, CSV exports and iCalendar files. Titles and
usernames are visible to the signed-in team. Do not enter confidential personal
information in a reservation purpose.

## Start on Windows

Use Python 3.11 or newer. These commands use the virtual environment's executable
directly; PowerShell execution-policy changes are not needed.

```powershell
# In the folder containing slotharbor.bundle:
git clone .\slotharbor.bundle slotharbor
cd slotharbor

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\python.exe -m slotharbor init
.\.venv\Scripts\python.exe -m slotharbor create-user --username owner --role admin
.\.venv\Scripts\python.exe -m slotharbor serve
```

The account command prompts twice for a password of at least 12 characters. There
is no built-in password. Open `http://127.0.0.1:8000` and sign in. The source ZIP can
also be extracted and run from its project directory; that ZIP does not contain
Git history.

For a demonstration workspace, run this before adding resources yourself:

```powershell
.\.venv\Scripts\python.exe -m slotharbor demo --actor owner
```

It adds four fictional resources, seven example reservations and one maintenance
window, dated relative to execution. It does not create additional accounts and
will refuse to seed a nonempty resource directory.

## Start on macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m slotharbor init
.venv/bin/python -m slotharbor create-user --username owner --role admin
.venv/bin/python -m slotharbor serve
```

## A first end-to-end check

Open Resources and create a resource with a 15-minute cleanup buffer. Make a
09:00–10:00 reservation on a future open day. A second reservation starting at
10:00 is rejected; one starting at 10:15 fits. Cancel the first occurrence and
check that the time is free again.

Create a second resource that requires approval. Its reservations appear as
pending even when requested by an administrator. Open Approvals, review one,
and confirm it. Maintenance cannot displace the confirmed interval or its cleanup.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest --cov=slotharbor --cov-report=term-missing
```

Tests use temporary SQLite databases and fictional accounts. They do not connect
to external services. The CI configuration exercises Python 3.11 and 3.13 on
Windows and Ubuntu; a configured job is not evidence that the hosted job has run.

## Project map

| Area | Responsibility |
|---|---|
| `slotharbor/accounts.py` | Password hashing, sessions, login throttling, account administration |
| `slotharbor/catalog.py` | Resource scheduling policies and activation |
| `slotharbor/planning.py` | Booking conflicts, recurrence, lifecycle, maintenance, reporting |
| `slotharbor/times.py` | Timezone conversion and clock-change validation |
| `slotharbor/db.py`, `schema.sql` | Transactions, persistence, audit records, backups |
| `slotharbor/web.py`, `models.py` | HTML routes, typed JSON inputs and access checks |
| `slotharbor/middleware.py` | Body-size boundary and browser response headers |
| `slotharbor/exports.py` | CSV cell protection and iCalendar encoding |
| `slotharbor/templates/`, `static/` | Responsive pages and the form client |
| `slotharbor/cli.py` | Initialization, account recovery, demo data, serving and backups |
| `tests/` | Domain, concurrency, authentication, HTTP, exports and CLI checks |
| `docs/` | Design, API reference, operations, security and decisions |

## Important boundaries

This release is for a **single trusted workspace**, not public self-service hosting.
Use a proper HTTPS termination layer before exposing it outside your computer;
read `docs/SECURITY.md` first. Protect the database and backups using operating-system
permissions. No personal datasets or working credentials belong in Git.

Resources are reserved exclusively: capacity limits party size, not parallel
bookings. Resource policies are fixed after creation; pause a resource and create
a replacement when policy changes. Pausing does not cancel existing reservations.
Reservation occurrences are reviewed and cancelled individually. Maintenance
windows may span dates; ordinary reservations must fit one local opening day.

Exports return up to 5,000 rows per request, ordered by start and ID, with an
`offset` parameter for larger registers. There is no automatic external calendar
synchronization. All installed dependency versions should be reviewed before a
networked deployment. No independent security certification is implied.
