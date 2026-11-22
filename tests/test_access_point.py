from datetime import date
from pathlib import Path

import yaml

from agents.system.tools import get_flight, get_policy, get_rule
from rules.lookup import ROOT, Exclusion

FIX = Path(__file__).parent / "fixtures" / "clean"


def test_flight_found_and_not_found():
    # @criterion C4
    r = get_flight("DL", 100, "2024-07-01", "ATL", root=FIX)
    assert r["destination"] == "SEA"
    assert get_flight("DL", 101, "2024-07-01", "ATL", root=FIX) is None
    assert get_flight("DL", 100, "2024-08-01", "ATL", root=FIX) is None


def test_flight_env_root(monkeypatch):
    # @criterion C4
    monkeypatch.setenv("SAY_IT_TWICE_DATA_ROOT", str(FIX))
    assert get_flight("AA", 200, "2024-07-02", "DFW")["cancelled"] == "1"


def test_rule_and_policy():
    # @criterion C4
    assert get_rule(date(2024, 7, 1), False).id == "v1"
    ids = {
        c: {
            x["id"]
            for v in yaml.safe_load((ROOT / f"rules/policies/{f}.yaml").read_text())[
                "versions"
            ]
            for x in v["clauses"]
        }
        for c, f in (("DL", "delta"), ("AA", "american"))
    }
    for carrier, other in (("DL", "AA"), ("AA", "DL")):
        p = get_policy(carrier, date(2024, 1, 15))
        assert not isinstance(p, Exclusion)
        assert p.carrier == carrier and p.clauses
        got = {c.id for c in p.clauses}
        assert got <= ids[carrier]
        assert not got & ids[other]
    assert isinstance(get_policy("XX", date(2025, 1, 1)), Exclusion)
    assert isinstance(get_policy("DL", date(1999, 1, 1)), Exclusion)
