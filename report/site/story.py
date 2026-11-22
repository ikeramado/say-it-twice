"""The story page (`site/index.html`, T61): the six blocks of docs/design/story.md, in the look
of docs/design/story-prototype.html. Every figure, answer string and quote is computed here
from the confirmatory runs (`cfg["_matrix"]`), the frozen labels, `eval.delays` (the flipped
set), `eval.fixed_rule` and the saved rule text; the prose around
them is the approved copy. No script, no model call, no request to another host.

A block whose data is missing is left out, so a build without runs still gives a page.
"""

from datetime import date

from report.confirm import esc
from report.site.matrix import LETTER, WORDS

SAY = {"refund": "yes", "no_refund": "no", "escalate": "handed it to a person"}
KEY = (("R", "refund", "refund"), ("N", "norefund", "no refund"), ("E", "escalate", "hand to a person"))
NUMBER = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
LETTERS = "RNE"
WRONG_ANSWER = {"R": "refund", "N": "no refund", "E": "hand to a person"}


def num(n):
    return NUMBER[n] if 0 <= n < len(NUMBER) else f"{n:,}"


def times(n):
    return "once" if n == 1 else f"{num(n)} times"


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def month_year(iso):
    return f"{date.fromisoformat(iso[:7] + '-01'):%B %Y}"


def letters(runs):
    return "".join(LETTER[r["decision"]] for r in runs)


def squares(s, correct=None):
    out = []
    for d in s:
        miss = " miss" if correct and d != correct else ""
        label = WRONG_ANSWER[d] + (", wrong" if miss else "")
        out.append(f'<div class="sq {d}{miss}" role="img" aria-label="{label}">{d}</div>')
    return '<div class="strip">' + "".join(out) + "</div>"


def run_block(who, s, correct=None):
    return f'<div class="run"><div class="who">{esc(who)}</div>{squares(s, correct)}</div>'


def key(correct=None):
    items = "".join(
        f'<span><i class="k{d}"></i>{esc(w)}</span>' for d, _c, w in KEY
    )
    tail = f"<span>correct answer here: {esc(correct)}</span>" if correct else ""
    return f'<div class="key">{items}{tail}</div>'


def case_by_id(m, cid):
    return next((c for c in m["cases"] if c["case_id"] == cid), None)


def fact(case, name):
    f = (case.get("facts") or {}).get(name)
    return f.get("value") if isinstance(f, dict) else f


def delay_of(case, flight):
    if flight and flight.get("arrival_delay", "") != "":
        return int(flight["arrival_delay"])
    v = fact(case, "arrival_delay_min")
    return int(v) if v is not None else None


def delay_words(n, unit="min"):
    if n is None:
        return None
    if n == 0:
        return "arrived on time"
    return f"arrived {abs(n)} {unit} " + ("late" if n > 0 else "early")


def flight_code(case):
    return f"{case['carrier']}{case['flight_number']}"


def place(cfg, case):
    s = cfg.get("story") or {}
    airline = (s.get("airlines") or {}).get(case["carrier"], case["carrier"])
    city = (s.get("cities") or {}).get(case.get("origin"), case.get("origin") or "")
    return airline, city


def record_line(case, flight):
    parts = [
        "BTS",
        f"{case['carrier']} {case['flight_number']}",
        case.get("origin") or "",
        case["flight_date"],
    ]
    status = "cancelled" if (flight or {}).get("cancelled") == "1" else "operated"
    if fact(case, "cancelled") is True:
        status = "cancelled"
    if fact(case, "renumbered") is True:
        status += ", renumbered"
    parts.append(status)
    dw = delay_words(delay_of(case, flight))
    if dw:
        parts.append(dw)
    bought = fact(case, "purchase_date")
    if bought:
        parts.append(f"bought {bought}")
    return " · ".join(esc(p) for p in parts if p)


