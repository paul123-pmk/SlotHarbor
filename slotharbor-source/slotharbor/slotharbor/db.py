"""Connection-per-operation SQLite storage with explicit write serialization."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from .errors import DomainError, require


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.read() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(Path(__file__).with_name("schema.sql").read_text())
            require(con.execute("SELECT version FROM meta").fetchone()[0] == 1,
                    "Unsupported database schema version.")

    @contextmanager
    def read(self):
        con = self.connect()
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def write(self):
        with self.read() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.commit()
            except sqlite3.OperationalError as exc:
                con.rollback()
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise DomainError("The workspace is busy. Retry this request.", 503, "busy") from None
                raise
            except BaseException:
                con.rollback()
                raise

    def backup(self, destination: str | Path):
        target = Path(destination).resolve()
        require(target != self.path, "A backup cannot replace the live database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting an existing backup by accident.
        with target.open("xb"):
            pass
        try:
            with self.read() as source:
                dest = sqlite3.connect(target)
                try:
                    source.backup(dest)
                    require(dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                            "Backup integrity verification failed.")
                finally:
                    dest.close()
        except BaseException:
            target.unlink(missing_ok=True)
            raise


def audit(con, actor, action: str, entity: str, entity_id: int, now: int, **detail):
    con.execute("INSERT INTO audit(actor_id,action,entity_type,entity_id,detail,happened_at) VALUES(?,?,?,?,?,?)",
                (actor, action, entity, entity_id, json.dumps(detail, sort_keys=True), now))


def get_row(con, table: str, identifier: int):
    require(table in {"users", "resources", "bookings", "blocks"}, "Unknown entity.")
    row = con.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    require(row is not None, "That record does not exist.", 404, "not_found")
    return dict(row)


def actor_row(con, identifier: int, roles=None):
    row = get_row(con, "users", identifier)
    require(bool(row["active"]), "This account is disabled.", 403, "forbidden")
    if roles is not None:
        require(row["role"] in roles, "Your role cannot perform this action.", 403, "forbidden")
    return row
