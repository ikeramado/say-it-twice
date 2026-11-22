"""The static site (`make site`): `python -m report.site --out site/`.

`index.html` is the story (`report/site/story.py`, docs/design/story.md). The six pages of its
"The evidence" list (`PAGES`) are built here from `SCREENS`, each in the story's look with a
link back: `cases.html` (the matrix and, per run, a trace fragment under `traces/`),
`versions.html`, `break.html`, `fails.html`, `audit.html` and `method.html`. Built from
`runs/confirm/report.json` and `config/site.yaml`. No model call and no request to another
host; the one script is `matrix.SCRIPT` on `cases.html`. The style is `style.css` next to the
pages and the fonts are in `fonts/`.

To add a screen: write a function `screen_<name>(report, cfg)` returning the screen's inner
HTML (None to leave it out), and add one `Screen(id, title, level, fn, page)` line to `SCREENS`
at its place in the order. Level "owner" has no mark; every other screen has level "team" and
gets the visible "for your team" mark. A trace uses the anchor
`#trace-<agent>-<case_id>-<run>` on `cases.html`.
"""

import argparse
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from eval import delays as delay_reading
from eval import fixed_rule, metrics
from eval.confirm import NotComplete
from report.confirm import esc, fmt
from report.site.breakit import build_failures, screen_break, screen_fails
from report.site.chatbots import build_chatbots, chatbots_html, write_protocol
from report.site.eligible import build_eligible, screen_line
from report.site.freshness import freshness_line
from report.site.matrix import (
    SCRIPT,
    build_data,
    screen_matrix,
    screen_trace,
    write_traces,
)
from report.site.method import screen_adr, screen_registered
from report.site.story import render_story
from report.site.timeline import build_timeline, screen_timeline
from report.tray import TrayError
from report.tray import view as tray_view

ROOT = Path(__file__).resolve().parents[2]
TEAM_MARK = "for your team"
NAMES = {"naive": "Naive", "cheap_strong": "Cheap-strong"}

