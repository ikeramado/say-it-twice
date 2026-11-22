"""`python -m labeling <sheets|import|kappa|freeze> [labeler]`."""

from __future__ import annotations

import sys

from labeling import kit


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    root = kit.ROOT
    try:
        if cmd in ("sheets", "import"):
            if not rest or not rest[0]:
                print(f"usage: make label-{cmd} LABELER=<{'|'.join(kit.LABELERS)}>")
                return 2
            lab = rest[0]
            if lab not in kit.LABELERS:
                raise kit.LabelingError(f"unknown labeler {lab!r}; use {kit.LABELERS}")
            if cmd == "sheets":
                print(f"sheets in {kit.label_sheets(root, lab)}")
                return 0
            r = kit.import_answers(root, lab)
            print(f"{lab}: {r['answered']} answered, {len(r['missing'])} missing")
            for key in ("missing", "invalid", "unknown"):
                if r[key]:
                    print(f"{key}: {' '.join(r[key])}")
            return 1 if r["missing"] or r["invalid"] or r["unknown"] else 0
        if cmd == "kappa":
            r = kit.compare(root)
            for pair, k in r["kappas"].items():
                print(f"kappa on decision, {pair}: {k:.3f} over {r['n']} cases")
            print(f"three-way agreement on decision: {r['three_way']:.3f}")
            print(f"{len(r['carried'])} resolutions carried, "
                  f"{len(r['disagreements'])} disagreements, listed in {r['path']}")
            return 0
        if cmd == "freeze":
            r = kit.label_freeze(root)
            print(f"{r['labels']} labels in {r['path']}; {len(r['excluded'])} excluded")
            return 0
    except kit.LabelingError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
