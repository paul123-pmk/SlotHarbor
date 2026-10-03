# Engineering decisions

## SQLite with explicit write transactions
The important failure is two request handlers both seeing a free interval. Reading
and inserting inside BEGIN IMMEDIATE serializes those decisions. This favors clear
correctness over high write throughput. The application is not intended for a busy
multi-region scheduling service.

## Trailing buffers, not symmetric buffers
A booking holds `[start, end + cleanup)`; another can begin exactly when cleanup
ends. The cleanup value is captured on each booking. This keeps overlap tests and
old reservations understandable even if a later release adds editable policies.
Maintenance has no extra trailing buffer.

## Local recurring dates, stored UTC instants
People mean “09:00 each Monday”, not “every 604,800 UTC seconds”. Each occurrence is
resolved independently in the resource's timezone, then stored as UTC epoch seconds.
A clock gap invalidates the whole request. A repeated clock time requires an explicit
choice. UTC ordering and local labels are intentionally separate concerns.

## Occurrence-level review
Series creation is atomic, but later review/cancellation is per occurrence. A whole
series status button would need explicit handling of already-started, already-reviewed
and independently-cancelled dates. That workflow is not silently approximated here.

## Fixed resource policies
Changing hours, timezones or buffer policy while reservations exist raises questions
about retrospective interpretation. This version only permits activation changes.
A replacement resource is explicit; an unreviewed implicit migration is not.

## Small client, no build tool
The HTML pages are usable for reading without JavaScript; mutations use a small
same-origin JSON form client. Form values are converted to typed JSON explicitly.
There are no external fonts, analytics beacons, CDN scripts or client-side secrets.
Interactive forms require JavaScript. This is documented rather than hidden behind
a nonfunctional no-JavaScript fallback.
