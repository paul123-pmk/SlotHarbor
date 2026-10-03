import importlib.util
import csv
import io
import pytest
from test_domain import env, reserve


def test_exports_module_exists():
    assert importlib.util.find_spec("slotharbor.exports") is not None


@pytest.mark.parametrize("value", ["=SUM(1,2)", "+1", "-1", "@value", "  =X", "\t=2"])
def test_csv_formula_neutralization(value):
    from slotharbor.exports import safe_cell
    assert safe_cell(value).startswith("'")


def test_csv_roundtrip(env):
    from slotharbor.exports import reservations_csv
    row = reserve(env,title='Meeting, notes "included"')[0]
    data = reservations_csv([row])
    parsed = list(csv.DictReader(io.StringIO(data)))
    assert parsed[0]["purpose"] == row["title"]
    assert parsed[0]["status"] == "confirmed"


def test_ical_escaping_and_utf8_line_folding(env):
    from slotharbor.exports import calendar_ics
    row = reserve(env,title="Team, review; " + "é"*90)[0]
    text = calendar_ics([row])
    assert "BEGIN:VCALENDAR\r\n" in text
    assert "DTSTART:20300107T060000Z" in text
    assert "Team\\, review\\;" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert text.endswith("END:VCALENDAR\r\n")


def test_ical_cancelled_status(env):
    from slotharbor.exports import calendar_ics
    row = reserve(env)[0]
    row = env["planner"].transition(env["member"]["id"], row["id"], "cancel", 1)
    assert "STATUS:CANCELLED" in calendar_ics([row])
