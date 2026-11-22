"""eval/delays.py on a small fixture whose counts are computed by hand (card T58): which
labels the delay reading flips, the per-agent figures after the flip, H2's interval from
eval.confirm.analyze on the overridden labels, and the document's --check."""

import json

import pytest

from eval import confirm, delays
from tests.test_confirm_report import DOT_CASE, build, case


def facts(**kw):
    return {k: {"value": v, "constructed": False} for k, v in kw.items()}


def fcase(cid, carrier, date, type_, **kw):
    return case(cid, carrier, date, type_, facts=facts(**kw))


# Three carrier-months (DL-2024-07, DL-2024-08, AA-2024-07), two or three cases each.
CASES = [
    fcase("d1", "DL", "2024-07-01", "delay_above", cancelled=False),  # flips
    fcase("d2", "DL", "2024-07-02", "delay_above", cancelled=False, travelled=False),
    fcase("c1", "DL", "2024-08-01", "canc_not_accepted", cancelled=True),
    fcase("e1", "DL", "2024-08-02", "out_of_scope", cancelled=False),
    fcase("r1", "AA", "2024-07-01", "renumbered", cancelled=False, renumbered=True),
    fcase("n1", "AA", "2024-07-02", "boundary", cancelled=False),
    case("m1", "AA", "2024-07-03", "missing_fact", facts={}),
]
LABEL = {
    "d1": "refund",  # a delay label, no "did not fly" fact: flips
    "d2": "refund",  # travelled: false keeps it
    "c1": "refund",  # a cancellation label does not flip
    "e1": "escalate",  # an escalate label does not flip
    "r1": "refund",  # renumbered: a cancellation
    "n1": "no_refund",  # already no_refund
    "m1": "refund",  # no cancelled fact: not read as a delay
}
RUNS = 10


def both(dec):
    return [dec] * RUNS


# Each agent decides RUNS times per case; 7 cases x 10 runs = 70 case-runs.
DECISIONS = {
    # the label on every case: no critical error registered; 10 wrong (d1) once flipped
    "system": {cid: both(d) for cid, d in LABEL.items()},
    # d1 and d2 no_refund: 20 wrong registered; e1 refund: 10 missed
    "naive": {
        **{cid: both(d) for cid, d in LABEL.items()},
        "d1": both("no_refund"),
        "d2": both("no_refund"),
        "e1": both("refund"),
    },
    # d1 no_refund: 10 wrong registered, none once flipped
    "cheap_strong": {
        **{cid: both(d) for cid, d in LABEL.items()},
        "d1": both("no_refund"),
    },
}
for a in DECISIONS.values():
    a["dot-p1"] = both("no_refund")

FLIPPED = {"d1": "no_refund"}


@pytest.fixture
def root(tmp_path):
    return build(tmp_path, CASES, LABEL, DECISIONS)


def test_the_flipped_set_is_the_delay_labels_without_a_did_not_fly_fact(root):
    from eval import failures

    cases, labels, _, _ = failures.load(root, root / "runs")
    assert delays.flipped(cases, labels) == FLIPPED
    # a case with travelled: false, a cancellation, an escalate label, a renumbered case, a
    # no_refund label and a case with no cancelled fact each keep their label
    assert not {"d2", "c1", "e1", "r1", "n1", "m1"} & set(delays.flipped(cases, labels))


def test_a_label_flips_only_when_every_condition_holds():
    base = fcase("x", "DL", "2024-07-01", "delay_above", cancelled=False)
    lab = {"x": {"decision": "refund"}}
    assert delays.flipped({"x": base}, lab) == {"x": "no_refund"}
    for kw in (
        {"cancelled": True},
        {"cancelled": False, "renumbered": True},
        {"cancelled": False, "travelled": False},
    ):
        assert (
            delays.flipped({"x": fcase("x", "DL", "2024-07-01", "t", **kw)}, lab) == {}
        )
    # travelled: true does not keep the label (the passenger flew)
    flew = fcase("x", "DL", "2024-07-01", "t", cancelled=False, travelled=True)
    assert delays.flipped({"x": flew}, lab) == {"x": "no_refund"}
    assert delays.flipped({"x": base}, {"x": {"decision": "escalate"}}) == {}
    assert delays.flipped({"x": base}, {}) == {}