def block_one(cfg):
    m, labels = cfg.get("_matrix"), cfg.get("_labels") or {}
    s = cfg.get("story") or {}
    c = case_by_id(m, s.get("first_case")) if m else None
    if not c or not (m["runs"].get("naive") and m["runs"].get("system")):
        return ""
    naive = letters(m["runs"]["naive"][c["case_id"]])
    system = letters(m["runs"]["system"][c["case_id"]])
    right = labels.get(c["case_id"])
    right_l = LETTER.get(right)
    airline, city = place(cfg, c)
    counts = [(d, naive.count(d)) for d in LETTERS if naive.count(d)]
    said = " and ".join(f"{SAY[next(k for k, v in LETTER.items() if v == d)]} {times(n)}" for d, n in counts)
    return (
        '<section class="col">'
        f"<p>A passenger on {esc(airline)} {esc(flight_code(c))}, {esc(city)}, "
        f"{esc(long_date(c['flight_date']))}, writes to the airline's assistant:</p>"
        f'<p class="quote">"{esc(c["message"]["text"])}"</p>'
        f'<div class="record">{record_line(c, m["flights"].get(c["case_id"]))}</div>'
        '<p class="lead lt">We asked an AI agent the same question ten times.</p>'
        '<div class="runs">'
        + run_block("AI agent, refund rules in its instructions", naive, right_l)
        + run_block("Same model, refund rules written in code", system, right_l)
        + "</div>"
        + key(WORDS.get(right))
        + f'<p class="lt">The agent said {said}. Same passenger, same flight, same words.</p>'
        "</section>"
    )


def cases_grid(m, agent):
    rows = [(c["case_id"], letters(m["runs"][agent][c["case_id"]])) for c in m["cases"]]
    rows.sort(key=lambda r: -len(set(r[1])))
    out = []
    for cid, s in rows:
        mixed = " m" if len(set(s)) > 1 else ""
        out.append(
            f'<div class="c{mixed}" role="img" aria-label="{esc(cid)}: {s}">'
            + "".join(f'<i class="{d}"></i>' for d in s)
            + "</div>"
        )
    return '<div class="cases">' + "".join(out) + "</div>"


def share_text(x):
    return f"{round(100 * x)}%"


def block_two(cfg, report):
    m = cfg.get("_matrix")
    if not m or not (m["runs"].get("naive") and m["runs"].get("system")):
        return ""
    h1 = report["primary"]["H1"]["values"]
    n_all = len(m["cases"])
    naive, system = share_text(h1["naive"]), share_text(h1["system"])
    return (
        '<section class="wide">'
        '<div class="col"><h2>It was not one case</h2>'
        f"<p>We did the same with {n_all} real flights. The plain agent gave the same answer "
        f'ten times in <span class="hl">{naive}</span> of them. With the rules in code, '
        f'<span class="hl">{system}</span>.</p></div>'
        '<div class="pair">'
        f'<div class="panel"><h3>Rules in its instructions</h3><div class="big">{naive}</div>'
        f"{cases_grid(m, 'naive')}</div>"
        f'<div class="panel"><h3>Rules in code</h3><div class="big">{system}</div>'
        f"{cases_grid(m, 'system')}</div></div>"
        '<p class="small col">Each block is one case, each square one of its ten answers. '
        "A yellow frame marks a case where the answers changed.</p></section>"
    )


def statute_html(text, highlights, cite):
    out = esc(text)
    for h in highlights:
        if h not in text:
            raise ValueError(f"statute_highlight {h!r} is not in the clause text")
        out = out.replace(esc(h), f"<mark>{esc(h)}</mark>")
    return f'<div class="law"><cite>{esc(cite)}</cite>{out}</div>'


def block_three(cfg):
    m, d = cfg.get("_matrix"), cfg.get("_delays")
    s = cfg.get("story") or {}
    c = case_by_id(m, s.get("second_case")) if m else None
    text = cfg.get("_statute")
    if not m or not d:
        return no_runs("Consistent is not the same as right", cfg)
    if not c or not text or not m["runs"].get("system"):
        return ""
    text += cfg.get("statute_continuation", "")
    system = letters(m["runs"]["system"][c["case_id"]])
    flipped = d["flipped"]
    correct = LETTER[flipped[c["case_id"]]] if c["case_id"] in flipped else None
    top = max(LETTERS, key=system.count)
    said = next(k for k, v in LETTER.items() if v == top)
    airline, city = place(cfg, c)
    dw = delay_words(delay_of(c, m["flights"].get(c["case_id"])), "minutes")
    return (
        '<section class="col"><h2>Consistent is not the same as right</h2>'
        f"<p>{esc(airline)} {esc(c['carrier'])} {esc(c['flight_number'])}, {esc(city)}, "
        f"{esc(long_date(c['flight_date']))}"
        f"{', ' + esc(dw) if dw else ''}. The passenger flew. The code version said "
        f"{esc(WORDS[said])}, {num(system.count(top))} times out of {num(len(system))}.</p>"
        + '<div class="runs">'
        + run_block("Same model, refund rules written in code", system, correct)
        + "</div><p>The law says otherwise:</p>"
        + statute_html(text, cfg.get("statute_highlight") or [], cfg["statute_cite"])
        + '<p class="lt">Our rule left that condition out. It was wrong on '
        f'<span class="hl">{len(flipped)} of {len(m["cases"])}</span> cases, the same way '
        "every time. A wrong rule in code fails consistently.</p></section>"
    )


