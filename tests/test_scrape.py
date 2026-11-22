"""The polite scraper, tested against a local HTTP server (no real host, no real sleep)."""

import gzip
import hashlib
import itertools
import json
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scrape import dot
from scrape.polite import USER_AGENT, Failed, PoliteScraper


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class Site:
    """routes: path -> (status, body, headers) or a list of those (popped in order, last
    repeats). Records (path, user_agent, clock time) of every request."""

    def __init__(self, clock):
        self.routes = {}
        self.log = []
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                site.log.append((self.path, self.headers.get("User-Agent"), clock()))
                route = site.routes.get(self.path)
                if route is None and self.path.startswith("/web/"):
                    route = site.routes.get("/web/*")
                if isinstance(route, list):
                    route = route.pop(0) if len(route) > 1 else route[0]
                status, body, headers = route or (404, b"", {})
                if callable(body):
                    body = body(self.path)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def paths(self):
        return [p for p, _, _ in self.log]

    def archive(self, url_path, body=b"ARCHIVED", ts="20240102030405"):
        url = self.base + url_path
        self.routes["/wayback/available?url=" + urllib.parse.quote(url, safe="")] = (
            200,
            json.dumps(
                {
                    "archived_snapshots": {
                        "closest": {"available": True, "timestamp": ts, "url": "x"}
                    }
                }
            ).encode(),
            {},
        )
        self.routes["/web/*"] = (200, body, {})


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    site = Site(clock)
    yield clock, site, tmp_path
    site.server.shutdown()


def scraper(env, **kw):
    clock, site, tmp = env
    kw.setdefault("interval", 0)
    return PoliteScraper(
        clock=clock,
        sleep=clock.sleep,
        wall=lambda: "2026-11-18T00:00:00Z",
        cache_root=tmp / "cache",
        archive_api=site.base + "/wayback/available",
        archive_web=site.base,
        archive_cdx=site.base + "/cdx",
        backoff=2.0,
        **kw,
    )


def ok(body=b"<html>page</html>"):
    return (200, body, {})