def test_per_agent_figures_registered_and_after_the_flip(root):
    data = delays.analyze(root, root / "runs")
    assert data["flipped"] == FLIPPED
    assert data["by_type"] == {"delay_above": ["d1"]}
    got = {
        a: {
            k: {m: v[m] for m in ("wrong", "missed", "critical", "runs")}
            for k, v in x.items()
        }
        for a, x in data["agents"].items()
    }
    assert got["system"]["registered"] == {
        "wrong": 0,
        "missed": 0,
        "critical": 0,
        "runs": 70,
    }
    assert got["system"]["flipped"] == {
        "wrong": 10,
        "missed": 0,
        "critical": 10,
        "runs": 70,
    }
    assert got["naive"]["registered"] == {
        "wrong": 20,
        "missed": 10,
        "critical": 30,
        "runs": 70,
    }
    assert got["naive"]["flipped"] == {
        "wrong": 10,
        "missed": 10,
        "critical": 20,
        "runs": 70,
    }
    assert got["cheap_strong"]["registered"]["wrong"] == 10
    assert got["cheap_strong"]["flipped"]["wrong"] == 0
    assert data["agents"]["system"]["flipped"]["critical_per_100"] == pytest.approx(
        100 * 10 / 70
    )
    assert data["agents"]["naive"]["registered"]["critical_per_100"] == pytest.approx(
        100 * 30 / 70
    )


def test_h2_is_confirm_analyze_with_the_labels_overridden(root, tmp_path_factory):
    data = delays.analyze(root, root / "runs")
    # an independent route: a tree whose labels file already holds the flipped label
    other = build(
        tmp_path_factory.mktemp("flipped"),
        CASES,
        {**LABEL, **FLIPPED},
        DECISIONS,
    )
    tests = [json.loads(x) for x in (other / "cases/test/cases.jsonl").open()]
    want = confirm.analyze(other, other / "runs", tests, [DOT_CASE])["primary"]["H2"]
    got = data["h2"]["flipped"]
    assert [c["other"] for c in got["comparisons"]] == ["naive", "cheap_strong"]
    for g, w in zip(got["comparisons"], want["comparisons"], strict=True):
        for k in ("difference", "low", "high", "resamples"):
            assert g[k] == w[k]
        assert g["resamples"] == 10_000
    assert got["verdict"] == want["verdict"]
    # the points, by hand: system minus naive and minus cheap_strong, per 100 runs
    by = {c["other"]: c["difference"] for c in got["comparisons"]}
    assert by["naive"] == pytest.approx(100 * 10 / 70 - 100 * 20 / 70)
    assert by["cheap_strong"] == pytest.approx(100 * 10 / 70 - 0)
    reg = {c["other"]: c["difference"] for c in data["h2"]["registered"]["comparisons"]}
    assert reg["naive"] == pytest.approx(-100 * 30 / 70)
    assert reg["cheap_strong"] == pytest.approx(-100 * 10 / 70)


def test_nothing_registered_is_written(root):
    before = (root / "data/labels/labels.jsonl").read_text()
    delays.analyze(root, root / "runs")
    assert (root / "data/labels/labels.jsonl").read_text() == before


def test_the_limitation_paragraph_holds_the_phrase_and_the_figure(root):
    data = delays.analyze(root, root / "runs")
    text = delays.limitation(data)
    assert "did not fly" in text
    assert "ADR-0008" in text and delays.ADR in text
    assert f"{100 * 10 / 70:.2f} critical errors per 100 runs (registered 0.00)" in text
    assert "reads the 1 refund labels that rest on a delay as no_refund" in text
    assert "system minus naive -14.29 [-50.00, 0.00]" in text
    plain = delays.limitation()
    assert "did not fly" in plain and "per 100 runs" not in plain