# The one stylesheet of every page: the story's look (docs/design/story-prototype.html) and the
# rules the evidence page needs, on the same dark ground.
STYLE = """\
:root{color-scheme:dark;--ground:#14161b;--panel:#1c1f26;--line:#2e333d;--text:#e9e6df;
--quiet:#9aa0ab;--mark:#f2c94c;--refund:#4fb286;--norefund:#7d8698;--escalate:#e0873a;
--wrong:#e5534b;--head:"Archivo",system-ui,sans-serif;--body:"Source Serif 4",Georgia,serif;
--data:"JetBrains Mono",ui-monospace,monospace}
body{background:var(--ground);color:var(--text);font-family:var(--body);font-size:18px;
line-height:1.6;margin:0;padding:40px max(16px,env(safe-area-inset-right,0px)) 80px
max(16px,env(safe-area-inset-left,0px))}
a{color:var(--mark)}
.col{max-width:38rem;margin:0 auto}
.wide{max-width:56rem;margin:0 auto}
.story{display:grid;gap:64px}
.byline{font-family:var(--data);font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;
color:var(--quiet);text-align:center}
h1{font-family:var(--head);font-weight:800;font-size:clamp(2.1rem,6vw,3.4rem);line-height:1.04;
text-align:center;margin:.6rem auto 0;max-width:16ch;text-wrap:balance}
h1.left{text-align:left;margin:0 0 1rem}
h2{font-family:var(--head);font-weight:700;font-size:1.5rem;line-height:1.2;margin:0 0 .6rem;
text-wrap:balance}
h2.ev{margin-top:40px}
p{margin:0 0 1rem}
.lt{margin-top:1rem}
.hl{color:var(--mark);font-weight:600}
.lead{color:var(--mark);font-weight:600}
.record{font-family:var(--data);font-size:.8rem;color:var(--quiet);border:1px solid var(--line);
background:var(--panel);padding:10px 12px;overflow-x:auto;white-space:nowrap}
.quote{border-left:3px solid var(--line);padding-left:14px;font-style:italic}
.runs{display:grid;gap:14px;margin:18px 0}
.run{display:grid;gap:6px}
.who{font-family:var(--data);font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;
color:var(--quiet)}
.strip{display:grid;grid-template-columns:repeat(10,1fr);gap:6px;max-width:30rem}
.sq{aspect-ratio:1;max-width:100%;border-radius:3px;display:grid;place-items:center;
font-family:var(--data);font-size:.8rem;font-weight:600;color:var(--ground)}
.R,.kR{background:var(--refund)}.N,.kN{background:var(--norefund)}
.E,.kE{background:var(--escalate)}
.sq.miss{outline:2px solid var(--wrong);outline-offset:2px}
.key{display:flex;flex-wrap:wrap;gap:6px 18px;font-family:var(--data);font-size:.74rem;
color:var(--quiet)}
.key i{display:inline-block;width:.8em;height:.8em;border-radius:2px;margin-right:6px;
vertical-align:-1px}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr));gap:32px;
margin-top:18px}
.panel h3{font-family:var(--data);font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--quiet);margin:0 0 4px;font-weight:600}
.big{font-family:var(--head);font-weight:800;font-size:2.4rem;line-height:1;margin-bottom:10px}
.cases{display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));gap:5px 8px}
.c{display:grid;grid-template-columns:repeat(10,1fr);gap:1px}
.c i{aspect-ratio:1;max-width:100%;display:block}
.c.m{outline:1px solid var(--mark);outline-offset:2px}
.law{background:var(--panel);border:1px solid var(--line);padding:16px 18px;font-size:1rem}
.law cite{display:block;font-family:var(--data);font-style:normal;font-size:.74rem;
color:var(--quiet);margin-bottom:8px;letter-spacing:.06em}
.law mark{background:none;color:var(--mark);font-weight:600;border-bottom:2px solid var(--mark)}
.bots{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr));gap:12px}
.bot{background:var(--panel);border:1px solid var(--line);padding:12px 14px;
font-family:var(--data);font-size:.8rem}
.bot b{display:block;font-family:var(--head);font-size:1.05rem;margin-bottom:4px}
.after,.costs{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr));gap:12px;margin:6px 0 1rem}
.after div,.costs div{background:var(--panel);border:1px solid var(--line);padding:14px 16px;font-size:.95rem}
.after b{display:block;font-family:var(--head);font-weight:800;font-size:1.7rem;line-height:1.1;margin-bottom:4px}
.costs p{margin:0 0 8px}
.costs a{font-family:var(--data);font-size:.8rem;color:var(--text)}
.figure{font-family:var(--head);font-weight:800;font-size:clamp(2.6rem,9vw,4.4rem);
line-height:1;color:var(--mark)}
.close{border-top:1px solid var(--line);padding-top:32px}
.mail{display:inline-block;font-family:var(--data);font-size:1rem;color:var(--ground);
background:var(--mark);padding:10px 14px;text-decoration:none;font-weight:600}
.mail:focus-visible{outline:3px solid var(--text);outline-offset:3px}
.evidence{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr));
gap:10px;margin-top:14px}
.evidence a{display:block;border:1px solid var(--line);padding:12px 14px;color:var(--text);
text-decoration:none;font-family:var(--head);font-weight:500}
.evidence a span{display:block;font-family:var(--body);font-size:.85rem;color:var(--quiet);
font-weight:400}
.evidence a:hover,.evidence a:focus-visible{border-color:var(--mark)}
.small{font-size:.85rem;color:var(--quiet)}
section.owner,section.team{margin:0 auto;padding-bottom:1rem;max-width:42rem;width:100%;
border-bottom:1px solid var(--line)}
.team{border-left:4px solid var(--line);padding-left:12px}
.mark{display:inline-block;background:var(--panel);border:1px solid var(--line);
padding:0 .5rem;font-size:.85rem;text-transform:uppercase}
.scroll{overflow-x:auto}
table{border-collapse:collapse;margin:.5rem 0}
th,td{border:1px solid var(--line);padding:.25rem .5rem;text-align:right}
th:first-child,td:first-child{text-align:left}
.cta{display:inline-block;padding:.6rem 1rem;background:var(--mark);color:var(--ground);
text-decoration:none;font-weight:600}
footer{margin:2rem auto;max-width:42rem;font-size:.9rem;color:var(--quiet)}
"""

