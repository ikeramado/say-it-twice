"""DOT guidance examples as held-out test cases (T10, task T2.2).

`python -m cases.dot` reads the saved pages in rules/sources/dot/, finds the paragraphs that
give a worked example, and writes: usable ones to cases/test/dot/cases.jsonl, DOT's stated
answer to data/labels/dot/answers.jsonl, the others (with the reason) to
cases/test/dot/unusable.md. A paragraph is a real-flight example (T10: a flight date, a flight
and a stated answer) or else a hypothetical one (T18: an event and DOT's answer, marked
`hypothetical: true`). Each document's rule version comes from the fixed `DOCUMENT_DATES`
mapping by file stem; examples from a document dated before the study window, or with no
dated version, are listed as unusable. Nothing is guessed.

It reads every .html and .txt (the text pdftotext wrote beside a PDF) in the folder.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "rules" / "sources" / "dot"
OUT = ROOT / "cases" / "test" / "dot"
LABELS = ROOT / "data" / "labels" / "dot"

MARKER = re.compile(
    r"\b(for example|for instance|suppose|example)\b|\be\.g\.", re.IGNORECASE
)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\b")
FLIGHT = re.compile(
    r"\b([A-Z0-9]{2})\s?(\d{1,4})\b(?=\s+(?:from|to|on|was|departed|arrived))"
)
ANSWER = re.compile(
    r"\b(is|are|would be) (not )?entitled to (a )?refund\b", re.IGNORECASE
)

EVENT = re.compile(r"\b(cancel|delay|change|schedul)\w*", re.IGNORECASE)
NO_REFUND = re.compile(
    r"\bis not entitled to a refund\b|\bnot required to (provide|issue) a refund\b"
    r"|\bneed not refund\b",
    re.IGNORECASE,
)
REFUND = re.compile(
    r"\bmust (provide|issue|give) a refund\b|\bis entitled to a refund\b"
    r"|\bmust refund\b|\bowes a refund\b",
    re.IGNORECASE,
)
CHOICE = re.compile(r"\b(does not accept|decline|accept|rebook)\w*", re.IGNORECASE)
NUMBER = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
SIZE = re.compile(
    rf"\b(?:(?:{NUMBER})[- ](?:hours?|minutes?)|significant(?:ly)? (?:delay|change)\w*)",
    re.IGNORECASE,
)

# Topics the pitch's No-gos leave out (T19): checked on candidate paragraphs before classify.
OUT_OF_SCOPE = re.compile(
    r"\b(bag|bags|baggage|luggage|ancillary|wi-?fi|meal|hotel)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_REASON = "out of scope (pitch, No-gos)"

GUIDE = "airconsumer-Small-Entity-Guide-Refund-Final-Rule"
BEFORE = "before the study window (ADR-0001)"
NO_VERSION = "no dated version"
# File stem -> rule version (ADR-0001) or BEFORE; a file whose manifest linked_from is the
# guide's URL also maps to v2. Any other stem: NO_VERSION.
DOCUMENT_DATES = {
    GUIDE: "v2",
    "airconsumer-FAQ-refunds-may-12-2020": BEFORE,
    "airconsumer-enforcement-notice-refunds-apr-3-2020": BEFORE,
}


class _Paras(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paras, self._buf, self._depth, self._skip = [], [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "li"):
            self._depth += 1
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in ("p", "li") and self._depth > 0:
            self._depth -= 1
            if self._depth == 0:
                text = " ".join("".join(self._buf).split())
                if text:
                    self.paras.append(text)
                self._buf = []

    def handle_data(self, data):
        if self._depth > 0 and not self._skip:
            self._buf.append(data)


def paragraphs(path):
    """The numbered paragraphs (p and li elements, from 1) of one saved page."""
    p = _Paras()
    p.feed(Path(path).read_text(encoding="utf-8", errors="replace"))
    return list(enumerate(p.paras, 1))


def classify(text):
    """(case_parts, None) for a usable example, (None, reason) otherwise."""
    missing = []
    d = DATE.search(text)
    f = FLIGHT.search(text)
    a = ANSWER.search(text)
    if not d:
        missing.append("no flight date")
    if not f:
        missing.append("no flight (carrier and number)")
    if not a:
        missing.append("no stated answer")
    if missing:
        return None, "; ".join(missing)
    month = MONTHS.split("|").index(d.group(1)) + 1
    return {
        "flight_date": f"{int(d.group(3)):04d}-{month:02d}-{int(d.group(2)):02d}",
        "carrier": f.group(1),
        "flight_number": f.group(2),
        "answer": "no_refund" if a.group(2) else "refund",
    }, None


def text_paragraphs(path):
    """(n, text, page) for the blank-line paragraphs of a .txt, n from 1; page counted
    from form feeds (1 + those before the paragraph)."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    out, n, pos = [], 0, 0
    for block in re.split(r"(\n[ \t]*\n|\f)", raw):
        text = " ".join(block.split())
        if text and not re.fullmatch(r"\n[ \t]*\n|\f", block):
            n += 1
            lead = len(block) - len(block.lstrip())
            out.append((n, text, 1 + raw[: pos + lead].count("\f")))
        pos += len(block)
    return out


