"""Consistency per case and its cluster-bootstrap interval (prereg sections 5 and 6)."""

import json
import random
from collections import defaultdict
from pathlib import Path

RESAMPLES = 10_000
SEED = 20261118


def load_decisions(run_dir):
    """{case_id: [decision per run]} from runs/<run_id>/outputs."""
    out = defaultdict(list)
    for f in sorted((Path(run_dir) / "outputs").glob("*.json")):
        d = json.loads(f.read_text())
        out[d["case_id"]].append(d["decision"])
    return dict(out)


def case_consistent(decisions):
    """1 if every run gives the same decision, else 0."""
    return int(len(set(decisions)) == 1)


def carrier_month(case):
    return f"{case['carrier']}-{case['flight_date'][:7]}"


def consistency_share(cases, decisions, resamples=RESAMPLES, seed=SEED):
    """Share of cases with identical decisions over their runs, with a 95% percentile
    cluster bootstrap by carrier-month (one agent: the paired version over differences
    comes with the real agents)."""
    clusters = defaultdict(list)
    for c in cases:
        clusters[carrier_month(c)].append(case_consistent(decisions[c["case_id"]]))
    groups = [clusters[k] for k in sorted(clusters)]
    total = sum(len(g) for g in groups)
    share = sum(sum(g) for g in groups) / total
    rng = random.Random(seed)
    shares = []
    for _ in range(resamples):
        draw = [groups[rng.randrange(len(groups))] for _ in groups]
        shares.append(sum(sum(g) for g in draw) / sum(len(g) for g in draw))
    shares.sort()
    lo = shares[int(0.025 * resamples)]
    hi = shares[int(0.975 * resamples) - 1]
    return {
        "share": share,
        "low": lo,
        "high": hi,
        "cases": total,
        "consistent": sum(sum(g) for g in groups),
        "clusters": len(groups),
        "resamples": resamples,
    }


def cluster_draws(keys, resamples=RESAMPLES, seed=SEED):
    """The resamples of a paired cluster bootstrap: each a list of len(keys) cluster keys
    drawn with replacement. One resample's draw serves every agent (the pairing)."""
    keys = sorted(keys)
    rng = random.Random(seed)
    return [[keys[rng.randrange(len(keys))] for _ in keys] for _ in range(resamples)]


def percentile_interval(values):
    """The 95% percentile interval, by consistency_share's index convention."""
    s = sorted(values)
    return s[int(0.025 * len(s))], s[int(0.975 * len(s)) - 1]


def _stat(units, keys):
    n = sum(units[k][1] for k in keys)
    return sum(units[k][0] for k in keys) / n if n else 0.0


def paired_difference(a, b, draws, point=None):
    """Agent a minus agent b with its 95% interval. a, b: {cluster: (sum, count)} over the
    same clusters (the sum of a 0/1 outcome over the cluster's units, and their count); a
    statistic is the sum over the drawn clusters divided by their count, and each resample
    uses one draw for both agents. point: the difference to report, when the statistic's own
    definition differs from the pooled one (else the pooled difference)."""
    keys = sorted(a)
    diff = _stat(a, keys) - _stat(b, keys) if point is None else point
    low, high = percentile_interval([_stat(a, d) - _stat(b, d) for d in draws])
    return {"difference": diff, "low": low, "high": high, "resamples": len(draws)}
