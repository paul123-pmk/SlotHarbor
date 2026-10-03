"""Atomic reservation and maintenance transitions; one resource per interval."""
import hashlib
import json
import re
import time
import uuid
from .catalog import resource_dict
from .db import actor_row, audit, get_row
from .errors import require
from .times import local_datetime, local_epoch, shifted
from .validation import integer, text


BOOKING_SELECT = """SELECT b.*, r.name AS resource_name, r.code AS resource_code,
    r.timezone, u.username FROM bookings b JOIN resources r ON r.id=b.resource_id
    JOIN users u ON u.id=b.user_id"""


def booking_row(con, identifier):
    row = con.execute(BOOKING_SELECT + " WHERE b.id=?", (identifier,)).fetchone()
    require(row is not None, "That reservation does not exist.", 404, "not_found")
    return dict(row)


def assert_available(con, resource_id, start, occupied_end):
    overlap = con.execute("""SELECT id FROM bookings WHERE resource_id=?
        AND status IN ('pending','confirmed') AND start_at<? AND end_at+buffer_minutes*60>?
        LIMIT 1""", (resource_id, occupied_end, start)).fetchone()
    require(overlap is None, "This interval overlaps a reservation or its cleanup time.", 409, "overlap")
    blocked = con.execute("""SELECT id FROM blocks WHERE resource_id=? AND active=1
        AND start_at<? AND end_at>? LIMIT 1""", (resource_id, occupied_end, start)).fetchone()
    require(blocked is None, "This interval overlaps a maintenance block.", 409, "maintenance")


