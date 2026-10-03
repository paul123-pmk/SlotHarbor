"""Bound mutating request bodies before JSON parsing and set browser protections."""
from starlette.responses import JSONResponse


class RequestGuard:
    def __init__(self, app, secure=False):
        self.app = app
        self.secure = secure

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def guarded_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                    (b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"same-origin"), (b"cache-control", b"no-store"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")]
                if self.secure:
                    message["headers"].append((b"strict-transport-security", b"max-age=31536000"))
            await send(message)
        if scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, guarded_send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            part = message.get("body", b"")
            size += len(part)
            if size > 65536:
                return await JSONResponse({"error":"Request body exceeds 64 KiB.","code":"too_large"},413)(scope,receive,guarded_send)
            chunks.append(part)
            if not message.get("more_body", False):
                break
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type":"http.request", "body":b"".join(chunks), "more_body":False}
            return await receive()
        await self.app(scope, replay, guarded_send)
