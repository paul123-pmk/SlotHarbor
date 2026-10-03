# Technical references

These are dependency/protocol references, not sources of copied application code.

- Python zoneinfo and the `fold` distinction: https://docs.python.org/3/library/zoneinfo.html
- SQLite transactions, including BEGIN IMMEDIATE: https://www.sqlite.org/lang_transaction.html
- SQLite online backup interface: https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup
- FastAPI templates: https://fastapi.tiangolo.com/advanced/templates/
- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/
- Browser security considerations: https://flask.palletsprojects.com/en/stable/web-security/
- iCalendar protocol (RFC 5545): https://www.rfc-editor.org/rfc/rfc5545
- Whole-history secret scanning: https://github.com/gitleaks/gitleaks

Runtime dependencies are installed separately, not vendored into the repository.
Their source code and lock metadata are not counted as first-party implementation.
