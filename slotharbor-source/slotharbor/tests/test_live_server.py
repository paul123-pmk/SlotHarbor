"""Exercise the real TCP/ASGI stack, not just the in-process HTTP test adapter."""
import re
import socket
import threading
import time
import httpx
import uvicorn
from test_domain import env


def test_live_server_login_booking_conflict_and_export(env):
    from slotharbor.web import create_app
    listener=socket.socket()
    listener.bind(("127.0.0.1",0))
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(env["db"].path,clock=lambda:env["now"]),
        log_level="error",access_log=False,proxy_headers=False,ws="none"))
    thread=threading.Thread(target=server.run,kwargs={"sockets":[listener]},daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}",trust_env=False,timeout=5) as client:
            for attempt in range(100):
                try:
                    if client.get("/health").status_code==200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.05)
            else:
                raise AssertionError("The local server did not become healthy")
            html=client.get("/login").text
            csrf=re.search(r'name="csrf-token" content="([^\"]+)"',html).group(1)
            login=client.post("/api/auth/login",json={"username":"owner","password":"test-only-long-passphrase"},
                              headers={"X-CSRF-Token":csrf})
            assert login.status_code==200
            headers={"X-CSRF-Token":login.json()["csrf"]}
            payload={"resource_id":env["resource"]["id"],"title":"TCP integration session",
                     "starts":"2030-01-07T09:00","ends":"2030-01-07T10:00","key":"live-server-request"}
            first=client.post("/api/reservations",json=payload,headers=headers)
            assert first.status_code==201
            assert client.post("/api/reservations",json=payload,headers=headers).json()==first.json()
            assert client.post("/api/reservations",json={**payload,"key":"another-live-request"},headers=headers).status_code==409
            assert "TCP integration session" in client.get("/exports/reservations.csv").text
            assert "function payloadFor" in client.get("/static/app.js").text
            assert client.post("/api/auth/logout",json={},headers=headers).status_code==200
            assert client.get("/api/me").status_code==401
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