# family, weight, file stem under vendor/fetched/fonts/ and site/fonts/ (latin subset, woff2)
FONTS = (
    ("Archivo", 500),
    ("Archivo", 700),
    ("Archivo", 800),
    ("Source Serif 4", 400),
    ("Source Serif 4", 600),
    ("JetBrains Mono", 400),
    ("JetBrains Mono", 600),
)


def font_file(family, weight):
    return f"{family.replace(' ', '')}-{weight}.woff2"


def copy_fonts(src, out):
    """Copy the fetched fonts and licences from `src` into `out/fonts`; return the
    `@font-face` rules of the font files that exist (a missing file leaves the system face)."""
    src, rules = Path(src), []
    if not src.is_dir():
        return ""
    fonts = out / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in sorted(src.glob("OFL-*.txt")):
        shutil.copy(f, fonts / f.name)
    for family, weight in FONTS:
        name = font_file(family, weight)
        if (src / name).is_file():
            shutil.copy(src / name, fonts / name)
            rules.append(
                f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;'
                f'font-display:swap;src:url(fonts/{name}) format("woff2")}}\n'
            )
    return "".join(rules)


def dig(obj, path):
    for part in path.split("."):
        obj = obj[part]
    return obj


def table(head, rows):
    h = "".join(f"<th>{esc(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><tr>{h}</tr>{b}</table></div>'


def screen_headline(report, cfg):
    rows = []
    for h, label in (
        ("H1", "Same answer every time"),
        ("H2", "Critical errors per 100 runs"),
    ):
        p = report["primary"][h]
        pct = h == "H1"
        k, dk = ("pct", "diff_pct") if pct else ("num", "diff")
        for c in p["comparisons"]:
            rows.append(
                [
                    f"{esc(label)}, system vs {esc(NAMES[c['other']])}",
                    fmt(p["values"]["system"], k),
                    fmt(p["values"][c["other"]], k),
                    f"{fmt(c['difference'], dk)} [{fmt(c['low'], dk)}, {fmt(c['high'], dk)}]",
                ]
            )
    cost = report["secondary"]
    for other in ("naive", "cheap_strong"):
        rows.append(
            [
                f"Dollars per correct decision, system vs {NAMES[other]}",
                fmt(cost["system"]["cost_per_correct_decision"], "usd"),
                fmt(cost[other]["cost_per_correct_decision"], "usd"),
                "",
            ]
        )
    return (
        f'<p class="moffatt"><a href="{esc(cfg["moffatt_url"])}">'
        f"{esc(' '.join(cfg['moffatt'].split()))}</a></p>"
        "<p>We ran an agent that checks the rules twice and a naive agent on the same US flight "
        "disruption cases, ten times each.</p>"
        + table(
            ["", "System", "Other agent", "Difference, 95% interval"],
            rows,
        )
        + "<p>The difference is system minus naive agent; the interval is the 95% interval of "
        "that difference.</p>"
    )


def screen_eligible(report, cfg):
    return screen_line(cfg.get("_eligible")) or None


def screen_chatbots(report, cfg):
    return chatbots_html(cfg.get("_chatbots"), cfg) or None


def screen_delays(report, cfg):
    return corrected_html(cfg.get("_delays"), cfg)


def screen_audit_files(report, cfg):
    """The audit report, the tray's view and the run-view GIF, each linked when it was built."""
    a = cfg["audit_files"]
    have = cfg.get("_audit") or {}
    parts = []
    if "report" in have:
        parts.append(
            f'<p><a href="report.html">{esc(a["report_label"])}</a> {esc(a["report_text"])}</p>'
        )
    else:
        parts.append(f"<p>{esc(a['report_missing'])}</p>")
    if "tray" in have:
        parts.append(
            f'<p><a href="tray.html">{esc(a["tray_label"])}</a> {esc(a["tray_text"])}</p>'
        )
    if "gif" in have:
        parts.append(
            f'<p><img src="run-view.gif" alt="{esc(a["gif_alt"])}" style="max-width:100%">'
            f"<br>{esc(a['gif_text'])}</p>"
        )
    return "".join(parts)


def corrected_html(data, cfg):
    """The corrected reading of the delay rule beside the registered rows: every figure from
    `eval.delays.analyze`, none typed."""
    c = cfg["corrected"]
    lesson = f"<p>{esc(c['lesson'])} <a href=\"method.html#chatbots\">{esc(c['lesson_link'])}</a></p>"
    if not data:
        return lesson + f"<p>{esc(c['no_runs'])}</p>"
    h2 = data["h2"]["flipped"]
    system = data["agents"]["system"]["flipped"]["critical_per_100"]
    rows = [
        [
            f"Critical errors per 100 runs, system vs {esc(NAMES[x['other']])}",
            fmt(system, "num"),
            fmt(h2["values"][x["other"]], "num"),
            f"{fmt(x['difference'], 'diff')} [{fmt(x['low'], 'diff')}, {fmt(x['high'], 'diff')}]",
            esc(h2["verdict"]),
        ]
        for x in h2["comparisons"]
    ]
    return (
        f"<h3>{esc(c['label'])}</h3>"
        + table(["", "System", "Other agent", "Difference, 95% interval", "H2"], rows)
        + f"<p>{esc(c['unchanged'])}</p>"
        + lesson
    )


def screen_business(report, cfg):
    b = cfg["business"]
    items = "".join(
        f"<li><strong>{esc(i['title'])}.</strong> {esc(i['text'])}</li>"
        for i in b["items"]
    )
    return f"<p>{esc(b['intro'])}</p><ul>{items}</ul>"


def screen_close(report, cfg):
    a = cfg["audit"]
    return (
        f"<p><strong>{esc(a['title'])}</strong></p><p>{esc(a['text'])}</p>"
        f'<p><a class="cta" href="{esc(cfg["contact_url"])}">{esc(cfg["contact_label"])}</a></p>'
    )


def screen_fears(report, cfg):
    agents = ("naive", "system")
    rows = []
    for f in cfg["fears"]:
        for i, m in enumerate(f["metrics"]):
            nums = [
                fmt(dig(report, m["path"].format(agent=a)), m["kind"]) for a in agents
            ]
            label = esc(m["label"])
            if m.get("gap"):
                g = dig(report, m["path"].format(agent="system")) - dig(
                    report, m["path"].format(agent="naive")
                )
                label += f"<br>Gap, system minus naive: {fmt(g, 'diff_pct')}"
            head = (
                f"<strong>{esc(f['fear'])}</strong><br>{esc(f['what_h_does'])}"
                if i == 0
                else ""
            )
            rows.append([head, label, *nums])
    return (
        table(["Fear and what the system does", "Number", "Naive", "System"], rows)
        + f"<p>{esc(' '.join(cfg['listings_limitations'].split()))}</p>"
    )


def screen_limitations(report, cfg):
    items = "".join(f"<li>{esc(t)}</li>" for t in cfg["limitations"])
    return (
        f"<ul>{items}</ul><p>{esc(delay_reading.limitation(cfg.get('_delays')))}</p>"
        f"<p>{esc(' '.join(cfg['constructed'].split()))}</p>"
        f'<p><a href="{esc(cfg["dot_refund_url"])}">DOT\'s refund page</a> states the '
        "rules this page checks agents against.</p>"
    )


@dataclass(frozen=True)
class Screen:
    id: str
    title: str
    level: str  # "owner" or "team"
    fn: Callable
    page: str  # the file of the evidence page the screen is on


# The order of each page.
SCREENS = [
    Screen("s1", "The headline", "owner", screen_headline, "audit.html"),
    Screen("audit-files", "The audit report, the tray and the run view", "team",
           screen_audit_files, "audit.html"),
    Screen("s7", "In your business", "owner", screen_business, "audit.html"),
    Screen("s8", "Does your agent give the same answer twice?", "owner", screen_close,
           "audit.html"),
    Screen("s2", "The ten runs, case by case", "owner", screen_matrix, "cases.html"),
    Screen("s3", "One run's trace", "team", screen_trace, "cases.html"),
    Screen("s4", "The rule versions over time", "team", screen_timeline, "versions.html"),
    Screen("s5", "Try to break it", "team", screen_break, "break.html"),
    Screen("s6", "Where it fails", "team", screen_fails, "fails.html"),
    Screen("delays", "The delay reading and how much it moves", "team", screen_delays,
           "fails.html"),
    Screen("registered", "What was measured, and what is exploratory", "team",
           screen_registered, "method.html"),
    Screen("fears", "What a buyer fears, and the number for each", "team", screen_fears,
           "method.html"),
    Screen("limitations", "Limitations", "team", screen_limitations, "method.html"),
    Screen("chatbots-section", "How the delay error was caught", "team", screen_chatbots,
           "method.html"),
    Screen("eligible-section", "Eligible flights and the passenger bound", "team",
           screen_eligible, "method.html"),
    Screen("adr", "ADR-0008, the delay refund", "team", screen_adr, "method.html"),
]


def render_page(report, cfg, ev):
    """The evidence page of `ev` (an entry of `cfg["evidence"]`): its screens in the story's
    look, a link back to the story above and below."""
    parts = []
    for s in SCREENS:
        if s.page != ev["href"]:
            continue
        body = s.fn(report, cfg)
        if body is None:
            continue
        title = cfg["close_question"] if s.id == "s8" else s.title
        mark = f' <span class="mark">{TEAM_MARK}</span>' if s.level == "team" else ""
        cls = "team" if s.level == "team" else "owner"
        parts.append(
            f'<section id="{s.id}" class="{cls}"><h2>{esc(title)}{mark}</h2>{body}</section>'
        )
    back = '<p><a class="mail" href="index.html">Back to the story</a></p>'
    script = f"<script>{SCRIPT}</script>" if ev["href"] == "cases.html" else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(ev['label'])}</title>"
        '<link rel="stylesheet" href="style.css"></head><body><div class="story">'
        f'<header class="col"><h1 class="left">{esc(ev["label"])}</h1>'
        f"<p>{esc(ev['sub'])}</p>{back}</header>"
        + "".join(parts)
        + f'<footer class="col">{back}This page evaluates agents against published rule text '
        f"and is not legal advice.</footer></div>{script}</body></html>"
    )


