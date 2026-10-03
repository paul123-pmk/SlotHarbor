PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (version INTEGER NOT NULL);
INSERT INTO meta SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM meta);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','coordinator','member')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), csrf TEXT NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS attempts (
 bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS resources (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
 timezone TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>0),
 opens TEXT NOT NULL, closes TEXT NOT NULL, weekdays TEXT NOT NULL,
 buffer_minutes INTEGER NOT NULL CHECK(buffer_minutes BETWEEN 0 AND 120),
 requires_approval INTEGER NOT NULL CHECK(requires_approval IN (0,1)),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
 id INTEGER PRIMARY KEY, series_id TEXT NOT NULL, resource_id INTEGER NOT NULL REFERENCES resources(id),
 user_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 start_at INTEGER NOT NULL, end_at INTEGER NOT NULL CHECK(end_at>start_at),
 buffer_minutes INTEGER NOT NULL CHECK(buffer_minutes BETWEEN 0 AND 120),
 attendees INTEGER NOT NULL CHECK(attendees>0),
 status TEXT NOT NULL CHECK(status IN ('pending','confirmed','cancelled','rejected')),
 version INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS bookings_window ON bookings(resource_id, status, start_at, end_at);
CREATE INDEX IF NOT EXISTS bookings_series ON bookings(series_id);
CREATE TABLE IF NOT EXISTS idempotency (
 user_id INTEGER NOT NULL REFERENCES users(id), key TEXT NOT NULL,
 payload_hash TEXT NOT NULL, booking_ids TEXT NOT NULL, PRIMARY KEY(user_id,key)
);
CREATE TABLE IF NOT EXISTS blocks (
 id INTEGER PRIMARY KEY, resource_id INTEGER NOT NULL REFERENCES resources(id),
 start_at INTEGER NOT NULL, end_at INTEGER NOT NULL CHECK(end_at>start_at), reason TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_by INTEGER NOT NULL REFERENCES users(id),
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS blocks_window ON blocks(resource_id,active,start_at,end_at);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, detail TEXT NOT NULL, happened_at INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
 BEGIN SELECT RAISE(ABORT,'Audit records cannot be edited'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
 BEGIN SELECT RAISE(ABORT,'Audit records cannot be deleted'); END;
