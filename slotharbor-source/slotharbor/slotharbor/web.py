"""Authenticated HTML pages and a same-origin JSON API."""
import hmac
import os
from pathlib import Path
import time
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .accounts import Accounts
from .catalog import Catalog
from .db import Database
from .errors import DomainError, require
from .exports import calendar_ics, reservations_csv
from .middleware import RequestGuard
from .models import Activation, Login, Maintenance, NewUser, Reservation, Resource, Transition
from .planning import Planner
from .times import local_label


COOKIE = "slotharbor_session"
ROOT = Path(__file__).parent


def create_app(database=None, *, clock=None, secure=None, hosts=None):
    clock = clock or (lambda: int(time.time()))
    db = Database(database or os.environ.get("SLOTHARBOR_DATABASE", "instance/slotharbor.sqlite"))
    db.initialize()
    accounts, catalog, planner = Accounts(db,clock), Catalog(db,clock), Planner(db,clock)
    secure = os.environ.get("SLOTHARBOR_SECURE_COOKIE", "0") == "1" if secure is None else secure
    hosts = hosts or os.environ.get("SLOTHARBOR_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    app = FastAPI(title="SlotHarbor",version="0.1.0",docs_url=None,redoc_url=None,openapi_url=None)
    app.state.accounts, app.state.catalog, app.state.planner, app.state.db = accounts,catalog,planner,db
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(RequestGuard, secure=secure)
    app.mount("/static", StaticFiles(directory=ROOT/"static"), name="static")
    templates = Jinja2Templates(directory=ROOT/"templates")
    templates.env.filters["localtime"] = local_label
    templates.env.filters["hours"] = lambda seconds: f"{seconds/3600:.1f}"

    def current(request):
        return accounts.session(request.cookies.get(COOKIE))

    def authenticated(request: Request):
        session = current(request)
        require(session is not None and session["user"] is not None, "Sign in to continue.", 401, "unauthenticated")
        return session

    def page_access(request: Request):
        session = current(request)
        if not session or not session["user"]:
            raise HTTPException(status_code=303, headers={"Location": "/login"})

    def csrf_guard(request: Request):
        if request.method not in {"POST","PUT","PATCH","DELETE"}:
            return
        session = current(request)
        token = request.headers.get("X-CSRF-Token", "")
        require(session is not None and 0 < len(token) <= 128 and token.isascii() and hmac.compare_digest(session["csrf"], token),
                "The form expired or could not be verified. Reload the page.", 403, "csrf")

    def role(session, allowed):
        require(session["user"]["role"] in allowed, "Your role cannot open this page.", 403, "forbidden")

    def render(request, name, *, allowed=None, **context):
        session = current(request)
        if not session or not session["user"]:
            return RedirectResponse("/login",303)
        if allowed:
            role(session,allowed)
        return templates.TemplateResponse(request=request,name=name,context={
            "user":session["user"],"csrf":session["csrf"],"path":request.url.path,
            "now":clock(),"resources":catalog.list(),**context})

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        if request.url.path.startswith(("/api/","/exports/")):
            return JSONResponse({"error":exc.message,"code":exc.code},status_code=exc.status)
        return templates.TemplateResponse(request=request,name="error.html",context={"message":exc.message,"status":exc.status},status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo submitted passwords, session tokens or complete request bodies.
        problems = [{"field":".".join(str(p) for p in e["loc"]),"message":e["msg"]} for e in exc.errors()]
        return JSONResponse({"error":"Check the submitted fields.","code":"validation","fields":problems},422)

    @app.get("/health")
    def health():
        with db.read() as con:
            con.execute("SELECT 1").fetchone()
        return {"status":"ok","version":"0.1.0"}

    @app.get("/login",response_class=HTMLResponse)
    def login_page(request: Request):
        session = current(request)
        if session and session["user"]:
            return RedirectResponse("/",303)
        raw = None
        if session is None:
            raw,csrf = accounts.new_session()
        else:
            csrf = session["csrf"]
        response = templates.TemplateResponse(request=request,name="login.html",context={"csrf":csrf})
        if raw:
            response.set_cookie(COOKIE,raw,max_age=900,httponly=True,secure=secure,samesite="strict",path="/")
        return response

    @app.get("/",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def dashboard(request: Request):
        upcoming = planner.list(start=clock(),end=clock()+7*86400,limit=100,active_only=True)
        summary = planner.summary(clock(),clock()+7*86400)
        return render(request,"dashboard.html",bookings=[b for b in upcoming if b["status"] in {"pending","confirmed"}],
                      summary=summary)

    @app.get("/resources",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def resource_page(request: Request):
        return render(request,"resources.html")

    @app.get("/reservations",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def reservations_page(request: Request, status: str | None=None, resource_id: int | None=None, offset: int=0):
        return render(request,"reservations.html",bookings=planner.list(status=status,resource_id=resource_id,limit=100,offset=offset),
                      selected_status=status or "",offset=offset,selected_resource=resource_id)

    @app.get("/reservations/{identifier}",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def detail_page(request: Request, identifier: int):
        return render(request,"detail.html",booking=planner.get(identifier))

    @app.get("/approvals",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def approvals_page(request: Request):
        return render(request,"approvals.html",allowed={"admin","coordinator"},bookings=planner.list(status="pending"))

    @app.get("/maintenance",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def maintenance_page(request: Request):
        return render(request,"maintenance.html",allowed={"admin","coordinator"},blocks=planner.blocks())

    @app.get("/reports",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def reports_page(request: Request):
        return render(request,"reports.html",summary=planner.summary(clock(),clock()+7*86400),
                      audit=planner.audit_log(50))

    @app.get("/team",response_class=HTMLResponse,dependencies=[Depends(page_access)])
    def team_page(request: Request):
        return render(request,"team.html",allowed={"admin"},users=accounts.list())

    api = APIRouter(prefix="/api",dependencies=[Depends(csrf_guard)])

    @api.post("/auth/login")
    def login(payload: Login, request: Request):
        client = request.client.host if request.client else "local"
        raw,csrf,user = accounts.login(payload.username,payload.password,client)
        previous = request.cookies.get(COOKIE)
        if previous:
            accounts.revoke(previous)
        response = JSONResponse({"user":user,"csrf":csrf,"redirect":"/"})
        response.set_cookie(COOKIE,raw,max_age=28800,httponly=True,secure=secure,samesite="strict",path="/")
        return response

    @api.post("/auth/logout")
    def logout(request: Request, session=Depends(authenticated)):
        accounts.revoke(request.cookies[COOKIE])
        response = JSONResponse({"redirect":"/login"})
        response.delete_cookie(COOKIE,path="/",httponly=True,secure=secure,samesite="strict")
        return response

    @api.get("/me")
    def me(session=Depends(authenticated)):
        return {"user":session["user"],"csrf":session["csrf"]}

    @api.get("/resources")
    def resource_list(session=Depends(authenticated)):
        return {"resources":catalog.list()}

    @api.post("/resources",status_code=201)
    def create_resource(payload: Resource, session=Depends(authenticated)):
        return catalog.create(session["user"]["id"],**payload.model_dump())

    @api.post("/resources/{identifier}/activation")
    def activate_resource(identifier:int,payload:Activation,session=Depends(authenticated)):
        return catalog.set_active(session["user"]["id"],identifier,payload.active)

    @api.get("/reservations")
    def reservation_list(status: str | None=None,resource_id:int | None=None,offset:int=0,session=Depends(authenticated)):
        return {"reservations":planner.list(status=status,resource_id=resource_id,limit=100,offset=offset)}

    @api.post("/reservations",status_code=201)
    def create_reservation(payload:Reservation,session=Depends(authenticated)):
        return {"reservations":planner.reserve(session["user"]["id"],**payload.model_dump())}

    @api.post("/reservations/{identifier}/transition")
    def transition(identifier:int,payload:Transition,session=Depends(authenticated)):
        return planner.transition(session["user"]["id"],identifier,payload.action,payload.expected_version)

    @api.post("/maintenance",status_code=201)
    def create_block(payload:Maintenance,session=Depends(authenticated)):
        return planner.block(session["user"]["id"],**payload.model_dump())

    @api.post("/maintenance/{identifier}/release")
    def release_block(identifier:int,session=Depends(authenticated)):
        return planner.unblock(session["user"]["id"],identifier)

    @api.post("/users",status_code=201)
    def create_user(payload:NewUser,session=Depends(authenticated)):
        return accounts.create_user(**payload.model_dump(),actor=session["user"]["id"])

    @api.post("/users/{identifier}/activation")
    def activate_user(identifier:int,payload:Activation,session=Depends(authenticated)):
        return accounts.set_active(session["user"]["id"],identifier,payload.active)

    @api.get("/schema")
    def schema(session=Depends(authenticated)):
        return app.openapi()

    @app.get("/exports/reservations.csv")
    def csv_export(offset:int=0,session=Depends(authenticated)):
        rows = planner.list(limit=5000,offset=offset)
        return Response("\ufeff"+reservations_csv(rows),media_type="text/csv",
                        headers={"Content-Disposition":"attachment; filename=slotharbor-reservations.csv","X-Export-Limit":"5000"})

    @app.get("/exports/calendar.ics")
    def ics_export(offset:int=0,session=Depends(authenticated)):
        return Response(calendar_ics(planner.list(limit=5000,offset=offset)),media_type="text/calendar",
                        headers={"Content-Disposition":"attachment; filename=slotharbor-calendar.ics","X-Export-Limit":"5000"})

    app.include_router(api)
    return app
