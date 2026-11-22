"""Split carrier-months into development and test, draw each type per side, write the files.

`python -m cases.split` (make cases) reads the ingested months through the access point and
writes cases/dev/cases.jsonl, cases/test/cases.jsonl, cases/test/hash.txt, cases/excluded.jsonl
and cases/split.json; it fills the seed, the test hash and the last month in the prereg.
It never deletes anything, so cases/test/dot/ (T10) stays.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from agents.system.tools import data_root, read_data
from cases.adversarial import ATTACKS, make_adversarial
from cases.builder import (
    CARRIERS,
    CLEAR_TYPES,
    DRAW_ORDER,
    MAX_PER_CM,
    POOL_TYPES,
    SEED,
    SHORT,
    TARGETS,
    build_case,
    flight_key,
    merge_pools,
    month_pools,
)
from rules.lookup import Exclusion

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREREG = ROOT / "docs" / "modules" / "prereg.md"


class Shortfall(Exception):
    """A type cannot reach its count from real flights: the card escalates."""


def capacity(pools, t, cm):
    return min(MAX_PER_CM, len(pools.get(t, {}).get(cm, ())))


def assign_split(pools, seed=SEED, targets=TARGETS):
    """Carrier-months go to test, in seeded order, while they add capacity to a type whose
    test count is not yet met; the rest go to dev. Returns (dev_cms, test_cms)."""
    cms = sorted({cm for by in pools.values() for cm in by})
    random.Random(f"{seed}:split").shuffle(cms)
    have = dict.fromkeys(POOL_TYPES, 0)
    need = {t: targets[t][1] for t in POOL_TYPES}
    test, dev = [], []
    for cm in cms:
        useful = [t for t in POOL_TYPES if have[t] < need[t] and capacity(pools, t, cm)]
        if useful:
            test.append(cm)
            for t in POOL_TYPES:
                have[t] += capacity(pools, t, cm)
        else:
            dev.append(cm)
    return sorted(dev), sorted(test)


def draw(pools, t, cms, count, used, seed, side, make):
    """Take `count` cases of type t from carrier-months cms, alternating airlines, at most
    MAX_PER_CM per carrier-month. make(cm, row, delay) returns a case or None (an exclusion,
    already listed). Raises Shortfall when the real flights run out."""
    rng = random.Random(f"{seed}:draw:{t}:{side}")
    by_carrier = {}
    for cm in cms:
        by_carrier.setdefault(cm.split(":")[0], []).append(cm)
    for lst in by_carrier.values():
        lst.sort()
        rng.shuffle(lst)
    taken = dict.fromkeys(cms, 0)
    cursor = dict.fromkeys(cms, 0)
    out = []
    progress = True
    width = max(map(len, by_carrier.values()), default=0)
    while len(out) < count and progress:
        progress = False
        for i in range(width):
            for carrier in CARRIERS:
                lst = by_carrier.get(carrier, [])
                if i >= len(lst) or len(out) >= count:
                    continue
                cm = lst[i]
                flights = pools.get(t, {}).get(cm, [])
                while taken[cm] < MAX_PER_CM and cursor[cm] < len(flights):
                    row, delay = flights[cursor[cm]]
                    cursor[cm] += 1
                    if flight_key(row) in used:
                        continue
                    used.add(flight_key(row))
                    case = make(cm, row, delay)
                    if case is None:
                        continue
                    out.append(case)
                    taken[cm] += 1
                    progress = True
                    break
    if len(out) < count:
        raise Shortfall(f"{t} on {side}: {len(out)} real flights of {count} needed")
    return out


def build_side(pools, cms, side, seed, targets, excluded):
    """All clean cases of one side, then its adversarial ones."""
    cases, used = [], set()
    col = 0 if side == "dev" else 1
    for t in DRAW_ORDER:
        n = [0]

        def make(cm, row, delay, t=t, n=n):
            cid = f"{side}-{SHORT[t]}-{n[0] + 1:03d}"
            case = build_case(cid, t, row, delay, side, seed)
            if isinstance(case, Exclusion):
                excluded.append(
                    {
                        "type": t,
                        "side": side,
                        "carrier_month": cm,
                        "bts_flight": dict(
                            zip(
                                ("carrier", "flight_number", "date", "origin"),
                                flight_key(row),
                            )
                        ),
                        "reason": case.reason,
                    }
                )
                return None
            n[0] += 1
            return case

        cases += draw(pools, t, cms, targets[t][col], used, seed, side, make)
    clear = sorted(
        (c for c in cases if c["type"] in CLEAR_TYPES), key=lambda c: c["case_id"]
    )
    rng = random.Random(f"{seed}:adversarial:{side}")
    rng.shuffle(clear)
    want = targets["adversarial"][col]
    if len(clear) < want:
        raise Shortfall(
            f"adversarial on {side}: {len(clear)} clear cases of {want} needed"
        )
    chosen, per_cm = [], {}
    for clean in clear:  # at most MAX_PER_CM adversarial cases per carrier-month
        cm = clean["meta"]["carrier_month"]
        if len(chosen) < want and per_cm.get(cm, 0) < MAX_PER_CM:
            per_cm[cm] = per_cm.get(cm, 0) + 1
            chosen.append(clean)
    if len(chosen) < want:
        raise Shortfall(
            f"adversarial on {side}: {len(chosen)} of {want} within the cap"
        )
    for i, clean in enumerate(chosen):
        cases.append(make_adversarial(clean, ATTACKS[i % len(ATTACKS)]))
    return cases


def build_split(pools, seed=SEED, targets=TARGETS):
    dev_cms, test_cms = assign_split(pools, seed, targets)
    excluded: list[dict] = []
    test = build_side(pools, test_cms, "test", seed, targets, excluded)
    dev = build_side(pools, dev_cms, "dev", seed, targets, excluded)
    return {
        "dev": dev,
        "test": test,
        "excluded": excluded,
        "dev_carrier_months": dev_cms,
        "test_carrier_months": test_cms,
    }


def canonical_lines(cases):
    return sorted(
        json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for c in cases
    )


def test_hash(cases) -> str:
    """SHA-256 of the sorted, canonical-JSON lines of the test cases, one per line."""
    text = "".join(line + "\n" for line in canonical_lines(cases))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- reading the ingested months through the access point ----


def months_available(root=None):
    d = data_root(root) / "data" / "clean" / "flights"
    return sorted(p.stem for p in d.glob("*.csv"))


def read_month_rows(month, root=None):
    text = read_data(f"data/clean/flights/{month}.csv", root)
    lines = text.splitlines()
    header = lines[0].split(",")
    keep = tuple(f"{c}," for c in CARRIERS)
    return [dict(zip(header, ln.split(","))) for ln in lines[1:] if ln.startswith(keep)]


def load_pools(months, root=None, seed=SEED):
    return merge_pools(month_pools(read_month_rows(m, root), m, seed) for m in months)


# ---- outputs ----


def write_jsonl(path, cases):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n" for c in cases
        ),
        encoding="utf-8",
    )


def update_prereg(path, seed, digest, last_month):
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(
        r"\*\*Sampling seed:\*\* .*", f"**Sampling seed:** {seed}", text, count=1
    )
    text = re.sub(
        r"\*\*Test case hash:\*\* .*", f"**Test case hash:** {digest}", text, count=1
    )
    text = re.sub(
        r"\(TODO: last month, filled in T4\.2\)|\(last month used: [0-9-]+\)",
        f"(last month used: {last_month})",
        text,
        count=1,
    )
    Path(path).write_text(text, encoding="utf-8")


def write_outputs(result, out=HERE, prereg=PREREG, seed=SEED, last_month=""):
    digest = test_hash(result["test"])
    write_jsonl(out / "dev" / "cases.jsonl", result["dev"])
    write_jsonl(out / "test" / "cases.jsonl", result["test"])
    (out / "test" / "hash.txt").write_text(digest + "\n", encoding="utf-8")
    write_jsonl(out / "excluded.jsonl", result["excluded"])
    (out / "split.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "last_month": last_month,
                "test_hash": digest,
                "dev_carrier_months": result["dev_carrier_months"],
                "test_carrier_months": result["test_carrier_months"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if prereg:
        update_prereg(prereg, seed, digest, last_month)
    return digest


def main(root=None):
    months = months_available(root)
    if not months or months[0] != "2024-01":
        raise SystemExit("escalate: the ingested months do not start in 2024-01")
    result = build_split(load_pools(months, root))
    digest = write_outputs(result, last_month=months[-1])
    print(
        f"dev {len(result['dev'])}, test {len(result['test'])}, "
        f"excluded {len(result['excluded'])}, test hash {digest}"
    )


if __name__ == "__main__":
    main()
