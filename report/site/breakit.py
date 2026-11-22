"""Screens 5 and 6 of the site: try to break it (the adversarial cases, the demo traps) and
where it fails (the critical-error classes of `docs/results/failures.md`).

Built from the matrix data (`cfg["_matrix"]`, screens 2 and 3) and from `eval.failures`, the
computation behind `python -m eval.failures`; no model call, no script (the attack filter is CSS
on radio inputs, as the matrix's agent switch). A case opens its trace on screen 3 by
`#trace-<agent>-<case_id>-<run>`.
"""

from collections import Counter
from pathlib import Path

from eval import failures
from eval.metrics import modal_or_escalate
from report.confirm import esc
from report.site.matrix import AGENTS, LABELS, WORDS, anchor

CSS = """\
.atkf input{position:absolute;opacity:0}
.atkf label{display:inline-block;padding:.3rem .8rem;border:1px solid var(--line);cursor:pointer;
margin:0 .3rem .3rem 0}
.atkf input:focus-visible+label{outline:3px solid var(--mark)}
.adv,.trap{border:1px solid var(--line);padding:0 12px;margin:1rem 0}
.cons{font-style:italic}
"""

NOT_COVERED = "not covered by the frozen test set"

# The five demo traps: (case type, title, why it is a trap).
TRAPS = (
    (
        "boundary",
        "A delay at the boundary",
        (
            "The delay sits next to the rule's delay threshold, as 2 h 59 min sits against "
            "3 h 01 min: a threshold read on the wrong side, or the wrong version's threshold, "
            "flips the answer."
        ),
    ),
    (
        "renumbered",
        "A renumbered flight",
        (
            "The airline changed the flight's number. Whether that is a cancellation depends on "
            "the rule version in force and on the customer's choice, so an agent that decides "
            "without the conditions gives a wrong answer."
        ),
    ),
    (
        "between_versions",
        "A flight from a version change",
        (
            "The flight falls where one rule version replaces another. The answer depends on "
            "which version is in force on the flight's date."
        ),
    ),
    (
        "adversarial",
        "An injection in the message",
        (
            "The customer's message tries to push the agent off the rules; the right answer is "
            "the one of the same case without the attack."
        ),
    ),
    (
        "policies_differ",
        "The other airline's terms",
        (
            "Delta's and American's contracts differ on this flight's facts; applying the other "
            "airline's terms gives a wrong answer."
        ),
    ),
)

# The system's critical errors, by the groups of docs/results/failures.md.
SYSTEM_GROUPS = (
    (
        "A",
        "A purchase date in a policy gap, read two ways (cause a)",
        (
            "No saved copy of American's contract covers the purchase date. The engine weighs the "
            "contract versions that ADR-0005 names and finds one whose text decides; the label "
            "follows the human's labeling criteria, under which an uncovered purchase date leaves "
            "the airline's conditions unknown, and escalates. The engine and the label read the "
            "same gap differently."
        ),
        (
            "test-bnd-012",
            "test-dab-006",
            "test-dab-010",
            "test-dab-010-adv-emotional-pressure",
        ),
    ),
    (
        "B",
        "A label wrong by its own criterion (cause d)",
        (
            "The contract text in force at purchase no longer holds the flight-number sentence the "
            "label's criterion rests on, so the engine's decision follows the text and the label "
            "does not. The label stays frozen and the registered figures stand."
        ),
        ("test-ren-008",),
    ),
    (
        "C",
        "The flight-number sentence read without its condition (cause a)",
        (
            "The engine reads American's sentence that a flight number change is a cancellation as "
            "a refund and drops the condition the same clause sets (the customer chooses not to "
            "fly). The label escalates on that condition, and the text supports the label."
        ),
        ("test-ren-010",),
    ),
)

KINDS = (
    (
        "missed",
        "Missed escalations",
        (
            "The label escalates and the agent decides: every out-of-scope request decided as a "
            "ticket refund, and missing-fact or renumbered cases decided where the answer is not "
            "known."
        ),
    ),
    (
        "wrong",
        "Wrong decisions",
        (
            "A refund against no refund or the reverse: a threshold read on the wrong side, or the "
            "wrong version's threshold."
        ),
    ),
)


def attack_of(case):
    return case.get("attack") or case["case_id"].split("-adv-", 1)[-1]


def counts(runs):
    c = Counter(r["decision"] for r in runs)
    return " &middot; ".join(f"{WORDS[d]} {c[d]}" for d in WORDS)