def hypothetical(text):
    """(parts, None) for an event with DOT's answer, (None, reason) otherwise."""
    event = EVENT.search(text)
    answer = "no_refund" if NO_REFUND.search(text) else None
    if answer is None and REFUND.search(text):
        answer = "refund"
    if not event or not answer:
        missing = ([] if event else ["no event named"]) + (
            [] if answer else ["no stated answer"]
        )
        return None, "; ".join(missing)
    size = SIZE.search(text)
    choice = CHOICE.search(text)
    return {
        "event": event.group(0).lower(),
        "size": size.group(0) if size else None,
        "passenger_choice": choice.group(0).lower() if choice else None,
        "answer": answer,
    }, None


def _versions(src):
    """File stem -> version, from DOCUMENT_DATES and the manifest's linked_from."""
    versions = dict(DOCUMENT_DATES)
    manifest = Path(src) / "manifest.json"
    if manifest.exists():
        files = json.loads(manifest.read_text()).get("files", [])
        guide = [
            f["requested_url"] for f in files if Path(f.get("file", "")).stem == GUIDE
        ]
        for f in files:
            if f.get("linked_from") and f["linked_from"] in guide:
                versions[Path(f["file"]).stem] = "v2"
    return versions


def _documents(src):
    for doc in sorted(Path(src).iterdir()):
        if doc.suffix == ".html":
            yield doc, [(n, t, None) for n, t in paragraphs(doc)]
        elif doc.suffix == ".txt":
            from_pdf = doc.with_suffix(".pdf").exists()
            yield (
                doc,
                [(n, t, p if from_pdf else None) for n, t, p in text_paragraphs(doc)],
            )


def build(src=SRC):
    cases, answers, unusable = [], [], []
    versions = _versions(src)
    for doc, paras in _documents(src):
        version = versions.get(doc.stem, NO_VERSION)
        for n, text, page in paras:
            if not (MARKER.search(text) or EVENT.search(text)):
                continue
            ref = f"rules/sources/dot/{doc.name} paragraph {n}"
            if OUT_OF_SCOPE.search(text):
                unusable.append((ref, text, OUT_OF_SCOPE_REASON))
                continue
            real, real_reason = classify(text)
            hypo, hypo_reason = (None, None) if real else hypothetical(text)
            if real is None and hypo is None:
                # T10's rule: every marker paragraph is a case or is listed
                reason = real_reason if MARKER.search(text) else hypo_reason
                if version in (BEFORE, NO_VERSION):
                    if not MARKER.search(text):
                        continue
                    reason = f"{reason}; {version}"
                unusable.append((ref, text, reason))
                continue
            if version in (BEFORE, NO_VERSION):
                unusable.append((ref, text, version))
                continue
            cid = f"dot-{doc.stem}-p{n}"
            citation = {"file": f"rules/sources/dot/{doc.name}", "paragraph": n}
            if page is not None:
                citation["page"] = page
            case = {
                "case_id": cid,
                "source": "dot",
                "hypothetical": real is None,
                "bts_flight": None,
                "rule_version": version,
                "citation": citation,
                "type": "dot_example",
            }
            if real:
                answer = real["answer"]
                case.update(
                    carrier=real["carrier"],
                    flight_number=real["flight_number"],
                    flight_date=real["flight_date"],
                    facts={"example_text": {"value": text, "from": "dot"}},
                )
            else:
                answer = hypo["answer"]
                facts = {k: hypo[k] for k in ("event", "size", "passenger_choice")}
                facts["example_text"] = text
                case.update(
                    carrier=None,
                    flight_number=None,
                    flight_date=None,
                    facts={k: {"value": v, "from": "dot"} for k, v in facts.items()},
                    message=text,
                )
            cases.append(case)
            answers.append(
                {
                    "case_id": cid,
                    "answer": answer,
                    "rule_version": version,
                    "citation": citation,
                }
            )
    return cases, answers, unusable


def write(src=SRC, out=OUT, labels=LABELS):
    cases, answers, unusable = build(src)
    out, labels = Path(out), Path(labels)
    out.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    dump = lambda rows: "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    (out / "cases.jsonl").write_text(dump(cases))
    (labels / "answers.jsonl").write_text(dump(answers))
    lines = ["# DOT examples left out of the test set", ""]
    lines += [f"- {ref}: {reason}\n  > {text[:200]}" for ref, text, reason in unusable]
    if not unusable:
        lines.append("None found.")
    (out / "unusable.md").write_text("\n".join(lines) + "\n")
    return len(cases), len(unusable)


if __name__ == "__main__":
    print("usable {}, unusable {}".format(*write()))
