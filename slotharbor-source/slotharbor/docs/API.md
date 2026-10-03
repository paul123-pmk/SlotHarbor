# Same-origin JSON API

The browser is one client of the same services used by the CLI. JSON request bodies
are limited to 64 KiB. Unknown fields fail validation. Signed-in API schema JSON is
available at `GET /api/schema`; interactive documentation is not loaded from a CDN.

## Session exchange

1. GET `/login` creates an anonymous session cookie and embeds its synchronizer
   token in `<meta name="csrf-token">`.
2. POST JSON to `/api/auth/login` with `username`, `password` and the token in the
   `X-CSRF-Token` header. The browser must send the session cookie too.
3. A successful login replaces the anonymous session. The JSON response includes
   the new `csrf` value, a public user object and `redirect`.
4. All subsequent POST requests require the authenticated cookie and matching
   header. `GET /api/me` returns the current public user and CSRF token.
5. POST `/api/auth/logout` revokes the current server-side session.

The cookie is named `slotharbor_session`. Its raw random value is never stored in
the database; only a SHA-256 digest is stored. Sessions expire after eight hours.
Anonymous sign-in sessions expire after 15 minutes.

## Resource routes

| Method and route | Fields / result |
|---|---|
| GET `/api/resources` | Resource list, including paused resources |
| POST `/api/resources` | `name`, `code`, `timezone`, `capacity`, `opens`, `closes`, `weekdays`, `buffer_minutes`, `requires_approval` |
| POST `/api/resources/{id}/activation` | `active`: JSON boolean |

Resource creation and activation require coordinator or administrator access.
Weekdays use Monday=0 through Sunday=6. Timezone must be a valid IANA name. Capacity
is 1–1,000; trailing cleanup is 0–120 minutes. Time fields use `HH:MM`. A closing
time must be later than the opening time on the same date. Defaults are documented
in `models.py` and the authenticated schema.

## Reservation routes

| Method and route | Fields / result |
|---|---|
| GET `/api/reservations` | Optional `status`, `resource_id`, `offset`; returns up to 100 rows |
| POST `/api/reservations` | Reservation request, described below |
| POST `/api/reservations/{id}/transition` | `action`: `approve`, `reject` or `cancel`; `expected_version`: integer |

A create request uses this shape; use your own resource ID and future dates:

```json
{
  "resource_id": 1,
  "title": "Weekly workshop planning",
  "starts": "2030-01-07T09:00",
  "ends": "2030-01-07T10:00",
  "attendees": 3,
  "count": 4,
  "interval_days": 7,
  "key": "a-unique-client-request-key",
  "start_fold": null,
  "end_fold": null
}
```

Times are interpreted in the selected resource's timezone, not the browser's.
`count` is 1–26 and `interval_days` is 1 or 7. For repeated local clock times, fold
0 means first occurrence and 1 means second. Missing local times are never silently
shifted. A request that contains any invalid or conflicting occurrence inserts none.

A key is 8–80 ASCII letters, digits, underscores or hyphens, scoped to the requester.
An exact normalized replay returns the original rows even after cancellation.
Reusing the key with different details returns 409. The application keeps a key
across a failed network attempt, so a retry cannot duplicate a successful insert.

Approval and rejection apply only to pending occurrences and require a coordinator
or administrator. Cancellation is available to the owner or a coordinator/admin.
A mismatched version returns 409. Pending requests hold their slots. Requests whose
start has passed cannot be approved. No automatic pending-expiry job is included.

## Maintenance and team administration

POST `/api/maintenance` accepts `resource_id`, `starts`, `ends`, `reason`, plus
optional `start_fold` and `end_fold`. A coordinator/admin can create a window up to
30 elapsed days and release it with POST `/api/maintenance/{id}/release` and `{}`.
Maintenance must begin in the future and cannot overlap held reservations or
another active maintenance window.

POST `/api/users` accepts `username`, `password`, and `role`. POST
`/api/users/{id}/activation` accepts `active`. Both require an administrator.
Deactivation revokes every current session. The last active admin is protected.
Password recovery is deliberately a local CLI command, not a web endpoint.

## Exports and errors

GET `/exports/reservations.csv` and `/exports/calendar.ics` require authentication.
They return up to 5,000 rows starting at the requested `offset`, default 0. Responses
include `X-Export-Limit: 5000`. Export pages are separate snapshots: do not assume
stable pagination if colleagues edit bookings between downloads. For a fixed
large dataset, use an offline backup before exporting each page.

Domain errors contain `error` and `code`. Validation errors also include a `fields`
array; submitted passwords and full request bodies are not echoed. Statuses are
400 for invalid domain inputs, 401 for sign-in required/failed, 403 for denied
permissions or CSRF, 404 for missing records, 409 for conflicts/stale state, 413 for
oversized requests, 422 for JSON-shape errors, 429 for throttling and 503 for a busy
database. Clients should not blindly retry validation or permission failures.
