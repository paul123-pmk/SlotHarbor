import importlib.util
import re
import pytest
from test_domain import env, reserve


def test_web_module_exists():
    assert importlib.util.find_spec("slotharbor.web") is not None


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient
    from slotharbor.web import create_app
    with TestClient(create_app(env["db"].path, clock=lambda: env["now"])) as client:
        yield client


def sign_in(client, username="owner"):
    page = client.get("/login")
    token = re.search(r'name="csrf-token" content="([^\"]+)"', page.text).group(1)
    response = client.post("/api/auth/login", json={"username":username,"password":"test-only-long-passphrase"},
                           headers={"X-CSRF-Token":token})
    assert response.status_code == 200, response.text
    return response.json()["csrf"]


@pytest.mark.parametrize("path", ["/", "/resources", "/reservations", "/approvals", "/maintenance", "/reports", "/team"])
def test_pages_require_login(client, path):
    result = client.get(path, follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/", "/resources", "/reservations", "/approvals", "/maintenance", "/reports", "/team"])
def test_owner_pages_render(client, path):
    sign_in(client)
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert "SlotHarbor" in response.text
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_login_csrf_required(client):
    response = client.post("/api/auth/login", json={"username":"owner","password":"test-only-long-passphrase"})
    assert response.status_code == 403


def test_mutation_csrf_required(client):
    sign_in(client)
    result = client.post("/api/resources/1/activation", json={"active":False})
    assert result.status_code == 403


def test_member_admin_pages_denied(client):
    sign_in(client, "member")
    for path in ("/team", "/approvals", "/maintenance"):
        assert client.get(path).status_code == 403


def test_api_booking_roundtrip(client, env):
    csrf = sign_in(client,"member")
    payload = {"resource_id":env["resource"]["id"],"title":"API reservation", "starts":"2030-01-07T09:00",
               "ends":"2030-01-07T10:00","attendees":2,"key":"api-request-001"}
    first = client.post("/api/reservations", json=payload, headers={"X-CSRF-Token":csrf})
    assert first.status_code == 201, first.text
    bid = first.json()["reservations"][0]["id"]
    second = client.post("/api/reservations", json=payload, headers={"X-CSRF-Token":csrf})
    assert second.json() == first.json()
    assert client.get(f"/reservations/{bid}").status_code == 200
    cancel = client.post(f"/api/reservations/{bid}/transition", json={"action":"cancel","expected_version":1},
                         headers={"X-CSRF-Token":csrf})
    assert cancel.json()["status"] == "cancelled"


def test_logout_revokes_stolen_cookie(client, env):
    csrf = sign_in(client)
    cookie = client.cookies.get("slotharbor_session")
    assert client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token":csrf}).status_code == 200
    client.cookies.set("slotharbor_session",cookie)
    assert client.get("/api/me").status_code == 401


def test_unknown_fields_rejected(client):
    csrf = sign_in(client)
    result = client.post("/api/resources/1/activation", json={"active":False,"role":"admin"},
                         headers={"X-CSRF-Token":csrf})
    assert result.status_code == 422


def test_request_limits_and_host_validation(client):
    sign_in(client)
    result = client.post("/api/auth/login", content="x"*70000)
    assert result.status_code == 413
    assert client.get("/health",headers={"host":"attacker.example"}).status_code == 400


def test_titles_are_escaped(client, env):
    reserve(env,title='<script>alert("test")</script>')
    sign_in(client)
    html = client.get("/reservations").text
    assert '<script>alert("test")</script>' not in html
    assert "&lt;script&gt;" in html


def test_export_requires_login(client):
    assert client.get("/exports/reservations.csv").status_code == 401
    assert client.get("/exports/calendar.ics").status_code == 401


def test_non_ascii_csrf_fails_closed(client):
    sign_in(client)
    response=client.post("/api/auth/logout",json={},headers=[(b"X-CSRF-Token",b"\xff")])
    assert response.status_code == 403


def test_boolean_fold_is_not_a_clock_occurrence(client,env):
    csrf=sign_in(client)
    response=client.post("/api/reservations",json={"resource_id":env["resource"]["id"],"title":"Test fold",
        "starts":"2030-01-07T09:00","ends":"2030-01-07T10:00","key":"strict-fold-request","start_fold":True},
        headers={"X-CSRF-Token":csrf})
    assert response.status_code == 422


def test_active_only_domain_query(env):
    first=reserve(env)[0]
    env["planner"].transition(env["member"]["id"],first["id"],"cancel",1)
    second=reserve(env,key="active-only-next")[0]
    rows=env["planner"].list(active_only=True,limit=1)
    assert [r["id"] for r in rows] == [second["id"]]


def test_api_management_and_exports(client,env):
    csrf=sign_in(client)
    headers={"X-CSRF-Token":csrf}
    response=client.post("/api/resources",json={"name":"API room","code":"API","capacity":4,"requires_approval":True},headers=headers)
    assert response.status_code == 201
    rid=response.json()["id"]
    assert client.get("/api/resources").status_code == 200
    assert client.get("/api/schema").json()["info"]["title"] == "SlotHarbor"
    response=client.post("/api/reservations",json={"resource_id":rid,"title":"Pending session",
        "starts":"2030-01-08T09:00","ends":"2030-01-08T10:00","key":"api-management-request"},headers=headers)
    bid=response.json()["reservations"][0]["id"]
    assert client.get("/api/reservations?status=pending").json()["reservations"][0]["id"] == bid
    assert client.get("/api/reservations?resource_id="+str(rid)).status_code == 200
    result=client.post(f"/api/reservations/{bid}/transition",json={"action":"approve","expected_version":1},headers=headers)
    assert result.json()["status"] == "confirmed"
    block=client.post("/api/maintenance",json={"resource_id":rid,"reason":"Maintenance",
        "starts":"2030-01-10T08:00","ends":"2030-01-10T09:00"},headers=headers)
    assert block.status_code == 201
    assert client.post(f"/api/maintenance/{block.json()['id']}/release",json={},headers=headers).status_code == 200
    added=client.post("/api/users",json={"username":"newperson","password":"test-only-api-password","role":"member"},headers=headers)
    assert added.status_code == 201
    assert client.post(f"/api/users/{added.json()['id']}/activation",json={"active":False},headers=headers).status_code == 200
    assert client.post(f"/api/resources/{rid}/activation",json={"active":False},headers=headers).status_code == 200
    csv=client.get("/exports/reservations.csv")
    ics=client.get("/exports/calendar.ics")
    assert csv.status_code == 200 and "Pending session" in csv.text
    assert "BEGIN:VEVENT" in ics.text
    assert client.get("/login",follow_redirects=False).status_code == 303


def test_secure_cookie_headers(env):
    from fastapi.testclient import TestClient
    from slotharbor.web import create_app
    with TestClient(create_app(env["db"].path,clock=lambda:env["now"],secure=True),base_url="https://testserver") as client:
        sign_in(client)
        response=client.get("/")
        assert "max-age" in response.headers["strict-transport-security"]
        cookie=client.cookies.jar
        assert any(c.secure and c.has_nonstandard_attr("HttpOnly") for c in cookie)


def test_anonymous_session_reused_and_expired_form_rejected(client,env):
    first=client.get("/login")
    raw=client.cookies.get("slotharbor_session")
    second=client.get("/login")
    assert client.cookies.get("slotharbor_session") == raw
    assert re.search(r'name="csrf-token" content="([^\"]+)"',first.text).group(1) in second.text
    csrf=re.search(r'name="csrf-token" content="([^\"]+)"',first.text).group(1)
    with env["db"].write() as con:
        con.execute("UPDATE sessions SET expires_at=?",(env["now"]-1,))
    result=client.post("/api/auth/login",json={"username":"owner","password":"test-only-long-passphrase"},headers={"X-CSRF-Token":csrf})
    assert result.status_code == 403


def test_unknown_private_record_redirects_before_existence_check(client):
    result=client.get("/reservations/987654",follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"] == "/login"