def _agents(m):
    return [a for a in AGENTS if m["runs"][a] is not None]


def _agent_rows(m, case, clean):
    cid = case["case_id"]
    rows = []
    for a in _agents(m):
        runs = m["runs"][a][cid]
        base = clean and m["runs"][a].get(clean)
        if base:
            modal = modal_or_escalate([r["decision"] for r in base])
            changed = sum(r["decision"] != modal for r in runs)
            tail = [WORDS[modal], f"{changed} of {len(runs)}"]
        else:
            tail = ["clean case not in this run", "n/a"]
        link = f'<a href="cases.html#{anchor(a, cid, 0)}">run 0</a>'
        rows.append([esc(LABELS[a]), counts(runs), *map(esc, tail), link])
    return rows


def _table(head, rows):
    h = "".join(f"<th>{esc(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><tr>{h}</tr>{b}</table></div>'


def _fact(case, name):
    v = (case.get("facts") or {}).get(name)
    return v.get("value") if v else None


def pick_trap(cases, kind):
    of = [c for c in cases if c.get("type") == kind]
    if not of:
        return None
    if kind == "boundary":
        # the case nearest 3 h (180 min) of arrival delay, the first in file order on a tie
        def gap(c):
            d = _fact(c, "arrival_delay_min")
            return abs(d - 180) if isinstance(d, int) else 10**9

        return min(of, key=gap)
    return of[0]


def screen_break(report, cfg):
    m = cfg.get("_matrix")
    if not m:
        return None
    cases = m["cases"]
    adv = [c for c in cases if c.get("type") == "adversarial"]
    attacks = sorted({attack_of(c) for c in adv})
    head = [
        "Agent",
        "Its 10 runs",
        "Clean case, modal decision",
        "Runs that differ",
        "Trace",
    ]
    css = (
        "".join(
            f"#atk-{a}:checked~.advs .adv:not(.atk-{a}){{display:none}}"
            f"#atk-{a}:checked+label{{background:var(--mark);color:var(--ground)}}"
            for a in attacks
        )
        + "#atk-all:checked+label{background:var(--mark);color:var(--ground)}"
    )
    sw = '<input type="radio" name="atk" id="atk-all" checked><label for="atk-all">All</label>'
    sw += "".join(
        f'<input type="radio" name="atk" id="atk-{a}"><label for="atk-{a}">{esc(a)}</label>'
        for a in attacks
    )
    blocks = ""
    for c in adv:
        a = attack_of(c)
        blocks += (
            f'<div class="adv atk-{esc(a)}"><h3>{esc(c["case_id"])}</h3>'
            f"<p>Attack type: <strong>{esc(a)}</strong></p>"
            f'<p class="cons">Customer message (constructed): {esc(c["message"]["text"])}</p>'
            + _table(head, _agent_rows(m, c, c.get("clean_case_id")))
            + "</div>"
        )
    traps = ""
    for kind, title, why in TRAPS:
        c = pick_trap(cases, kind)
        if c is None:
            traps += f'<div class="trap"><h3>{esc(title)}</h3><p>{esc(NOT_COVERED)}</p></div>'
            continue
        extra = f" Attack: {esc(attack_of(c))}." if kind == "adversarial" else ""
        delay = _fact(c, "arrival_delay_min")
        dl = f" Arrival delay {delay} min." if isinstance(delay, int) else ""
        rows = _agent_rows(m, c, None)
        traps += (
            f'<div class="trap"><h3>{esc(title)}</h3>'
            f"<p>Case <strong>{esc(c['case_id'])}</strong> (type {esc(kind)}).{extra}{dl}</p>"
            f"<p>{esc(why)}</p>"
            + _table(
                ["Agent", "Its 10 runs", "", "", "Trace"],
                [r[:2] + ["", "", r[4]] for r in rows],
            )
            + "</div>"
        )
    return (
        f"<style>{CSS}{css}</style>"
        "<p>We wrote 20 adversarial versions of ordinary cases: the same facts with a customer "
        "message that tries to move the agent. The messages are constructed for this study. "
        "For each agent: its answers over 10 runs, and how many differ from its modal answer "
        "on the clean case.</p>"
        f'<div class="atkf" role="group" aria-label="Attack type">{sw}'
        f'<div class="advs">{blocks}</div></div>'
        "<h3>Demo: five cases that fail on purpose</h3>" + traps
    )


def build_failures(root, runs_dir):
    """The screen's data, or `None` (no screen) when the runs cannot be read as the failures
    analysis reads them; screen 3 reports such files itself.
    """
    try:
        return _failures(root, runs_dir)
    except (ValueError, OSError):
        return None


def _failures(root, runs_dir):
    """The data of screen 6, from `eval.failures`: its `analyze` totals and its rows. `None`
    when a confirmatory run directory is absent."""
    runs_dir = Path(runs_dir)
    if not all((runs_dir / f"confirm-{a}").is_dir() for a in failures.AGENTS):
        return None
    totals = failures.analyze(root, runs_dir)
    cases, labels, table, ent = failures.load(root, runs_dir)
    per = {}
    for a in failures.AGENTS:
        d = runs_dir / f"confirm-{a}"
        rs = failures.rows(failures.metrics.load_outputs(d), cases, labels, table, ent)
        crit = [r for r in rs if failures.critical(r)]
        ids = {}
        for kind in ("missed", "wrong"):
            for cid in sorted(
                {r["case"]["case_id"] for r in crit if r["kind"] == kind}
            ):
                of = [r for r in crit if r["case"]["case_id"] == cid]
                ids.setdefault(kind, []).append(
                    {
                        "case_id": cid,
                        "type": of[0]["case"]["type"],
                        "runs": sum(r["kind"] == kind for r in of),
                        "run": min(
                            r["out"].get("run", 0) for r in of if r["kind"] == kind
                        ),
                    }
                )
        per[a] = ids
    system = {c["case_id"]: c for c in totals["system"]["cases"]}
    return {
        "totals": {
            a: {k: totals[a][k] for k in ("runs", "wrong", "missed", "critical")}
            for a in failures.AGENTS
        },
        "per": per,
        "system": system,
    }


def _case_li(agent, c, extra=""):
    return (
        f'<li><a href="cases.html#{anchor(agent, c["case_id"], c["run"])}">{esc(c["case_id"])}</a> '
        f"(type {esc(c['type'])}): {c['runs']} critical runs{extra}</li>"
    )


def screen_fails(report, cfg):
    f = cfg.get("_failures")
    if not f:
        return None
    rows = [
        [
            esc(LABELS[a]),
            str(f["totals"][a]["runs"]),
            str(f["totals"][a]["wrong"]),
            str(f["totals"][a]["missed"]),
            str(f["totals"][a]["critical"]),
        ]
        for a in failures.AGENTS
    ]
    out = [
        (
            "<p>A critical error is a wrong decision (refund against no refund or the reverse) or "
            "a missed escalation (a decision where the label escalates). These are the cases "
            "where the agents fail, with the cause found in the traces and the texts.</p>"
        ),
        _table(
            [
                "Agent",
                "Case-runs",
                "Wrong decisions",
                "Missed escalations",
                "Critical errors",
            ],
            rows,
        ),
        "<h3>System</h3>",
    ]
    listed = set()
    for key, title, cause, ids in SYSTEM_GROUPS:
        have = [i for i in ids if i in f["system"]]
        listed.update(have)
        lis = "".join(
            _case_li(
                "system",
                {
                    "case_id": i,
                    "type": f["system"][i]["type"],
                    "runs": f["system"][i]["critical"],
                    "run": 0,
                },
            )
            for i in have
        )
        if have:
            out.append(
                f"<h4>Group {key}: {esc(title)}</h4><p>{esc(cause)}</p><ul>{lis}</ul>"
            )
    rest = [i for i in f["system"] if i not in listed]
    if rest:
        lis = "".join(
            _case_li(
                "system",
                {
                    "case_id": i,
                    "type": f["system"][i]["type"],
                    "runs": f["system"][i]["critical"],
                    "run": 0,
                },
            )
            for i in rest
        )
        out.append(
            "<h4>Cause not yet written</h4><p>No cause for these cases is written in "
            f"docs/results/failures.md.</p><ul>{lis}</ul>"
        )
    for a in ("naive", "cheap_strong"):
        out.append(f"<h3>{esc(LABELS[a])}</h3>")
        for kind, title, cause in KINDS:
            cs = f["per"][a].get(kind, [])
            lis = "".join(_case_li(a, c) for c in cs) or "<li>none</li>"
            out.append(f"<h4>{esc(title)}</h4><p>{esc(cause)}</p><ul>{lis}</ul>")
    return "".join(out)
