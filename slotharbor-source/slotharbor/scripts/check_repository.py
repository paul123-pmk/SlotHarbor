"""Check tracked-file hygiene; this is not a secret scanner or PII detector."""
from pathlib import Path
import subprocess
import sys


def main():
    root=Path(__file__).resolve().parents[1]
    files=subprocess.check_output(["git","ls-files","-z"],cwd=root).decode().split("\0")
    forbidden=[]
    for name in filter(None,files):
        path=Path(name)
        if ({"instance",".venv","node_modules","__pycache__"} & set(path.parts)
            or path.suffix in {".sqlite",".sqlite3",".db",".pyc",".bundle"}
            or path.name==".env" or path.name.startswith(".env.")):
            forbidden.append(name)
    if forbidden:
        print("Unexpected private/runtime files tracked:",*forbidden,sep="\n")
        return 1
    print("Tracked-file hygiene passed. This does not replace a whole-history secret scan.")
    return 0


if __name__=="__main__":
    sys.exit(main())