def test_user_agent_is_honest_and_constant(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/a"] = ok()
    site.routes["/b"] = ok()
    s = scraper(env)
    s.fetch(site.base + "/a")
    s.fetch(site.base + "/b")
    agents = {ua for _, ua, _ in site.log}
    assert agents == {USER_AGENT}
    assert "say-it-twice" in USER_AGENT and "Mozilla" not in USER_AGENT


def test_robots_disallow_goes_to_archive(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /blocked\n", {})
    site.archive("/blocked", b"FROM ARCHIVE")
    got = scraper(env).fetch(site.base + "/blocked")
    assert "/blocked" not in site.paths()
    assert got.body == b"FROM ARCHIVE"
    assert got.record["via"] == "archive"
    assert got.record["archive_timestamp"] == "20240102030405"


def test_robots_unreadable_counts_as_disallow(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (403, b"", {})
    site.archive("/p")
    got = scraper(env).fetch(site.base + "/p")
    assert "/p" not in site.paths() and got.record["via"] == "archive"


def test_rate_spacing_between_requests_to_one_host(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/a"] = ok()
    site.routes["/b"] = ok()
    s = scraper(env, interval=3.0)
    s.fetch(site.base + "/a")
    s.fetch(site.base + "/b")
    times = [t for _, _, t in site.log]
    assert len(times) == 3
    assert all(b - a >= 3.0 for a, b in itertools.pairwise(times))
    assert PoliteScraper().interval == 3.0


def test_retry_and_fallback(env):
    clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"", {})
    # 503 twice with Retry-After, then fine
    site.routes["/flaky"] = [
        (503, b"", {"Retry-After": "7"}),
        (429, b"", {}),
        ok(b"GOOD"),
    ]
    got = scraper(env).fetch(site.base + "/flaky")
    assert got.record["via"] == "source" and site.paths().count("/flaky") == 3
    assert clock.sleeps == [7.0, 4.0]  # Retry-After honoured; else growing backoff
    # never recovers: 1 + 3 retries, waits grow, then archive
    clock.sleeps.clear()
    site.routes["/down"] = (503, b"", {})
    site.archive("/down")
    got = scraper(env).fetch(site.base + "/down")
    assert site.paths().count("/down") == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]
    assert got.record["via"] == "archive"
    # 403: not retried, archive
    site.routes["/forbidden"] = (403, b"no", {})
    site.archive("/forbidden")
    got = scraper(env).fetch(site.base + "/forbidden")
    assert site.paths().count("/forbidden") == 1 and got.record["via"] == "archive"


def test_cache_serves_second_fetch_without_request(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/a"] = ok(b"ONCE")
    s = scraper(env)
    first = s.fetch(site.base + "/a")
    n = len(site.log)
    second = scraper(env).fetch(
        site.base + "/a"
    )  # a fresh scraper reads the disk cache
    assert len(site.log) == n
    assert second.body == b"ONCE" and second.record == first.record


def test_provenance_fields_and_hash(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(b'<a href="/faq">FAQ</a>')
    site.routes["/faq"] = ok(b"faq page")
    out = tmp / "out"
    code = dot.run(site.base + "/refunds", out, scraper(env))
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["start_url"] == site.base + "/refunds"
    assert len(manifest["files"]) == 2
    for e in manifest["files"]:
        for k in (
            "file",
            "requested_url",
            "final_url",
            "fetched_at",
            "status",
            "sha256",
            "via",
        ):
            assert k in e
        assert e["via"] == "source"
        assert hashlib.sha256((out / e["file"]).read_bytes()).hexdigest() == e["sha256"]


def test_dry_run_makes_no_request(env, capsys):
    _clock, site, _ = env
    assert dot.main(["--dry-run", "--start-url", site.base + "/refunds"]) == 0
    text = capsys.readouterr().out
    assert site.base + "/refunds" in text and "10" in text and "faq" in text
    assert site.log == []
    r = subprocess.run(
        [sys.executable, "-m", "scrape.dot", "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "individuals/aviation-consumer-protection/refunds" in r.stdout


def test_crawl_limits_and_filters(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    links = [f'<a href="/page{i}">Compliance guide {i}</a>' for i in range(11)]
    links.append('<a href="/faq-x">x</a>')  # 12th match by href only -> over the limit
    links.append('<a href="/other">About us</a>')  # neither faq nor guide
    links.append('<a href="http://example.invalid/faq">FAQ elsewhere</a>')  # other host
    site.routes["/refunds"] = ok("".join(links).encode())
    for i in range(11):
        site.routes[f"/page{i}"] = ok(f"p{i}".encode())
    site.routes["/faq-x"] = ok(b"x")
    out = tmp / "out"
    code = dot.run(site.base + "/refunds", out, scraper(env))
    assert code == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert len(files) == 11  # start + 10
    fetched = [e["requested_url"] for e in files[1:]]
    assert len(fetched) == 10
    assert all(u.startswith(site.base) and ("page" in u or "faq" in u) for u in fetched)
    assert "/other" not in " ".join(site.paths())
    assert not any("example.invalid" in p for p in site.paths())
    for e in files:
        assert hashlib.sha256((out / e["file"]).read_bytes()).hexdigest() == e["sha256"]


def test_archive_missing_marks_failed_and_exits_1(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(b'<a href="/faq">FAQ</a>')
    site.routes["/faq"] = (403, b"", {})
    # the availability API knows no snapshot of /faq
    api = "/wayback/available?url=" + urllib.parse.quote(site.base + "/faq", safe="")
    site.routes[api] = (200, b'{"archived_snapshots": {}}', {})
    out = tmp / "out"
    s = scraper(env)
    code = dot.run(site.base + "/refunds", out, s)
    assert code == 1
    files = json.loads((out / "manifest.json").read_text())["files"]
    bad = [e for e in files if e["via"] == "failed"]
    assert (
        len(bad) == 1 and bad[0]["requested_url"].endswith("/faq") and bad[0]["error"]
    )
    assert set(bad[0]) == {"requested_url", "via", "error"}
    with pytest.raises(Failed):
        scraper(env).fetch(site.base + "/faq")


def cdx_only(site, url_path, ts="20261115225156", empty=False):
    """The availability API knows nothing; the CDX index answers (or is empty)."""
    url = site.base + url_path
    q = urllib.parse.quote(url, safe="")
    site.routes["/wayback/available?url=" + q] = (
        200,
        b'{"archived_snapshots": {}}',
        {},
    )
    rows = (
        [["urlkey", "timestamp"]]
        if empty
        else [["urlkey", "timestamp"], ["k", "2020"], ["k", ts]]
    )
    body = b"[]" if empty else json.dumps(rows).encode()
    site.routes[f"/cdx?url={q}&output=json&limit=-1&filter=statuscode:200"] = (
        200,
        body,
        {},
    )


def test_cdx_fallback(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (403, b"", {})
    cdx_only(site, "/p")
    site.routes["/web/*"] = (200, b"VIA CDX", {})
    got = scraper(env).fetch(site.base + "/p")
    assert got.body == b"VIA CDX"
    assert got.record["via"] == "archive"
    assert got.record["archive_timestamp"] == "20261115225156"
    assert any(p.startswith("/web/20261115225156id_/") for p in site.paths())
    # both empty: failed
    cdx_only(site, "/q", empty=True)
    with pytest.raises(Failed):
        scraper(env).fetch(site.base + "/q")
    # CDX answers an error: no snapshot
    url = site.base + "/r"
    q = urllib.parse.quote(url, safe="")
    site.routes["/wayback/available?url=" + q] = (200, b"{}", {})
    site.routes[f"/cdx?url={q}&output=json&limit=-1&filter=statuscode:200"] = (
        200,
        b"not json",
        {},
    )
    with pytest.raises(Failed):
        scraper(env).fetch(url)


def test_archived_links(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (403, b"", {})
    cdx_only(site, "/refunds")
    cdx_only(site, "/faq", ts="20261101000000")
    site.routes["/web/*"] = (
        200,
        lambda path: b'<a href="/faq">FAQ</a>' if path.endswith("/refunds") else b"faq",
        {},
    )
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 0
    assert "/faq" not in site.paths() and "/refunds" not in site.paths()
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert len(files) == 2
    assert all(e["via"] == "archive" and e["archive_timestamp"] for e in files)
    assert files[1]["archive_timestamp"] == "20261101000000"


def test_summary(env, capsys):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(b'<a href="/faq">FAQ</a><a href="/guide">guide</a>')
    site.routes["/faq"] = (403, b"", {})
    cdx_only(site, "/faq", empty=True)
    site.routes["/guide"] = ok(b"g")
    out = tmp / "out"
    code = dot.run(site.base + "/refunds", out, scraper(env))
    assert code == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"source 200 {out.as_posix()}/refunds.html {site.base}/refunds"
    assert f"failed no archive snapshot - {site.base}/faq" in lines
    assert lines[-1] == "saved 2, failed 1"


def test_gzip_with_header_is_saved_decoded(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    html = b'<a href="/faq">FAQ</a>'
    site.routes["/refunds"] = (200, gzip.compress(html), {"Content-Encoding": "gzip"})
    site.routes["/faq"] = ok(b"faq")
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert files[0]["content_encoding"] == "gzip"
    assert files[1]["content_encoding"] == "identity"
    assert (out / files[0]["file"]).read_bytes() == html
    assert files[0]["sha256"] == hashlib.sha256(html).hexdigest()
    assert len(files) == 2  # the link inside the decoded page was followed


def test_gzip_by_magic_bytes_without_header(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/a"] = ok(gzip.compress(b"plain"))
    got = scraper(env).fetch(site.base + "/a")
    assert got.body == b"plain" and got.record["content_encoding"] == "gzip"
    assert got.record["sha256"] == hashlib.sha256(b"plain").hexdigest()


def test_gzip_archive_body_is_decoded(env):
    _clock, site, _ = env
    site.routes["/robots.txt"] = (403, b"", {})
    cdx_only(site, "/a")
    site.routes["/web/*"] = (200, gzip.compress(b"old"), {"Content-Encoding": "gzip"})
    got = scraper(env).fetch(site.base + "/a")
    assert got.body == b"old" and got.record["content_encoding"] == "gzip"


def test_gzip_corrupt_body_is_failed(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = (200, b"\x1f\x8bnot gzip", {"Content-Encoding": "gzip"})
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 1
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert files[0]["via"] == "failed" and files[0]["error"] == "cannot decode gzip"


def test_gzip_cached_entry_decoded_on_read(env):
    _clock, site, _ = env
    s = scraper(env)
    url = site.base + "/a"
    path = s._cache_path(url)
    path.parent.mkdir(parents=True)
    packed = gzip.compress(b"cached")
    path.write_bytes(packed)
    path.with_name(path.name + ".json").write_text(
        json.dumps({"requested_url": url, "sha256": hashlib.sha256(packed).hexdigest()})
    )
    got = s.fetch(url)
    assert got.body == b"cached" and site.log == []
    assert got.record["content_encoding"] == "gzip"
    assert got.record["sha256"] == hashlib.sha256(b"cached").hexdigest()
    assert path.read_bytes() == b"cached"  # rewritten, so not decoded twice


def test_link_rule(env):
    _clock, site, tmp = env
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/a/start"] = ok(
        b'<a href="/a/guidance-x">x</a><a href="/a/ticket-refunds">y</a>'
        b'<a href="#Refund-of-ticket">z</a><a href="/a/other">o</a>'
        b'<a href="/a/start">Refund guide</a>'
    )
    site.routes["/a/guidance-x"] = ok()
    site.routes["/a/ticket-refunds"] = ok()
    out = tmp / "out"
    assert dot.run(site.base + "/a/start", out, scraper(env)) == 0
    assert [p for p in site.paths() if p.startswith("/a/")] == [
        "/a/start",
        "/a/guidance-x",
        "/a/ticket-refunds",
    ]


PDF_BODY = b"%PDF-1.4\n% a tiny stand-in PDF\n%%EOF\n"


def test_extra_urls_first_outside_the_limit_with_summary(env, capsys, monkeypatch):
    # @criterion C6
    _clock, site, tmp = env
    monkeypatch.setattr(dot.shutil, "which", lambda name: None)
    site.routes["/robots.txt"] = (200, b"", {})
    links = [f'<a href="/page{i}">Compliance guide {i}</a>' for i in range(11)]
    # equal to an extra URL, inside the first 10 links: skipped, its slot freed
    links.insert(3, '<a href="/airconsumer/FAQ_x">FAQ again</a>')
    site.routes["/refunds"] = ok("".join(links).encode())
    for i in range(11):
        site.routes[f"/page{i}"] = ok(f"p{i}".encode())
    site.routes["/airconsumer/Guide_x"] = ok(b'<a href="/files/guide.pdf">PDF</a>')
    site.routes["/airconsumer/FAQ_x"] = ok(b"faq")
    site.routes["/airconsumer/gone"] = (404, b"", {})
    site.routes["/files/guide.pdf"] = ok(PDF_BODY)
    extras = [site.base + p for p in ("/airconsumer/Guide_x", "/airconsumer/FAQ_x")]
    extras.append(site.base + "/airconsumer/gone")
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env), extras) == 1
    files = json.loads((out / "manifest.json").read_text())["files"]
    urls = [e["requested_url"] for e in files]
    assert urls[1:4] == extras  # right after the start page
    assert len(files) == 1 + 3 + 10  # the crawl fills the limit, extras still fetched
    assert site.paths().count("/airconsumer/FAQ_x") == 1
    assert sorted(urls[4:]) == sorted(site.base + f"/page{i}" for i in range(10))
    assert "/files/guide.pdf" not in site.paths()  # over the shared limit
    lines = capsys.readouterr().out.splitlines()
    assert "extra: 2 fetched, 1 failed" in lines
    assert lines[-1] == "saved 13, failed 1"


def test_extra_urls_pdf_links_share_the_limit(env, monkeypatch):
    # @criterion C6
    _clock, site, tmp = env
    monkeypatch.setattr(dot.shutil, "which", lambda name: None)
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(b'<a href="/faq">FAQ</a>')
    site.routes["/faq"] = ok(b"faq")
    site.routes["/airconsumer/Guide_x"] = ok(
        b'<a href="/files/guide.pdf">PDF</a><a href="/files/guide.pdf#p2">again</a>'
    )
    site.routes["/files/guide.pdf"] = ok(PDF_BODY)
    out = tmp / "out"
    guide = site.base + "/airconsumer/Guide_x"
    assert dot.run(site.base + "/refunds", out, scraper(env), [guide]) == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert [e["file"] for e in files] == [
        "refunds.html",
        "airconsumer-Guide-x.html",
        "faq.html",
        "files-guide.pdf",
    ]
    assert files[3]["linked_from"] == guide and files[3]["text_file"] is None


def test_pdf_text_written_beside_the_pdf(env, monkeypatch):
    # @criterion C6
    _clock, site, tmp = env
    calls = []

    def fake_run(cmd, check, timeout):
        assert timeout == 60
        calls.append(cmd)
        Path(cmd[-1]).write_text("page one\n\fpage two\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dot.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(dot.subprocess, "run", fake_run)
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(PDF_BODY)  # PDF by magic bytes, whatever the URL
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert files[0]["file"] == "refunds.pdf" and files[0]["text_file"] == "refunds.txt"
    assert files[0]["linked_from"] is None
    assert (out / "refunds.txt").read_text().startswith("page one")
    assert calls[0][:2] == ["/usr/bin/pdftotext", "-layout"]


def test_pdf_text_null_when_pdftotext_missing(env, monkeypatch):
    # @criterion C6
    _clock, site, tmp = env
    monkeypatch.setattr(dot.shutil, "which", lambda name: None)
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(PDF_BODY)
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert files[0]["text_file"] is None
    assert not (out / "refunds.txt").exists()


def test_pdf_text_null_on_pdftotext_timeout(env, monkeypatch):
    # @criterion C6
    _clock, site, tmp = env

    def slow(cmd, check, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(dot.shutil, "which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(dot.subprocess, "run", slow)
    site.routes["/robots.txt"] = (200, b"", {})
    site.routes["/refunds"] = ok(PDF_BODY)
    out = tmp / "out"
    assert dot.run(site.base + "/refunds", out, scraper(env)) == 0
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert files[0]["text_file"] is None
