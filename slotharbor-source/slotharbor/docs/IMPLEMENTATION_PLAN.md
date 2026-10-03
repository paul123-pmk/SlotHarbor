# SlotHarbor implementation plan

Goal: deliver a functional shared-resource scheduling application.
Spec: DESIGN.md. Execution: native, in this isolated new repository.

1. Time and persistence contracts. Write failing tests for UTC conversion,
   missing/repeated times, schema integrity and transaction rollback. Implement
   `Database(path)`, `local_epoch(value, zone, fold=None)` and validation helpers.
2. Booking domain. Write failing tests for roles, capacity, hours, cleanup buffers,
   recurrence rollback, maintenance and concurrent booking. Implement resource and
   planning services; test before recording the implementation checkpoint.
3. Identity and HTTP. Test account creation, password verification, login throttling,
   CSRF, revocation, stale updates, request limits and ownership. Implement opaque
   sessions and HTTP adapters, then run the whole suite.
4. Interface, exports and operations. Build the agenda, resource directory, request
   form, approvals, maintenance, reports and team controls. Add safe CSV/iCalendar
   export, backup/restore documentation, CLI and CI. Test the real browser workflow.
5. Delivery. Review source; run the complete suite with coverage; build a wheel;
   create and verify a Git bundle; clone it and rerun tests. Record any checks the
   execution environment prevented. No hosted repository is created or published.

Review focus: half-open boundary treatment; DST ambiguity; partial series failures;
unauthorized object IDs; stale reservation state. Each belongs to an explicit test.
