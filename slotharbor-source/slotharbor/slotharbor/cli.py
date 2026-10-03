"""Local administration. Passwords are prompted, never accepted as command arguments."""
import argparse
from datetime import datetime, timedelta
import getpass
import sys
from zoneinfo import ZoneInfo
from .accounts import Accounts
from .catalog import Catalog
from .db import Database
from .errors import DomainError, require
from .planning import Planner


def user_id(db,username):
    with db.read() as con:
        row=con.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE",(username,)).fetchone()
        require(row is not None,"That local account does not exist.",404)
        return row[0]


def demo(db,actor):
    catalog,planner=Catalog(db),Planner(db)
    require(not catalog.list(),"Demo setup requires an empty resource directory.")
    # Synthetic operational examples only. No passwords, contact details or real users.
    definitions=[("Recording studio","STUDIO",6,15,False),("Workshop bench","BENCH",4,20,True),
                 ("Focus room","FOCUS",2,10,False),("Seminar room","SEMINAR",18,15,True)]
    resources=[]
    for name,code,capacity,buffer,approval in definitions:
        resources.append(catalog.create(actor,name=name,code=code,capacity=capacity,buffer_minutes=buffer,
                         requires_approval=approval,timezone="Africa/Nairobi"))
    tomorrow=datetime.now(ZoneInfo("Africa/Nairobi")).date()+timedelta(days=1)
    titles=["Audio edit session","Prototype review","Writing block","Research roundtable",
            "Sound check","Fixture calibration","Sprint planning"]
    for i,title in enumerate(titles):
        resource=resources[i%4]
        date=tomorrow+timedelta(days=i//4)
        hour=9+i%4
        planner.reserve(actor,resource_id=resource["id"],title=title,starts=f"{date}T{hour:02}:00",
                        ends=f"{date}T{hour+1:02}:00",attendees=min(3,resource["capacity"]),key=f"demo-reservation-{i:03}")
    date=tomorrow+timedelta(days=3)
    planner.block(actor,resources[0]["id"],f"{date}T08:00",f"{date}T10:00","Microphone and cable inspection")


def main(argv=None):
    parser=argparse.ArgumentParser(prog="slotharbor",description="Shared-resource scheduling workspace")
    parser.add_argument("--database",default="instance/slotharbor.sqlite",help="SQLite database path")
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("init",help="Create the database schema")
    create=commands.add_parser("create-user",help="Create a workspace account")
    create.add_argument("--username",required=True)
    create.add_argument("--role",choices=["admin","coordinator","member"],default="member")
    create.add_argument("--actor",help="Existing administrator username; omit only for the first admin")
    reset=commands.add_parser("reset-password",help="Local account recovery; revokes existing sessions")
    reset.add_argument("--username",required=True)
    seed=commands.add_parser("demo",help="Add fictional examples to an empty resource directory")
    seed.add_argument("--actor",required=True)
    backup=commands.add_parser("backup",help="Create a consistent, integrity-checked backup")
    backup.add_argument("destination")
    serve=commands.add_parser("serve",help="Serve the workspace on loopback by default")
    serve.add_argument("--host",default="127.0.0.1")
    serve.add_argument("--port",type=int,default=8000)
    args=parser.parse_args(argv)
    try:
        db=Database(args.database)
        db.initialize()
        if args.command=="init":
            print(f"Database initialized: {db.path}")
        elif args.command=="create-user":
            password=getpass.getpass("New password (12+ characters): ")
            require(password==getpass.getpass("Repeat password: "),"The passwords did not match.")
            actor=user_id(db,args.actor) if args.actor else None
            user=Accounts(db).create_user(args.username,password,args.role,actor)
            print(f"Created {user['role']} account: {user['username']}")
        elif args.command=="reset-password":
            password=getpass.getpass("New password (12+ characters): ")
            require(password==getpass.getpass("Repeat password: "),"The passwords did not match.")
            Accounts(db).reset_password_local(args.username,password)
            print("Password changed; existing sessions revoked.")
        elif args.command=="demo":
            demo(db,user_id(db,args.actor))
            print("Fictional demonstration resources and reservations created.")
        elif args.command=="backup":
            db.backup(args.destination)
            print(f"Verified backup written: {args.destination}")
        elif args.command=="serve":
            import uvicorn
            from .web import create_app
            uvicorn.run(create_app(db.path),host=args.host,port=args.port,access_log=False,proxy_headers=False)
        return 0
    except (DomainError,OSError) as exc:
        print(f"Error: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
