"""`python -m labeler_rules`: answer every case, write labeling/work/rules/answers.csv."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from labeler_rules.decide import decide
from labeling import kit

FIELDS = ("case_id", "decision", "clause", "rule_version", "policy_version")


def label(root: Path) -> Path:
    cases = sorted(kit.load_cases(root), key=lambda c: kit.opaque_id(c["case_id"]))
    kit.write_map(root, kit.load_cases(root))
    out = kit.work(root) / "rules" / "answers.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for c in cases:
            a = decide(c)
            w.writerow([kit.opaque_id(c["case_id"]), a.decision, a.clause, a.rule_version,
                        a.policy_version])
    return out


def main(argv: list[str]) -> int:
    path = label(kit.ROOT)
    print(f"rules labeler answers in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
