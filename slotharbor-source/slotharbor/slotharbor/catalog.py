"""Shared resources and their fixed scheduling policies."""
import json
import re
import sqlite3
import time
from .db import actor_row, audit, get_row
from .errors import DomainError, require
from .times import zone
from .validation import text, integer, boolean


def resource_dict(row):
    result = dict(row)
    result["weekdays"] = json.loads(result["weekdays"])
    result["requires_approval"] = bool(result["requires_approval"])
    result["active"] = bool(result["active"])
    return result


class Catalog:
    def __init__(self, db, clock=None):
        self.db = db
        self.clock = clock or (lambda: int(time.time()))

    def create(self, actor, *, name, code, timezone="Africa/Nairobi", capacity=1,
               opens="07:00", closes="21:00", weekdays=None, buffer_minutes=0, requires_approval=False):
        name = text(name, "Resource name", maximum=100)
        code = text(code, "Resource code", maximum=20).upper()
        require(re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", code) is not None, "Use letters, numbers and hyphens for the code.")
        zone(timezone)
        capacity = integer(capacity, "Capacity", 1, 1000)
        buffer_minutes = integer(buffer_minutes, "Cleanup minutes", 0, 120)
        requires_approval = boolean(requires_approval, "Approval setting")
        for value in (opens, closes):
            require(isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is not None,
                    "Opening and closing times must use HH:MM.")
        require(opens < closes, "Closing time must be after opening time on the same day.")
        weekdays = list(range(7)) if weekdays is None else weekdays
        require(isinstance(weekdays, list) and 1 <= len(weekdays) <= 7 and
                all(type(v) is int and 0 <= v <= 6 for v in weekdays) and len(set(weekdays)) == len(weekdays),
                "Choose unique weekdays from 0 (Monday) to 6 (Sunday).")
        with self.db.write() as con:
            actor_row(con, actor, {"admin", "coordinator"})
            try:
                cur = con.execute("""INSERT INTO resources(name,code,timezone,capacity,opens,closes,weekdays,
                    buffer_minutes,requires_approval,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (name,code,timezone,capacity,opens,closes,json.dumps(sorted(weekdays)),buffer_minutes,
                     int(requires_approval),self.clock()))
            except sqlite3.IntegrityError:
                raise DomainError("That resource code already exists.", 409, "duplicate") from None
            audit(con, actor, "resource.created", "resource", cur.lastrowid, self.clock())
            return resource_dict(get_row(con, "resources", cur.lastrowid))

    def get(self, identifier):
        with self.db.read() as con:
            return resource_dict(get_row(con, "resources", identifier))

    def list(self):
        with self.db.read() as con:
            return [resource_dict(r) for r in con.execute("SELECT * FROM resources ORDER BY name,id")]

    def set_active(self, actor, identifier, active):
        boolean(active, "active")
        with self.db.write() as con:
            actor_row(con, actor, {"admin", "coordinator"})
            get_row(con, "resources", identifier)
            con.execute("UPDATE resources SET active=? WHERE id=?", (int(active),identifier))
            audit(con, actor, "resource.activation", "resource", identifier, self.clock(), active=active)
            return resource_dict(get_row(con, "resources", identifier))
