from datetime import datetime, timezone
import pytest
from test_domain import env, reserve


def approval_resource(env, **extra):
    return env["catalog"].create(env["admin"]["id"],name="Review room",code="REVIEW",
            timezone="UTC",capacity=4,buffer_minutes=0,requires_approval=True,**extra)


def test_pending_holds_slot_and_member_cannot_approve(env):
    from slotharbor.errors import DomainError
    r = approval_resource(env)
    booking = reserve(env,resource_id=r["id"])[0]
    assert booking["status"] == "pending"
    with pytest.raises(DomainError): reserve(env,resource_id=r["id"],key="another-booking-001")
    with pytest.raises(DomainError) as ex:
        env["planner"].transition(env["member"]["id"],booking["id"],"approve",1)
    assert ex.value.status == 403
    result = env["planner"].transition(env["admin"]["id"],booking["id"],"approve",1)
    assert result["status"] == "confirmed" and result["version"] == 2


def test_rejection_releases_slot(env):
    r = approval_resource(env)
    b = reserve(env,resource_id=r["id"])[0]
    assert env["planner"].transition(env["admin"]["id"],b["id"],"reject",1)["status"] == "rejected"
    assert reserve(env,resource_id=r["id"],key="replacement-booking")


def test_past_and_paused_approval_rejected(env):
    from slotharbor.errors import DomainError
    r = approval_resource(env)
    b = reserve(env,resource_id=r["id"])[0]
    env["catalog"].set_active(env["admin"]["id"],r["id"],False)
    with pytest.raises(DomainError): env["planner"].transition(env["admin"]["id"],b["id"],"approve",1)
    env["catalog"].set_active(env["admin"]["id"],r["id"],True)
    env["planner"].clock = lambda: b["start_at"]
    with pytest.raises(DomainError): env["planner"].transition(env["admin"]["id"],b["id"],"approve",1)


def test_coordinator_scope(env):
    from slotharbor.errors import DomainError
    u = env["accounts"].create_user("coordinator","test-only-long-passphrase","coordinator",env["admin"]["id"])
    r = env["catalog"].create(u["id"],name="New bench",code="BENCH")
    assert r["id"] > 0
    with pytest.raises(DomainError): env["accounts"].set_active(u["id"],env["member"]["id"],False)


@pytest.mark.parametrize("changes", [
    {"capacity":0},{"capacity":1.5},{"capacity":True},{"opens":"25:00"},{"closes":"06:00"},
    {"weekdays":[]},{"weekdays":[0,0]},{"weekdays":[7]},{"weekdays":[True]},
    {"buffer_minutes":121},{"code":"BAD CODE"},{"timezone":"Not/AZone"},{"requires_approval":"false"},
])
def test_bad_resource_policy(env,changes):
    from slotharbor.errors import DomainError
    payload = dict(name="Another room",code="OTHER")
    payload.update(changes)
    with pytest.raises(DomainError): env["catalog"].create(env["admin"]["id"],**payload)


def test_closed_weekday_in_series_rolls_back(env):
    from slotharbor.errors import DomainError
    r = approval_resource(env,weekdays=[0])
    with pytest.raises(DomainError): reserve(env,resource_id=r["id"],count=2,interval_days=1)
    assert env["planner"].list() == []


def test_weekly_local_time_survives_dst_shift(env):
    r = env["catalog"].create(env["admin"]["id"],name="NY studio",code="NY",timezone="America/New_York")
    rows = reserve(env,resource_id=r["id"],attendees=1,starts="2030-03-03T09:00",ends="2030-03-03T10:00",count=3)
    assert rows[1]["start_at"]-rows[0]["start_at"] == 7*86400-3600
    assert rows[2]["start_at"]-rows[1]["start_at"] == 7*86400


def test_gap_in_recurrence_rolls_back_whole_series(env):
    from slotharbor.errors import DomainError
    r = env["catalog"].create(env["admin"]["id"],name="Night studio",code="NIGHT",timezone="America/New_York",opens="00:00",closes="23:59")
    with pytest.raises(DomainError):
        reserve(env,resource_id=r["id"],attendees=1,starts="2030-03-03T02:15",ends="2030-03-03T03:15",count=2)
    assert not env["planner"].list()


def test_idempotency_scoped_to_user(env):
    first = reserve(env)[0]
    other = reserve(env,actor=env["second"]["id"],starts="2030-01-07T12:00",ends="2030-01-07T13:00")[0]
    assert first["id"] != other["id"]


def test_member_cannot_manage_resources_or_maintenance(env):
    from slotharbor.errors import DomainError
    with pytest.raises(DomainError): env["catalog"].set_active(env["member"]["id"],env["resource"]["id"],False)
    with pytest.raises(DomainError): env["planner"].block(env["member"]["id"],env["resource"]["id"],"2030-01-08T09:00","2030-01-08T11:00","Inspection")


def test_summary_clips_to_window_and_excludes_cleanup(env):
    b = reserve(env)[0]
    rows = env["planner"].summary(b["start_at"]+900,b["end_at"]-900)
    assert rows[0]["booked_seconds"] == 1800 and rows[0]["confirmed"] == 1
    env["planner"].transition(env["member"]["id"],b["id"],"cancel",1)
    assert env["planner"].summary(b["start_at"],b["end_at"])[0]["booked_seconds"] == 0


def test_database_rollback_and_backup(env,tmp_path):
    from slotharbor.db import Database
    with pytest.raises(RuntimeError):
        with env["db"].write() as con:
            con.execute("UPDATE resources SET active=0")
            raise RuntimeError("deliberate rollback")
    assert env["catalog"].get(env["resource"]["id"])["active"]
    reserve(env)
    dest=tmp_path/"backup.sqlite"
    env["db"].backup(dest)
    with Database(dest).read() as con:
        assert con.execute("SELECT count(*) FROM bookings").fetchone()[0] == 1
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with pytest.raises(FileExistsError): env["db"].backup(dest)


def test_pausing_preserves_existing_and_exact_replays(env):
    from slotharbor.errors import DomainError
    b=reserve(env)
    env["catalog"].set_active(env["admin"]["id"],env["resource"]["id"],False)
    assert reserve(env) == b
    with pytest.raises(DomainError): reserve(env,key="new-while-paused")


def test_concurrent_idempotent_retries_return_one_reservation(env):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(lambda _:reserve(env),range(5)))
    assert len({result[0]["id"] for result in rows}) == 1
    assert len(env["planner"].list()) == 1
