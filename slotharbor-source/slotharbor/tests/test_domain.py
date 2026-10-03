import importlib.util
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest


def test_domain_modules_exist():
    for name in ("db", "accounts", "catalog", "planning"):
        assert importlib.util.find_spec(f"slotharbor.{name}") is not None


@pytest.fixture
def env(tmp_path):
    from slotharbor.db import Database
    from slotharbor.accounts import Accounts
    from slotharbor.catalog import Catalog
    from slotharbor.planning import Planner
    now = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp())
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    accounts = Accounts(db, lambda: now)
    admin = accounts.create_user("owner", "test-only-long-passphrase", "admin")
    member = accounts.create_user("member", "test-only-long-passphrase", "member", admin["id"])
    second = accounts.create_user("second", "test-only-long-passphrase", "member", admin["id"])
    catalog = Catalog(db, lambda: now)
    resource = catalog.create(admin["id"], name="North studio", code="NORTH", timezone="Africa/Nairobi",
                              capacity=8, opens="07:00", closes="21:00", weekdays=[0,1,2,3,4,5,6],
                              buffer_minutes=15, requires_approval=False)
    return {"db":db, "accounts":accounts, "admin":admin, "member":member, "second":second,
            "catalog":catalog, "resource":resource, "planner":Planner(db, lambda: now), "now":now}


def reserve(env, actor=None, **changes):
    payload = dict(resource_id=env["resource"]["id"], title="Workshop planning", starts="2030-01-07T09:00",
                   ends="2030-01-07T10:00", attendees=3, count=1, interval_days=7,
                   key="test-reservation-001", start_fold=None, end_fold=None)
    payload.update(changes)
    return env["planner"].reserve(actor or env["member"]["id"], **payload)


def test_reservation_persists(env):
    rows = reserve(env)
    assert len(rows) == 1 and rows[0]["status"] == "confirmed"
    assert rows[0]["version"] == 1 and rows[0]["buffer_minutes"] == 15
    assert env["planner"].get(rows[0]["id"])["title"] == "Workshop planning"


@pytest.mark.parametrize("starts,ends,conflicts", [
    ("2030-01-07T08:00","2030-01-07T08:45",False),
    ("2030-01-07T08:00","2030-01-07T08:46",True),
    ("2030-01-07T10:00","2030-01-07T11:00",True),
    ("2030-01-07T10:14","2030-01-07T11:00",True),
    ("2030-01-07T10:15","2030-01-07T11:00",False),
    ("2030-01-07T09:30","2030-01-07T09:45",True),
    ("2030-01-07T08:00","2030-01-07T12:00",True),
])
def test_buffer_and_half_open_boundaries(env, starts, ends, conflicts):
    from slotharbor.errors import DomainError
    reserve(env)
    if conflicts:
        with pytest.raises(DomainError) as ex:
            reserve(env, starts=starts, ends=ends, key="test-reservation-002")
        assert ex.value.status == 409
    else:
        assert reserve(env, starts=starts, ends=ends, key="test-reservation-002")


@pytest.mark.parametrize("changes", [
    {"attendees":9},{"attendees":0},{"attendees":True},{"count":0},{"count":27},
    {"interval_days":2},{"title":""},{"key":"short"},{"starts":"2029-12-31T09:00"},
    {"starts":"2030-01-07T06:59"},{"ends":"2030-01-07T21:01"},
    {"ends":"2030-01-08T10:00"},{"ends":"2030-01-07T08:59"},
    {"resource_id":9999},
])
def test_invalid_reservations(env, changes):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError):
        reserve(env, **changes)
    assert not env["planner"].list()


def test_idempotency_and_conflicting_replay(env):
    from slotharbor.errors import DomainError
    first = reserve(env)
    assert reserve(env) == first
    with pytest.raises(DomainError) as ex:
        reserve(env, title="Different purpose")
    assert ex.value.status == 409
    assert len(env["planner"].list()) == 1


def test_weekly_series_and_atomic_rollback(env):
    from slotharbor.errors import DomainError
    reserve(env, starts="2030-01-14T09:00", ends="2030-01-14T10:00", key="existing-in-week2")
    with pytest.raises(DomainError):
        reserve(env, count=3)
    assert len(env["planner"].list()) == 1
    rows = reserve(env, count=3, starts="2030-01-07T12:00", ends="2030-01-07T13:00")
    assert len(rows) == 3 and len({r["series_id"] for r in rows}) == 1


def test_cancel_releases_slot_and_replay_does_not_rebook(env):
    row = reserve(env)[0]
    result = env["planner"].transition(env["member"]["id"], row["id"], "cancel", 1)
    assert result["status"] == "cancelled" and result["version"] == 2
    assert reserve(env)[0]["status"] == "cancelled"
    assert reserve(env, key="new-after-cancel")


def test_ownership_and_stale_version(env):
    from slotharbor.errors import DomainError
    row = reserve(env)[0]
    with pytest.raises(DomainError) as ex:
        env["planner"].transition(env["second"]["id"], row["id"], "cancel", 1)
    assert ex.value.status == 403
    env["planner"].transition(env["member"]["id"], row["id"], "cancel", 1)
    with pytest.raises(DomainError) as ex:
        env["planner"].transition(env["member"]["id"], row["id"], "cancel", 1)
    assert ex.value.status == 409


def test_maintenance_blocks_and_releases(env):
    from slotharbor.errors import DomainError
    block = env["planner"].block(env["admin"]["id"], env["resource"]["id"],
          "2030-01-07T09:00", "2030-01-07T12:00", "Lighting inspection")
    with pytest.raises(DomainError): reserve(env)
    env["planner"].unblock(env["admin"]["id"], block["id"])
    assert reserve(env)


def test_maintenance_cannot_displace_booking(env):
    from slotharbor.errors import DomainError
    reserve(env)
    with pytest.raises(DomainError):
        env["planner"].block(env["admin"]["id"], env["resource"]["id"],
          "2030-01-07T10:00", "2030-01-07T12:00", "Inspection")


def test_simultaneous_writers_cannot_double_book(env):
    from slotharbor.errors import DomainError
    def run(i):
        try:
            return bool(reserve(env, key=f"concurrent-key-{i:03}"))
        except DomainError as ex:
            assert ex.status == 409
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, range(6)))
    assert sum(results) == 1 and len(env["planner"].list()) == 1


def test_audit_is_append_only(env):
    reserve(env)
    with env["db"].read() as con:
        assert con.execute("select count(*) from audit").fetchone()[0] >= 5
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("delete from audit")
