"""The fixed development subset: 40 case ids drawn from the development cases (seed 20261118).

3 per case type with the seed, then the clean twin of every drawn adversarial case, then
filled to 40 by the seed (a candidate whose twin would not fit is skipped). `make dev-subset`
writes cases/dev/subset.txt.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

SEED = 20261118
SIZE = 40
PER_TYPE = 3


def draw(cases, seed=SEED, size=SIZE, per_type=PER_TYPE):
    """Sorted case ids of the subset."""
    by_id = {c["case_id"]: c for c in cases}
    by_type = defaultdict(list)
    for cid in sorted(by_id):
        by_type[by_id[cid]["type"]].append(cid)
    rng = random.Random(seed)
    chosen = set()
    for t in sorted(by_type):
        chosen.update(rng.sample(by_type[t], per_type))
    chosen.update(
        by_id[c]["clean_case_id"] for c in list(chosen) if by_id[c].get("clean_case_id")
    )
    rest = sorted(set(by_id) - chosen)
    rng.shuffle(rest)
    for cid in rest:
        if len(chosen) >= size:
            break
        add = {cid} | (
            {by_id[cid]["clean_case_id"]} if by_id[cid].get("clean_case_id") else set()
        )
        if len(chosen | add) <= size:
            chosen |= add
    return sorted(chosen)


def read_subset(path):
    return [x.strip() for x in Path(path).read_text().splitlines() if x.strip()]


def main(root=".", out="cases/dev/subset.txt"):
    root = Path(root)
    cases = [
        json.loads(x)
        for x in (root / "cases/dev/cases.jsonl").read_text().splitlines()
        if x.strip()
    ]
    ids = draw(cases)
    (root / out).write_text("\n".join(ids) + "\n")
    print(f"{len(ids)} case ids written to {root / out}")


if __name__ == "__main__":
    main()
