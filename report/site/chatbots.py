"""Screen 1's chatbot block (T55): popular chatbots asked by hand, counts from `eval.chatbots`.

Exploratory and outside the registered study. The numbers come from `eval.chatbots.totals`, the
quotes from the saved answers, and the protocol page is `docs/chatbots/protocol.md` in `<pre>`.
"""

import html
from pathlib import Path

from eval import chatbots as cb

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs/chatbots/protocol.md"
LINK = "chatbots/protocol.html"


def build_chatbots(chatbots_dir, questions=cb.QUESTIONS):
    """None when `chatbots_dir` holds no answer; else {"totals": [...], "quotes": {chatbot: ...}}."""
    root = Path(chatbots_dir)
    proto = cb.load(questions)
    found, _ = cb.find(root, proto)
    if not found:
        return None
    sheet = {
        (r["chatbot"], r["question"], int(r["repeat"])): r
        for r in cb.read_sheet(root) or []
    }
    quotes = {}
    for c in proto["chatbots"]:
        mine = sorted(
            (days[0], k[1], k[2], k)
            for k, days in found.items()
            if k[0] == c and root.joinpath(days[0], cb.stem(*k) + ".txt").is_file()
        )
        if not mine:
            continue
        invented = [
            m for m in mine if sheet.get(m[3], {}).get("invented_human") == "yes"
        ]
        day, q, r, _ = (invented or mine)[0]
        quotes[c] = {
            "question": q,
            "date": day,
            "invented": bool(invented),
            "text": (root / day / f"{cb.stem(c, q, r)}.txt").read_text(),
        }
    return {"totals": cb.totals(proto, root), "quotes": quotes}


def chatbots_html(data, cfg):
    if not data:
        return ""
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(t['chatbot'])}</td><td>{t['invented']} of {t['asked']}</td>"
        f"<td>{t['right']} of {t['asked']}</td><td>{e(', '.join(t['dates']))}</td></tr>"
        for t in data["totals"]
    )
    quotes = "".join(
        f"<h4>{e(c)}, {e(q['question'])}, asked {e(q['date'])} "
        f"({'marked invented' if q['invented'] else 'its first answer'})</h4>"
        f'<blockquote style="white-space: pre-wrap">{e(q["text"])}</blockquote>'
        for c, q in data["quotes"].items()
    )
    return (
        '<div class="chatbots" id="chatbots">'
        f"<h3>{e(cfg['chatbots_title'])}</h3>"
        f"<p><strong>{e(cfg['chatbots_label'])}</strong>. {e(cfg['chatbots_text'])}</p>"
        '<div class="scroll"><table><tr><th>Chatbot</th>'
        "<th>Answers that invented an entitlement or amount</th>"
        "<th>Right decisions</th><th>Asked on</th></tr>"
        f"{rows}</table></div>{quotes}"
        f'<p><a href="{LINK}">{e(cfg["chatbots_protocol_label"])}</a></p></div>'
    )


def write_protocol(out, cfg, protocol=PROTOCOL):
    path = Path(out) / LINK
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(cfg['chatbots_protocol_label'])}</title>"
        '<link rel="stylesheet" href="../style.css"></head><body>'
        f'<pre style="white-space: pre-wrap">{html.escape(Path(protocol).read_text())}</pre>'
        '<p><a href="../method.html">Back to the method page</a></p></body></html>'
    )
    return path
