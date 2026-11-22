"""The escalation tray (T51, spec T6.7): a local tool over the system agent's escalations.

Reads runs/confirm-system/{outputs,traces}; each operator action appends one line to
runs/tray/actions.jsonl and changes nothing else. The customer message of a preview is a
fixed template (no model call)."""

import html
import json
import time
from pathlib import Path

SYSTEM_RUN = Path("runs") / "confirm-system"
LOG = Path("runs") / "tray" / "actions.jsonl"
CHOICES = ("refund", "no_refund", "escalate")

AMOUNT_NOTE = "The amount comes from the ticket record; the cases carry none."
MESSAGES = {
    "refund": "Your refund request has been approved. The refund of your ticket "
    "(amount as in the ticket record) will be issued to the original form of payment.",
    "no_refund": "We reviewed your refund request and, under the rule that applies to "
    "your flight, it does not qualify for a refund.",
    "escalate": "Your request is still with our review team. We will contact you when "
    "it has been decided.",
}
REFUNDS = {
    "refund": "grants a refund; " + AMOUNT_NOTE,
    "no_refund": "grants no refund",
    "escalate": "grants no refund yet; the case stays escalated",
}


class TrayError(Exception):
    pass


def queue(root=".") -> list[dict]:
    """Every escalated case-run of the system's confirmatory run, sorted."""
    base = Path(root) / SYSTEM_RUN
    items = []
    for f in sorted((base / "outputs").glob("*.json")):
        out = json.loads(f.read_text())
        if out.get("decision") != "escalate":
            continue
        tf = base / "traces" / f.name
        trace = json.loads(tf.read_text()) if tf.exists() else []
        last = trace[-1] if trace else {}
        eng = last.get("engine") or {}
        proposal = eng.get("decision")
        if proposal not in ("refund", "no_refund"):
            proposal = None
        flight = next(
            (c["args"] for c in last.get("tool_calls", []) if c.get("tool") == "get_flight"),
            None,
        )
        items.append(
            {
                "case_id": out["case_id"],
                "run": out["run"],
                "flight": flight,
                "facts": last.get("facts") or {},
                "rule_version": out.get("rule_version"),
                "clause": out.get("clause"),
                "policy_version": out.get("policy_version"),
                "triggers": last.get("triggers") or [],
                "proposal": proposal,
            }
        )
    return items


def find(root, case_id, run) -> dict:
    for it in queue(root):
        if it["case_id"] == case_id and it["run"] == int(run):
            return it
    raise TrayError(f"no escalated case-run {case_id} run {run}")


def preview(item, decision=None) -> dict:
    """What approving (or the given decision) would do; none without a decision."""
    d = decision or item["proposal"]
    if d is None:
        return {"decision": None, "refund": "none proposed: the operator must choose",
                "message": None, "amount": AMOUNT_NOTE}
    return {"decision": d, "refund": REFUNDS[d], "message": MESSAGES[d], "amount": AMOUNT_NOTE}


def current(root, case_id, run) -> str:
    """The case-run's decision now: the last logged `after`, escalate when none."""
    log = Path(root) / LOG
    now = "escalate"
    if log.exists():
        for x in log.read_text().splitlines():
            d = json.loads(x)
            if d["case"] == case_id and d["run"] == run:
                now = d["after"]
    return now


def act(root, action, case_id, run, to=None, note="") -> dict:
    item = find(root, case_id, run)
    before = current(root, case_id, item["run"])
    if action == "approve":
        if item["proposal"] is None:
            raise TrayError("approve refused: no proposal; use change")
        after = item["proposal"]
    elif action == "change":
        if to not in CHOICES:
            raise TrayError(f"change needs --to one of {', '.join(CHOICES)}")
        after = to
    elif action == "reject":
        after = "rejected"
    else:
        raise TrayError(f"unknown action {action}")
    line = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "case": case_id,
            "run": item["run"], "action": action, "before": before, "after": after,
            "note": note}
    log = Path(root) / LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(line) + "\n")
    return line


def render(items) -> str:
    e = html.escape
    def section(it):
        p = preview(it)
        return (
            "<section><h2>{c} (run {r})</h2><p>Flight: {fl}</p><p>Rule {rv}, clause {cl}, "
            "policy {pv}</p><p>Reasons: {tr}</p><p>Facts: {fa}</p><p>Proposed decision: "
            "{pd}</p><p>Approval {rf}</p><p>Message: {m}</p></section>".format(
                c=e(it["case_id"]), r=it["run"], fl=e(" ".join(map(str, it["flight"] or [])) or "none"),
                rv=e(str(it["rule_version"])), cl=e(str(it["clause"])), pv=e(str(it["policy_version"])),
                tr=e(", ".join(it["triggers"]) or "none"), fa=e(json.dumps(it["facts"])),
                pd=e(it["proposal"] or "none"), rf=e(p["refund"]), m=e(p["message"] or "none"),
            )
        )

    test = [section(i) for i in items if not i["case_id"].startswith("dot-")]
    dot = [section(i) for i in items if i["case_id"].startswith("dot-")]
    rows = test + (["<h2>DOT external case, reported apart</h2>"] + dot if dot else [])
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Escalation tray</title></head>'
        f"<body><h1>Escalation tray</h1><p>{len(test)} escalated case-runs of the test set and {len(dot)} of the DOT external case. Read-only view: "
        "actions are taken in the operator's tool (python -m report.tray).</p>"
        + "".join(rows) + "</body></html>"
    )


def view(root, out) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "tray.html"
    path.write_text(render(queue(root)))
    return path