def write_doc(root):
    doc = root / delays.DOC
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# D\n\nProse.\n\n"
        + "".join(
            f"<!-- generated:{n} -->\nold\n<!-- /generated:{n} -->\n\n"
            for n in ("flipped", "figures", "h2")
        )
    )
    return doc


# @criterion C10
def test_check_exits_1_when_the_document_differs_and_0_after_a_write(root, capsys):
    doc = write_doc(root)
    args = ["--root", str(root), "--runs-dir", str(root / "runs")]
    assert delays.main([*args, "--check"]) == 1
    assert doc.read_text().count("old") == 3  # --check writes nothing
    assert delays.main(args) == 0
    text = doc.read_text()
    assert "old" not in text and "Prose." in text
    assert "| system | 0.00 (0) | 14.29 (10) |" in text
    assert "| naive | 28.57 (20) | 14.29 (10) |" in text
    assert delays.main([*args, "--check"]) == 0
    doc.write_text(text.replace("14.29 (10)", "14.29 (11)", 1))
    assert delays.main([*args, "--check"]) == 1
    assert "differ from a rerun" in capsys.readouterr().err


def test_a_document_without_the_markers_fails(root, capsys):
    doc = root / delays.DOC
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# D\n\n<!-- generated:flipped -->\nold\n<!-- /generated:flipped -->\n"
    )
    rc = delays.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    assert rc == 1
    assert "no markers for figures, h2" in capsys.readouterr().err


def limitation_of(html):
    return html.split('<section id="limitations"')[1].split("</section>")[0]


# @criterion C10
def test_the_report_page_carries_the_limitation_and_the_system_figure(root):
    from report import confirm as rc

    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    page = (root / "runs/confirm/report.html").read_text()
    data = delays.analyze(root, root / "runs")
    figure = f"{data['agents']['system']['flipped']['critical_per_100']:.2f}"
    assert figure == "14.29"
    para = page.split("<h2>Limitation: delays and the passenger who flew</h2>")[1]
    para = para.split("</p>")[0]
    assert "did not fly" in para
    assert f"the system then makes {figure} critical errors per 100 runs" in para
    assert "(registered 0.00)" in para and "ADR-0008" in para


# @criterion C10
def test_the_site_limitations_block_carries_the_limitation_and_the_figure(root):
    from report import confirm as rc
    from report.site import ROOT, build

    rc.main(["--root", str(root), "--runs-dir", str(root / "runs")])
    out = root / "site"
    build(
        out,
        root / "runs/confirm/report.json",
        ROOT / "config/site.yaml",
        root / "runs",
        cases_path=root / "cases/test/cases.jsonl",
        root=root,
    )
    block = limitation_of((out / "method.html").read_text())
    data = delays.analyze(root, root / "runs")
    figure = f"{data['agents']['system']['flipped']['critical_per_100']:.2f}"
    assert "did not fly" in block
    assert f"the system then makes {figure} critical errors per 100 runs" in block


def test_the_site_without_a_complete_run_states_the_limitation_without_figures(root):
    from report.site import ROOT, build

    (root / "runs/confirm/complete.json").unlink(missing_ok=True)
    out = root / "site-incomplete"
    # a report.json from another build: only its presence matters to the limitations block
    (root / "runs/confirm").mkdir(parents=True, exist_ok=True)
    (root / "runs/confirm/report.json").write_text(
        (ROOT / "tests/fixtures/site/report.json").read_text()
    )
    build(
        out,
        root / "runs/confirm/report.json",
        ROOT / "config/site.yaml",
        root / "runs",
        cases_path=root / "cases/test/cases.jsonl",
        root=root,
    )
    block = limitation_of((out / "method.html").read_text())
    assert "did not fly" in block and "per 100 runs" not in block
