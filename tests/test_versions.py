import itertools
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml

from rules.lookup import ROOT, Exclusion, rule_for, rule_versions


def test_table():
    # @criterion C6
    vs = rule_versions()
    assert [v.id for v in vs] == ["v0", "v1", "v2", "v3", "v4"]
    for v in vs:
        assert v.first_day and v.clauses
        assert (ROOT / v.source_file).is_file()
        assert all((ROOT / s).is_file() for s in v.source_files)
        assert all(c.id.startswith(v.id + "-") for c in v.clauses)
    for a, b in itertools.pairwise(vs):
        assert a.last_day is not None and a.last_day < b.first_day
    assert vs[-1].last_day is None
    ids = [c.id for v in vs for c in v.clauses]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "d,vid",
    [
        ("2024-01-01", "v0"),
        ("2024-05-15", "v0"),
        ("2024-05-16", "v1"),
        ("2024-10-27", "v1"),
        ("2024-10-28", "v2"),
        ("2025-12-04", "v2"),
        ("2025-12-05", "v3"),
        ("2026-06-30", "v3"),
        ("2026-07-07", "v4"),
        ("2026-11-18", "v4"),
    ],
)
def test_boundaries(d, vid):
    # @criterion C6
    for renumbered in (False, True):
        assert rule_for(date.fromisoformat(d), renumbered).id == vid


def test_boundaries_gap():
    # @criterion C6
    for day in range(1, 7):
        d = date(2026, 7, day)
        ex = rule_for(d, True)
        assert isinstance(ex, Exclusion) and "2026-07-06" in ex.reason
        assert rule_for(d, False).id == "v2"


def test_boundaries_before_window():
    # @criterion C6
    assert isinstance(rule_for(date(2023, 12, 31), False), Exclusion)


_ARTIFACTS = re.compile(
    r"PO \d+ Frm \d+ Fmt \d+ Sfmt \d+(?: \d+)?"
    r"|VerDate [^ ]+ \d\d:\d\d [A-Za-z]+ \d+, \d{4} Jkt \d+"
    r"|Federal Register / Vol\. \d+, No\. \d+ / [A-Za-z]+, [A-Za-z]+ \d+, \d{4} / [A-Za-z ]+"
    r"|E:\\[A-Z]+\\[A-Z0-9]+\.SGM \S+"
    r"|\S+ on \S+ with \S+ \S+"
    r"|Jkt \d+"
)


def _norm(t):
    """Whitespace, line-end hyphenation and the PDF's page-break artifacts removed."""
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    return re.sub(" +", " ", _ARTIFACTS.sub(" ", t))


def test_clauses_verbatim():
    # @criterion C6
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext missing")
    from rules.lookup import policy_versions

    clauses = [c for v in rule_versions() for c in v.clauses]
    for carrier in ("DL", "AA"):
        clauses += [c for v in policy_versions(carrier) for c in v.clauses]
    for c in clauses:
        p = ROOT / c.source_file
        if p.suffix == ".pdf":
            src = subprocess.check_output(["pdftotext", str(p), "-"]).decode()
        else:
            import html

            src = Path(p).read_text(encoding="utf-8", errors="replace")
            src = re.sub(
                r"<script.*?</script>|<style.*?</style>", "", src, flags=re.DOTALL
            )
            src = html.unescape(re.sub(r"<[^>]+>", " ", src))
        assert c.text in _norm(src), c.id


def test_yaml_loads():
    # @criterion C6
    assert yaml.safe_load((Path(ROOT) / "rules/versions.yaml").read_text())["versions"]