def no_runs(heading, cfg):
    return (
        f'<section class="col"><h2>{esc(heading)}</h2>'
        f'<p>{esc(cfg["corrected"]["no_runs"])}</p></section>'
    )


def changed_runs(fixed, system_runs):
    """(runs whose corrected decision differs from the registered one, cases they belong to)."""
    runs = cases = 0
    for cid, ds in fixed["cases"].items():
        n = sum(1 for d, r in zip(ds, system_runs[cid]) if d != r["decision"])
        runs += n
        cases += bool(n)
    return runs, cases


def block_four(cfg):
    m, f = cfg.get("_matrix"), cfg.get("_fixed")
    s = cfg.get("story") or {}
    if not m or not f or not m["runs"].get("system"):
        return no_runs("With the rule fixed", cfg)
    cid = s.get("second_case")
    c = case_by_id(m, cid)
    if not c or cid not in f["cases"]:
        return ""
    total = f["total"]
    runs, cases = changed_runs(f, m["runs"]["system"])
    answers = "".join(LETTER[d] for d in f["cases"][cid])
    right = LETTER.get(f["labels"].get(cid))
    airline, _ = place(cfg, c)
    still = (
        f"{esc(airline)} {esc(flight_code(c))} still gets a refund, ten times out of ten, and is "
        "still marked wrong: the airline's own contract gives that refund at its own delay "
        "threshold, so it is a matter of the contract, not of the model."
        if right and set(answers) != {right}
        else ""
    )
    return (
        '<section class="col"><h2>With the rule fixed</h2>'
        "<p>We rewrote the rule to match the law's words and decided the same "
        f"{total} cases again, with no new model call. The fix changes only "
        f'<span class="hl">{runs}</span> runs: {num(cases)} cases that lack a fact the rule needs now go to '
        "a person instead of getting a refund. The AI still gathers the facts, explains the "
        "decision and hands unclear cases to a person. The rule decides.</p>"
        '<div class="runs">'
        + run_block(f"{flight_code(c)}, rule fixed", answers, right)
        + "</div>"
        + key(WORDS.get(f["labels"].get(cid)))
        + '<div class="after">'
        f'<div><b>{f["consistent"]} of {total}</b>cases answered the same way every time</div>'
        f'<div><b class="hl">{f["correct"]} of {total}</b>answered correctly, as before the fix</div>'
        "</div>"
        f'<p>{still}</p>'
        '<p class="small">The fix was made after we saw these results, so it is checked again '
        "on new cases each month.</p></section>"
    )


def block_five(cfg):
    items = "".join(
        f"<div><p>{esc(c['text'])}</p>"
        f'<a href="{esc(c["source_url"])}">{esc(c["source_label"])}</a></div>'
        for c in cfg.get("costs") or []
    )
    if not items:
        return ""
    return (
        '<section class="col"><h2>What a wrong answer costs</h2>'
        f'<div class="costs">{items}</div>'
        f'<p>{esc(cfg["costs_intro"])}</p></section>'
    )


def block_close(cfg):
    url = cfg["contact_url"]
    links = "".join(
        f'<a href="{esc(ev["href"])}">{esc(ev["label"])}<span>{esc(ev["sub"])}</span></a>'
        for ev in cfg["evidence"]
    )
    return (
        '<section class="col close">'
        f"<h2>{esc(cfg['close_question'])}</h2><p>{esc(cfg['offer'])}</p>"
        f'<a class="mail" href="{esc(url)}">{esc(cfg["contact_label"])}</a>'
        f'<h2 class="ev">The evidence</h2><div class="evidence">{links}</div></section>'
    )


def render_story(report, cfg):
    blocks = [
        (
            '<header class="col"><div class="byline">An audit of AI agents · US flight '
            "refunds · 2026</div><h1>Same question, ten times</h1></header>"
        ),
        block_one(cfg),
        block_two(cfg, report),
        block_three(cfg),
        block_four(cfg),
        block_five(cfg),
        block_close(cfg),
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Say It Twice</title>"
        '<link rel="stylesheet" href="style.css"></head><body><div class="story">'
        + "".join(blocks)
        + (
            f'<footer class="col"><p class="freshness">{esc(cfg["_freshness"])}</p></footer>'
            if cfg.get("_freshness")
            else ""
        )
        + "</div></body></html>"
    )
