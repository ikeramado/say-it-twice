"""A polite fetcher: honest User-Agent, robots.txt, per-host spacing, retries, cache, provenance.

Standard library only. The clock and the sleep function are injected so tests never sleep.
It never disguises itself: on 403, 451, a robots.txt disallow or exhausted retries it falls
back to the Internet Archive's latest snapshot and records `via: archive`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = (
    "say-it-twice-research-bot/1.0 (+https://github.com/say-it-twice; "
    "reads public US DOT consumer guidance pages for an airline-refund study)"
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REFUSED_STATUSES = frozenset({403, 451})
ARCHIVE_API = "https://archive.org/wayback/available"
ARCHIVE_WEB = "https://web.archive.org"
ARCHIVE_CDX = "https://web.archive.org/cdx/search/cdx"
CACHE_ROOT = Path("data/raw/scrape")


class Failed(Exception):
    """The URL could not be had from the source nor from the archive."""


@dataclass
class Fetched:
    body: bytes
    record: dict  # requested_url, final_url, fetched_at, status, sha256, via[, archive_timestamp]


GZIP_MAGIC = b"\x1f\x8b"


def _decode(body: bytes, headers: dict) -> tuple[bytes, str]:
    """Gunzip a body sent with Content-Encoding: gzip or starting with the gzip magic bytes.

    Returns (body, "gzip" | "identity"); raises Failed when it cannot be gunzipped."""
    declared = any(
        k.lower() == "content-encoding" and v.strip().lower() in ("gzip", "x-gzip")
        for k, v in headers.items()
    )
    if not declared and not body.startswith(GZIP_MAGIC):
        return body, "identity"
    try:
        return gzip.decompress(body), "gzip"
    except (OSError, EOFError, ValueError) as e:
        raise Failed("cannot decode gzip") from e


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PoliteScraper:
    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        interval: float = 3.0,
        clock=time.monotonic,
        sleep=time.sleep,
        wall=_now_utc,
        cache_root: Path = CACHE_ROOT,
        archive_api: str = ARCHIVE_API,
        archive_web: str = ARCHIVE_WEB,
        archive_cdx: str = ARCHIVE_CDX,
        retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 30.0,
    ):
        self.user_agent = user_agent
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.wall = wall
        self.cache_root = Path(cache_root)
        self.archive_api = archive_api
        self.archive_web = archive_web.rstrip("/")
        self.archive_cdx = archive_cdx
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # -- low level -------------------------------------------------------------------
    def _throttle(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = last + self.interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def _request(self, url: str) -> tuple[int, bytes, str, dict]:
        """One request, spaced per host. Returns (status, body, final_url, headers).

        HTTP error statuses are returned, not raised; a network error raises URLError."""
        self._throttle(urllib.parse.urlsplit(url).netloc)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read(), resp.geturl(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), url, dict(e.headers or {})

    def _request_retrying(self, url: str) -> tuple[int, bytes, str, dict]:
        attempt = 0
        while True:
            try:
                result = self._request(url)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                result = (0, str(e).encode(), url, {})
            if result[0] not in RETRY_STATUSES and result[0] != 0:
                return result
            if attempt >= self.retries:
                return result
            wait = self.backoff * (2**attempt)
            try:
                wait = max(wait, float(result[3].get("Retry-After", 0)))
            except ValueError:
                pass
            self.sleep(wait)
            attempt += 1

    # -- robots ----------------------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._read_robots(origin)
        rp = self._robots[origin]
        return rp is not None and rp.can_fetch(self.user_agent, url)

    def _read_robots(self, origin: str):
        try:
            status, body, _, _ = self._request_retrying(origin + "/robots.txt")
        except OSError:
            return None
        rp = urllib.robotparser.RobotFileParser()
        if status == 404:  # no robots.txt: nothing is disallowed
            rp.parse([])
            return rp
        if status != 200:  # cannot be read: counts as a disallow
            return None
        rp.parse(body.decode("utf-8", "replace").splitlines())
        return rp

    # -- cache -----------------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        host = urllib.parse.urlsplit(url).netloc.replace(":", "_")
        return self.cache_root / host / hashlib.sha256(url.encode()).hexdigest()

    def _cache_get(self, url: str) -> Fetched | None:
        path = self._cache_path(url)
        meta = path.with_name(path.name + ".json")
        if path.is_file() and meta.is_file():
            body, record = path.read_bytes(), json.loads(meta.read_text())
            if body.startswith(GZIP_MAGIC):  # an entry saved compressed by an older run
                body, record["content_encoding"] = _decode(body, {})
                record["sha256"] = hashlib.sha256(body).hexdigest()
                self._cache_put(url, Fetched(body, record))
            else:
                record.setdefault("content_encoding", "identity")
            return Fetched(body, record)
        return None

    def _cache_put(self, url: str, fetched: Fetched) -> None:
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetched.body)
        path.with_name(path.name + ".json").write_text(
            json.dumps(fetched.record, indent=2)
        )

    # -- archive ---------------------------------------------------------------------
    def _timestamp_api(self, url: str) -> str | None:
        api = f"{self.archive_api}?url={urllib.parse.quote(url, safe='')}"
        status, body, _, _ = self._request_retrying(api)
        if status != 200:
            return None
        try:
            closest = json.loads(body)["archived_snapshots"]["closest"]
            if not closest.get("available", True):
                return None
            return str(closest["timestamp"])
        except (KeyError, ValueError, TypeError, AttributeError):
            return None

    def _timestamp_cdx(self, url: str) -> str | None:
        cdx = (
            f"{self.archive_cdx}?url={urllib.parse.quote(url, safe='')}"
            "&output=json&limit=-1&filter=statuscode:200"
        )
        status, body, _, _ = self._request_retrying(cdx)
        if status != 200:
            return None
        try:
            rows = json.loads(body)
            return str(rows[-1][1]) if len(rows) > 1 else None  # row 0 is the header
        except (ValueError, TypeError, IndexError, KeyError):
            return None

    def _from_archive(self, url: str) -> Fetched:
        timestamp = self._timestamp_api(url) or self._timestamp_cdx(url)
        if timestamp is None:
            raise Failed("no archive snapshot")
        snap = f"{self.archive_web}/web/{timestamp}id_/{url}"
        status, page, final, headers = self._request_retrying(snap)
        if status != 200:
            raise Failed(f"archive snapshot answered {status}")
        page, encoding = _decode(page, headers)
        return Fetched(
            page,
            {
                "requested_url": url,
                "final_url": final,
                "fetched_at": self.wall(),
                "status": status,
                "sha256": hashlib.sha256(page).hexdigest(),
                "content_encoding": encoding,
                "via": "archive",
                "archive_timestamp": timestamp,
            },
        )

    # -- public ----------------------------------------------------------------------
    def fetch(self, url: str, archive_only: bool = False) -> Fetched:
        """The page from the cache, the source or the archive; raises Failed.

        archive_only: make no request to the source (it already refused)."""
        cached = self._cache_get(url)
        if cached is not None:
            return cached
        fetched = None
        if not archive_only and self._allowed(url):
            try:
                status, body, final, headers = self._request_retrying(url)
            except (
                Exception
            ) as e:  # pragma: no cover - _request_retrying catches network errors
                raise Failed(str(e)) from e
            if status == 200:
                body, encoding = _decode(body, headers)
                fetched = Fetched(
                    body,
                    {
                        "requested_url": url,
                        "final_url": final,
                        "fetched_at": self.wall(),
                        "status": status,
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "content_encoding": encoding,
                        "via": "source",
                    },
                )
            elif status in REFUSED_STATUSES or status in RETRY_STATUSES or status == 0:
                pass  # fall back to the archive
            else:
                raise Failed(f"source answered {status}")
        if fetched is None:
            fetched = self._from_archive(url)
        self._cache_put(url, fetched)
        return fetched