def copy_audit(out, runs_dir):
    """Put the audit's parts beside the pages: T50's `report.html`, the tray's view (T51) and
    the run-view GIF (T52); {name: file} of those that exist."""
    have = {}
    report = Path(runs_dir) / "confirm" / "report.html" if runs_dir else None
    if report and report.is_file():
        shutil.copy(report, out / "report.html")
        have["report"] = "report.html"
    if runs_dir and Path(runs_dir).name == "runs":
        try:
            tray_view(Path(runs_dir).parent, out)
            have["tray"] = "tray.html"
        except (TrayError, OSError, KeyError, ValueError):  # no system run: no tray view
            pass
    gif = ROOT / "docs/run-view.gif"
    if gif.is_file():
        shutil.copy(gif, out / "run-view.gif")
        have["gif"] = "run-view.gif"
    return have


def read_labels(root):
    """{case id: frozen decision}, empty when the labels are not under `root`."""
    try:
        rows = metrics.read_jsonl(root / metrics.LABELS)
    except OSError:
        return {}
    return {r["case_id"]: r["decision"] for r in rows}


def clause_text(root, clause_id):
    """The text of a clause of rules/versions.yaml, None when absent."""
    try:
        table = yaml.safe_load((root / "rules/versions.yaml").read_text())
    except OSError:
        return None
    for v in table["versions"]:
        for c in v.get("clauses", []):
            if c["id"] == clause_id:
                return c["text"]
    return None


