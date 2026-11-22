import argparse
import json
import sys

from . import TrayError, act, find, preview, queue, view


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m report.tray")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("show", "approve", "change", "reject"):
        p = sub.add_parser(name)
        p.add_argument("case_id")
        p.add_argument("run", type=int)
        if name in ("change", "reject", "approve"):
            p.add_argument("--note", default="")
        if name == "change":
            p.add_argument("--to", required=True)
    v = sub.add_parser("view")
    v.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            for it in queue(a.root):
                print(it["case_id"], it["run"], it["clause"], it["proposal"] or "none")
        elif a.cmd == "show":
            it = find(a.root, a.case_id, a.run)
            print(json.dumps({**it, "preview": preview(it)}, indent=2))
        elif a.cmd == "view":
            print(view(a.root, a.out))
        else:
            print(json.dumps(act(a.root, a.cmd, a.case_id, a.run, getattr(a, "to", None), a.note)))
    except TrayError as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
