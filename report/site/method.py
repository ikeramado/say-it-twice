"""The prose of the method page (T62): the registered study and the ADR, read from their
documents and shown as text; no figure here is typed."""

import re
from pathlib import Path

from report.confirm import esc

ROOT = Path(__file__).resolve().parents[2]
PREREG = "docs/modules/prereg.md"
ADR = "docs/decisions/0008-delay-refund-when-the-passenger-did-not-fly.md"


def section_of(path, heading):
    """The lines under the `## <heading...>` line of a Markdown file, until the next `## `."""
    lines = Path(path).read_text().splitlines()
    start = next(i for i, x in enumerate(lines) if x == f"## {heading}")
    out = []
    for x in lines[start + 1 :]:
        if x.startswith("## "):
            break
        out.append(x)
    return out


def inline(text):
    """Escaped text with the **bold** and `code` of Markdown."""
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def md_html(lines):
    """Paragraphs and (nested) bullet lists of a Markdown section as HTML."""
    out, para, depth = [], [], 0

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    for raw in lines:
        m = re.match(r"^( *)- (.*)$", raw)
        if m:
            flush()
            d = len(m.group(1)) // 4 + 1
            if d > depth:
                out.append("<ul>" * (d - depth))
            else:
                out.append("</li></ul>" * (depth - d) + "</li>")
            depth = d
            out.append(f"<li>{inline(m.group(2))}")
        elif raw.strip() == "":
            flush()
        elif depth and raw.startswith(" "):
            out.append(" " + inline(raw.strip()))
        else:
            flush()
            while depth:
                out.append("</li></ul>")
                depth -= 1
            para.append(raw.strip())
    flush()
    while depth:
        out.append("</li></ul>")
        depth -= 1
    return "".join(out)


def screen_registered(report, cfg):
    path = ROOT / PREREG
    return (
        "<p>What was measured is the study registered before the confirmatory run "
        "(tag <code>prereg-v1</code>); sections 1 and 6 of the registration follow as "
        "written. Anything not named there is exploratory and labeled so wherever it is "
        "shown.</p><h3>1. Study information</h3>"
        + md_html(section_of(path, "1. Study information"))
        + "<h3>6. Analysis plan</h3>"
        + md_html(section_of(path, "6. Analysis plan"))
    )


def screen_adr(report, cfg):
    return (
        "<p>ADR-0008 was decided after the results; nothing registered changed. Its decision, "
        "as written:</p>" + md_html(section_of(ROOT / ADR, "Decision"))
    )
