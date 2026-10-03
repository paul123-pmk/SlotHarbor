"""Password authentication, revocable opaque sessions and login throttling."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from .db import actor_row, audit, get_row
from .errors import DomainError, require
from .validation import text


def password_hash(password: str) -> str:
    require(isinstance(password, str) and 12 <= len(password) <= 256,
            "Use a password between 12 and 256 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row):
    return {k:row[k] for k in ("id", "username", "role", "active", "created_at")}


class Accounts:
    def __init__(self, db, clock=None):
        self.db = db
        self.clock = clock or (lambda: int(time.time()))
        self.dummy_hash = password_hash(secrets.token_urlsafe(24))

    def create_user(self, username: str, password: str, role: str = "member", actor=None):
        username = text(username, "Username", 3, 40).lower()
        require(re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", username) is not None,
                "Username may contain letters, numbers, dots, underscores and hyphens.")
        require(role in ("admin", "coordinator", "member"), "Choose a valid role.")
        encoded = password_hash(password)
        with self.db.write() as con:
            exists = con.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            if exists:
                require(actor is not None, "An administrator is required.", 403)
                actor_row(con, actor, {"admin"})
            else:
                require(role == "admin", "The first account must be an administrator.")
            try:
                cursor = con.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                                     (username, encoded, role, self.clock()))
            except sqlite3.IntegrityError:
                raise DomainError("That username is already taken.", 409, "duplicate") from None
            audit(con, actor, "user.created", "user", cursor.lastrowid, self.clock(), role=role)
            return public_user(get_row(con, "users", cursor.lastrowid))

    def list(self):
        with self.db.read() as con:
            return [public_user(dict(r)) for r in con.execute("SELECT * FROM users ORDER BY username")]

    def set_active(self, actor: int, user_id: int, active: bool):
        require(type(active) is bool, "active must be true or false.")
        with self.db.write() as con:
            actor_row(con, actor, {"admin"})
            target = get_row(con, "users", user_id)
            if target["role"] == "admin" and not active:
                count = con.execute("SELECT count(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0]
                require(not target["active"] or count > 1, "The last active administrator cannot be disabled.", 409)
            con.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))
            if not active:
                con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(con, actor, "user.activation", "user", user_id, self.clock(), active=active)
            return public_user(get_row(con, "users", user_id))

    def reset_password_local(self, username: str, password: str):
        """OS-level recovery command, deliberately not exposed as an HTTP endpoint."""
        encoded = password_hash(password)
        with self.db.write() as con:
            row = con.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            require(row is not None, "Unknown username.", 404)
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, row[0]))
            con.execute("DELETE FROM sessions WHERE user_id=?", (row[0],))
            audit(con, None, "user.local_password_reset", "user", row[0], self.clock())

    def new_session(self, user_id=None):
        raw = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self.db.write() as con:
            if user_id is not None:
                actor_row(con, user_id)
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (self.clock(),))
            con.execute("INSERT INTO sessions VALUES(?,?,?,?)",
                        (token_hash(raw), user_id, csrf, self.clock() + (28800 if user_id else 900)))
        return raw, csrf

    def session(self, raw: str | None):
        if not raw or len(raw) > 128:
            return None
        with self.db.read() as con:
            row = con.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",
                              (token_hash(raw), self.clock())).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["user"] = None
            if row["user_id"] is not None:
                user = get_row(con, "users", row["user_id"])
                if not user["active"]:
                    return None
                result["user"] = public_user(user)
            return result

    def revoke(self, raw: str):
        with self.db.write() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(raw),))

    def login(self, username: str, password: str, client: str = "local"):
        require(isinstance(username, str) and len(username) <= 80, "Invalid sign-in details.", 401)
        normalized = username.strip().lower()
        # Both an account bucket and a source bucket apply; varying one cannot bypass the other.
        buckets = [(token_hash("account:" + normalized), 8), (token_hash("source:" + client), 40)]
        now = self.clock()
        error = None
        user = None
        with self.db.write() as con:
            con.execute("DELETE FROM attempts WHERE window_start<=?", (now-900,))
            for bucket, limit in buckets:
                row = con.execute("SELECT failures FROM attempts WHERE bucket=?", (bucket,)).fetchone()
                if row and row[0] >= limit:
                    error = DomainError("Too many sign-in attempts. Retry after the 15-minute window.", 429, "rate_limited")
            if error is None:
                row = con.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (normalized,)).fetchone()
                valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
                if row is None or not valid or not row["active"]:
                    for bucket, _ in buckets:
                        con.execute("INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET failures=failures+1",
                                    (bucket, now))
                    error = DomainError("The username or password is incorrect.", 401, "bad_login")
                else:
                    con.execute("DELETE FROM attempts WHERE bucket=?", (buckets[0][0],))
                    user = public_user(dict(row))
                    audit(con, user["id"], "user.login", "user", user["id"], now)
        # Failed-attempt counters must commit before the error is raised.
        if error:
            raise error
        raw, csrf = self.new_session(user["id"])
        return raw, csrf, user
