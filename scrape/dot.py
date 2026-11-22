"""Fetch DOT's refunds page and the FAQ / compliance-guide pages it links to.

    uv run python -m scrape.dot [--dry-run]

Writes rules/sources/dot/<file> and rules/sources/dot/manifest.json (provenance of every
file). Run it outside the sandbox; exit 1 when any page failed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from scrape.polite import (
    ARCHIVE_API,
    ARCHIVE_CDX,
    ARCHIVE_WEB,
    CACHE_ROOT,
    Failed,
    PoliteScraper,
)

START_URL = (
    "https://www.transportation.gov/individuals/aviation-consumer-protection/refunds"
)
KEYWORDS = ("faq", "frequently asked", "compliance", "guid", "refund")
EXTRA_URLS = (
    "https://www.transportation.gov/airconsumer/Small_Entity_Guide_Refund_Final_Rule",
    "https://www.transportation.gov/airconsumer/FAQ_refunds_may_12_2020",
    "https://www.transportation.gov/airconsumer/enforcement_notice_refunds_apr_3_2020",
)
PDF_MAGIC = b"%PDF"
MAX_PAGES = 10
OUT_DIR = Path("rules/sources/dot")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def select_links(html: str, start_url: str, limit: int = MAX_PAGES) -> list[str]:
    """Depth-1 links: same host, href or text contains a keyword; at most `limit`."""
    parser = _Links()
    parser.feed(html)
    host = urllib.parse.urlsplit(start_url).netloc
    chosen: list[str] = []
    for href, text in parser.links:
        if href.strip().startswith("#"):
            continue
        url = urllib.parse.urldefrag(urllib.parse.urljoin(start_url, href))[0]
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.netloc != host:
            continue
        if url == start_url or url in chosen:
            continue
        if any(k in href.lower() or k in text.lower() for k in KEYWORDS):
            chosen.append(url)
    return chosen[:limit]


def pdf_links(html: str, page_url: str) -> list[str]:
    """Same-host links of a page whose path ends in .pdf, in page order, no duplicates."""
    parser = _Links()
    parser.feed(html)
    host = urllib.parse.urlsplit(page_url).netloc
    chosen: list[str] = []
    for href, _text in parser.links:
        url = urllib.parse.urldefrag(urllib.parse.urljoin(page_url, href.strip()))[0]
        parts = urllib.parse.urlsplit(url)
        if parts.netloc != host or not parts.path.lower().endswith(".pdf"):
            continue
        if url not in chosen:
            chosen.append(url)
    return chosen


def _filename(url: str, taken: set[str], ext: str = "html") -> str:
    parts = urllib.parse.urlsplit(url)
    path = re.sub(r"\.pdf$", "", parts.path, flags=re.IGNORECASE)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-") or "index"
    name = f"{slug}.{ext}"
    n = 2
    while name in taken:
        name = f"{slug}-{n}.{ext}"
        n += 1
    taken.add(name)
    return name


def pdf_to_text(pdf: Path) -> str | None:
    """Write <stem>.txt beside the PDF with `pdftotext -layout`; its name, or None when
    pdftotext is missing or fails."""
    exe = shutil.which("pdftotext")
    if exe is None:
        print(f"pdftotext missing: no text for {pdf.as_posix()}")
        return None
    txt = pdf.with_suffix(".txt")
    try:
        subprocess.run([exe, "-layout", str(pdf), str(txt)], check=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        print(f"pdftotext failed ({e}): no text for {pdf.as_posix()}")
        return None
    return txt.name


def run(
    start_url: str = START_URL,
    out_dir: Path = OUT_DIR,
    scraper: PoliteScraper | None = None,
    extra_urls: tuple[str, ...] | list[str] = (),
) -> int:
    """Start page, then every extra URL (outside the limit), then the crawl's links and
    the PDFs the extra pages link to, sharing MAX_PAGES (crawl links first)."""
    scraper = scraper or PoliteScraper()
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    taken: set[str] = set()
    failed = False

    def get(url: str, archive_only: bool = False, linked_from: str | None = None):
        nonlocal failed
        try:
            got = scraper.fetch(url, archive_only=archive_only)
        except Failed as e:
            files.append({"requested_url": url, "via": "failed", "error": str(e)})
            print(f"failed {e} - {url}")
            failed = True
            return None
        is_pdf = got.body.startswith(PDF_MAGIC)
        name = _filename(url, taken, "pdf" if is_pdf else "html")
        (out_dir / name).write_bytes(got.body)
        entry = {"file": name, **got.record}
        if is_pdf:
            entry["text_file"] = pdf_to_text(out_dir / name)
            entry["linked_from"] = linked_from
        files.append(entry)
        print(
            f"{got.record['via']} {got.record['status']} {(out_dir / name).as_posix()} {url}"
        )
        return got

    start = get(start_url)
    from_archive = start is not None and start.record["via"] == "archive"
    extra_ok = extra_bad = 0
    queue: list[tuple[str, str | None]] = []
    extra_pages = []
    for url in extra_urls:
        got = get(url, archive_only=from_archive)
        if got is None:
            extra_bad += 1
            continue
        extra_ok += 1
        if not got.body.startswith(PDF_MAGIC):
            extra_pages.append((url, got))
    if start is not None:
        body = start.body.decode("utf-8", "replace")
        # no cut here: duplicates of extra URLs are dropped before the shared limit
        for url in select_links(body, start_url, limit=len(body)):
            queue.append((url, None))
    for url, got in extra_pages:
        for link in pdf_links(got.body.decode("utf-8", "replace"), url):
            queue.append((link, url))
    seen = {start_url, *extra_urls}
    limited = 0
    for url, parent in queue:
        if url in seen or limited >= MAX_PAGES:
            continue
        seen.add(url)
        limited += 1
        get(url, archive_only=from_archive, linked_from=parent)
    (out_dir / "manifest.json").write_text(
        json.dumps({"start_url": start_url, "files": files}, indent=2) + "\n"
    )
    bad = sum(1 for f in files if f["via"] == "failed")
    print(f"extra: {extra_ok} fetched, {extra_bad} failed")
    print(f"saved {len(files) - bad}, failed {bad}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dry-run", action="store_true", help="print the plan, make no request"
    )
    ap.add_argument("--start-url", default=START_URL)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--cache", type=Path, default=CACHE_ROOT)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--archive-api", default=ARCHIVE_API)
    ap.add_argument("--archive-web", default=ARCHIVE_WEB)
    ap.add_argument("--archive-cdx", default=ARCHIVE_CDX)
    args = ap.parse_args(argv)
    if args.dry_run:
        print(f"start URL: {args.start_url}")
        print(
            "link rule: same host, depth 1, href or link text contains one of "
            + ", ".join(repr(k) for k in KEYWORDS)
            + " (case-insensitive)"
        )
        print("extra URLs, fetched first and outside the limit:")
        for url in EXTRA_URLS:
            print(f"  {url}")
        print(
            f"limit: at most {MAX_PAGES} more files (crawl links, then PDFs linked "
            "from the extra pages)"
        )
        print("dry run: no request made")
        return 0
    scraper = PoliteScraper(
        interval=args.interval,
        cache_root=args.cache,
        archive_api=args.archive_api,
        archive_web=args.archive_web,
        archive_cdx=args.archive_cdx,
    )
    return run(args.start_url, args.out, scraper, EXTRA_URLS)


if __name__ == "__main__":
    sys.exit(main())