class Planner:
    def __init__(self, db, clock=None):
        self.db = db
        self.clock = clock or (lambda: int(time.time()))

    def reserve(self, actor, *, resource_id, title, starts, ends, attendees=1, count=1,
                interval_days=7, key, start_fold=None, end_fold=None):
        resource_id = integer(resource_id, "Resource", 1, 2**31-1)
        title = text(title, "Purpose", 1, 160)
        attendees = integer(attendees, "Party size", 1, 1000)
        count = integer(count, "Occurrences", 1, 26)
        interval_days = integer(interval_days, "Repeat interval", 1, 7)
        require(interval_days in (1, 7), "Repeat daily or weekly.")
        key = text(key, "Request key", 8, 80)
        require(re.fullmatch(r"[A-Za-z0-9_-]+", key) is not None, "Invalid request key.")
        # Shape validation runs even on retries, but resource/time policy does not.
        local_datetime(starts)
        local_datetime(ends)
        for fold in (start_fold, end_fold):
            require(fold is None or (type(fold) is int and fold in (0,1)), "fold must be 0 or 1.")
        payload = dict(resource_id=resource_id, title=title, starts=starts, ends=ends,
                       attendees=attendees, count=count, interval_days=interval_days,
                       start_fold=start_fold, end_fold=end_fold)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.db.write() as con:
            actor_row(con, actor)
            replay = con.execute("SELECT * FROM idempotency WHERE user_id=? AND key=?", (actor,key)).fetchone()
            if replay:
                require(replay["payload_hash"] == digest, "This request key was already used for different details.",
                        409, "idempotency_conflict")
                return [booking_row(con, bid) for bid in json.loads(replay["booking_ids"])]
            resource = resource_dict(get_row(con, "resources", resource_id))
            require(resource["active"], "This resource is paused.", 409, "inactive")
            require(attendees <= resource["capacity"], "The party size exceeds this resource's capacity.")
            status = "pending" if resource["requires_approval"] else "confirmed"
            series = str(uuid.uuid4())
            ids = []
            for occurrence in range(count):
                local_start = shifted(starts, occurrence*interval_days)
                local_end = shifted(ends, occurrence*interval_days)
                begin = local_datetime(local_start)
                finish = local_datetime(local_end)
                require(begin.date() == finish.date(), "Each reservation must end on its starting local date.")
                require(begin.weekday() in resource["weekdays"], "The resource is closed on one of these weekdays.")
                require(resource["opens"] <= begin.strftime("%H:%M") and finish.strftime("%H:%M") <= resource["closes"],
                        "The reservation falls outside this resource's opening hours.")
                start = local_epoch(local_start, resource["timezone"], start_fold)
                end = local_epoch(local_end, resource["timezone"], end_fold)
                require(start > self.clock(), "Reservations must start in the future.")
                require(0 < end-start <= 43200, "A reservation must last more than zero and no more than 12 hours.")
                assert_available(con, resource_id, start, end+resource["buffer_minutes"]*60)
                cur = con.execute("""INSERT INTO bookings(series_id,resource_id,user_id,title,start_at,end_at,
                    buffer_minutes,attendees,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (series,resource_id,actor,title,start,end,resource["buffer_minutes"],attendees,status,self.clock(),self.clock()))
                ids.append(cur.lastrowid)
                audit(con, actor, "booking.created", "booking", cur.lastrowid, self.clock(), status=status)
            con.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (actor,key,digest,json.dumps(ids)))
            return [booking_row(con, bid) for bid in ids]

    def get(self, identifier):
        with self.db.read() as con:
            return booking_row(con, identifier)

    def list(self, *, start=None, end=None, status=None, resource_id=None, user_id=None, limit=1000, offset=0, active_only=False):
        limit = integer(limit, "Limit", 1, 5000)
        offset = integer(offset, "Offset", 0, 1000000)
        conditions, values = [], []
        if active_only:
            conditions.append("b.status IN ('pending','confirmed')")
        if start is not None:
            conditions.append("b.end_at>?")
            values.append(start)
        if end is not None:
            conditions.append("b.start_at<?")
            values.append(end)
        if status:
            require(status in {"pending","confirmed","cancelled","rejected"}, "Unknown reservation status.")
            conditions.append("b.status=?")
            values.append(status)
        if resource_id is not None:
            conditions.append("b.resource_id=?")
            values.append(integer(resource_id, "Resource", 1, 2**31-1))
        if user_id is not None:
            conditions.append("b.user_id=?")
            values.append(user_id)
        sql = BOOKING_SELECT + (" WHERE " + " AND ".join(conditions) if conditions else "")
        with self.db.read() as con:
            return [dict(r) for r in con.execute(sql+" ORDER BY b.start_at,b.id LIMIT ? OFFSET ?", [*values,limit,offset])]

    def transition(self, actor, identifier, action, expected_version):
        require(action in {"cancel", "approve", "reject"}, "Unknown reservation action.")
        expected_version = integer(expected_version, "Version", 1, 2**31-1)
        with self.db.write() as con:
            user = actor_row(con, actor)
            booking = get_row(con, "bookings", identifier)
            manager = user["role"] in {"admin", "coordinator"}
            require(manager or (action == "cancel" and booking["user_id"] == actor),
                    "You cannot change this reservation.", 403, "forbidden")
            require(booking["version"] == expected_version, "This reservation changed. Reload before trying again.", 409, "stale")
            if action in {"approve", "reject"}:
                require(booking["status"] == "pending", "Only pending reservations can be reviewed.", 409, "state")
            else:
                require(booking["status"] in {"pending", "confirmed"}, "This reservation is already closed.", 409, "state")
            if action == "approve":
                require(booking["start_at"] > self.clock(), "A reservation that has already started cannot be approved.", 409)
                require(get_row(con, "resources", booking["resource_id"])["active"], "The resource is paused.", 409)
            status = {"cancel":"cancelled", "approve":"confirmed", "reject":"rejected"}[action]
            con.execute("UPDATE bookings SET status=?,version=version+1,updated_at=? WHERE id=?",
                        (status,self.clock(),identifier))
            audit(con, actor, "booking."+action, "booking", identifier, self.clock(), from_status=booking["status"])
            return booking_row(con, identifier)

    def block(self, actor, resource_id, starts, ends, reason, start_fold=None, end_fold=None):
        reason = text(reason, "Maintenance reason", 1, 160)
        resource_id = integer(resource_id, "Resource", 1, 2**31-1)
        with self.db.write() as con:
            actor_row(con, actor, {"admin", "coordinator"})
            resource = get_row(con, "resources", resource_id)
            start = local_epoch(starts, resource["timezone"], start_fold)
            end = local_epoch(ends, resource["timezone"], end_fold)
            require(start > self.clock(), "Maintenance must start in the future.")
            require(0 < end-start <= 30*86400, "Maintenance must last more than zero and no more than 30 days.")
            assert_available(con, resource_id, start, end)
            cur = con.execute("""INSERT INTO blocks(resource_id,start_at,end_at,reason,created_by,created_at)
                VALUES(?,?,?,?,?,?)""", (resource_id,start,end,reason,actor,self.clock()))
            audit(con, actor, "maintenance.created", "block", cur.lastrowid, self.clock())
            return get_row(con, "blocks", cur.lastrowid)

    def unblock(self, actor, identifier):
        with self.db.write() as con:
            actor_row(con, actor, {"admin", "coordinator"})
            row = get_row(con, "blocks", identifier)
            require(row["active"], "This maintenance block is already released.", 409)
            con.execute("UPDATE blocks SET active=0 WHERE id=?", (identifier,))
            audit(con, actor, "maintenance.released", "block", identifier, self.clock())
            return get_row(con, "blocks", identifier)

    def blocks(self):
        with self.db.read() as con:
            return [dict(r) for r in con.execute("""SELECT b.*,r.name AS resource_name,r.timezone
                FROM blocks b JOIN resources r ON r.id=b.resource_id ORDER BY b.start_at DESC LIMIT 1000""")]

    def summary(self, start, end):
        """Clip confirmed occupancy to a UTC window; cleanup and pending time are excluded."""
        require(type(start) is int and type(end) is int and 0 < end-start <= 366*86400,
                "Report window must be positive and no more than 366 days.")
        with self.db.read() as con:
            return [dict(r) for r in con.execute("""SELECT r.id,r.name,r.code,
                COALESCE(SUM(CASE WHEN b.status='confirmed' THEN MIN(b.end_at,?)-MAX(b.start_at,?) ELSE 0 END),0) AS booked_seconds,
                COALESCE(SUM(CASE WHEN b.status='confirmed' THEN 1 ELSE 0 END),0) AS confirmed,
                COALESCE(SUM(CASE WHEN b.status='pending' THEN 1 ELSE 0 END),0) AS pending
                FROM resources r LEFT JOIN bookings b ON b.resource_id=r.id AND b.start_at<? AND b.end_at>?
                GROUP BY r.id ORDER BY r.name""", (end,start,end,start))]

    def audit_log(self, limit=100):
        limit = integer(limit, "Limit", 1, 1000)
        with self.db.read() as con:
            return [dict(r) for r in con.execute("""SELECT a.*,u.username FROM audit a LEFT JOIN users u ON u.id=a.actor_id
                ORDER BY a.id DESC LIMIT ?""", (limit,))]