def build(
    out,
    report_path,
    config_path,
    runs_dir=None,
    cases_path=None,
    flights_dir=None,
    root=None,
    chatbots_dir=None,
    fonts_dir=None,
    data_root=None,
    today=None,
):
    """With `runs_dir` the matrix and trace screens are built from `confirm-<agent>` there.
    With `fonts_dir` the fonts and their licences are copied into `out/fonts`."""
    report = json.loads(Path(report_path).read_text())
    cfg = yaml.safe_load(Path(config_path).read_text())
    if runs_dir:
        cfg["_matrix"] = build_data(
            runs_dir, cases_path or ROOT / "cases/test/cases.jsonl", report, flights_dir
        )
        cfg["_failures"] = build_failures(root or ROOT, runs_dir)
        try:
            cfg["_delays"] = delay_reading.analyze(root or ROOT, runs_dir)
        except (NotComplete, ValueError, OSError):  # runs unreadable: no figures
            cfg["_delays"] = None
        try:
            cfg["_fixed"] = fixed_rule.analyze(root or ROOT, runs_dir)
        except (NotComplete, ValueError, OSError, KeyError):  # no figures without the runs
            cfg["_fixed"] = None
    flights = Path(
        flights_dir
        or Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT) / "data/clean/flights"
    )
    cfg["_freshness"] = freshness_line(
        cfg, data_root or os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT, today
    )
    cfg["_timeline"] = build_timeline(flights)
    cfg["_eligible"] = build_eligible(flights, flights.parent / "t100")
    cdir = Path(
        chatbots_dir
        or os.environ.get("SAY_IT_TWICE_CHATBOTS")
        or (Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT) / "data/chatbots")
    )
    cfg["_chatbots"] = build_chatbots(cdir)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if cfg["_chatbots"]:
        write_protocol(out, cfg)
    cfg["_labels"] = read_labels(Path(root or ROOT))
    cfg["_statute"] = clause_text(Path(root or ROOT), cfg["statute_clause"])
    faces = copy_fonts(fonts_dir, out) if fonts_dir else ""
    (out / "style.css").write_text(faces + STYLE)
    cfg["_audit"] = copy_audit(out, runs_dir)
    write_traces(out, cfg)
    for ev in cfg["evidence"]:
        (out / ev["href"]).write_text(render_page(report, cfg, ev))
    (out / "index.html").write_text(render_story(report, cfg))
    return out / "index.html"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--report", help="default: <runs-dir>/confirm/report.json")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument(
        "--chatbots-dir", help="default: $SAY_IT_TWICE_CHATBOTS or data/chatbots"
    )
    ap.add_argument("--config", default=str(ROOT / "config" / "site.yaml"))
    a = ap.parse_args(argv)
    report = (
        Path(a.report) if a.report else Path(a.runs_dir) / "confirm" / "report.json"
    )
    if not report.exists():
        print(f"site: {report} not found (run make report-confirm)", file=sys.stderr)
        raise SystemExit(2)
    root = Path(os.environ.get("SAY_IT_TWICE_DATA_ROOT") or ROOT)
    index = build(
        a.out,
        report,
        a.config,
        a.runs_dir,
        chatbots_dir=a.chatbots_dir,
        root=root,
        fonts_dir=ROOT / "vendor/fetched/fonts",
    )
    print(f"site: {index}")
