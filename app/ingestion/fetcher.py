"""Allow-listed HTTP client for the ingestion service. It is the only
component permitted to reach the OCBC website.

* every URL (including each redirect hop) must be https on an allow-listed
  host and under an allow-listed research path prefix;
* robots.txt is honoured;
* requests are rate limited and retries are bounded.
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass

import httpx

from app.common import config

USER_AGENT = "OCBC-Research-Assistant-Ingestion/1.0 (+internal research consolidation; contact: admin)"


class SourceBoundaryError(Exception):
    pass


@dataclass
class FetchResult:
    url: str              # final URL after verified redirects
    status: int
    content: bytes
    content_type: str
    last_modified: str | None   # recorded for reference only, never used as a publication date
    redirects: list[str]


def check_allowed(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https":
        raise SourceBoundaryError(f"non-https URL refused: {url}")
    if (p.hostname or "").lower() not in config.OCBC_ALLOWED_HOSTS:
        raise SourceBoundaryError(f"host outside OCBC research boundary: {p.hostname}")
    path = urllib.parse.unquote(p.path)
    if not any(path.startswith(pre) for pre in config.OCBC_ALLOWED_PATH_PREFIXES):
        raise SourceBoundaryError(f"path outside OCBC research boundary: {path}")
    return url


def absolutise(href: str, base: str = "https://www.ocbc.com/") -> str:
    url = urllib.parse.urljoin(base, href.strip())
    p = urllib.parse.urlsplit(url)
    # Percent-encode spaces etc. in the path while leaving existing escapes intact.
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, p.query, ""))


class Fetcher:
    def __init__(self, min_interval: float | None = None, max_retries: int | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.min_interval = config.INGEST_MIN_INTERVAL_S if min_interval is None else min_interval
        self.max_retries = config.INGEST_MAX_RETRIES if max_retries is None else max_retries
        self._last = 0.0
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=False,
                                   timeout=httpx.Timeout(45.0, connect=15.0), transport=transport)
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self.requests_made = 0

    def close(self):
        self.client.close()

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def robots_allowed(self, url: str) -> bool:
        if self._robots is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self._request("GET", "https://www.ocbc.com/robots.txt", check_robots=False)
                rp.parse(r.content.decode("utf-8", "replace").splitlines())
            except Exception:
                rp.parse([])  # unreachable robots.txt: proceed with no extra restrictions
            self._robots = rp
        return self._robots.can_fetch("*", url)

    def _request(self, method: str, url: str, data: dict | None = None, headers: dict | None = None,
                 check_robots: bool = True, max_bytes: int = 60_000_000) -> FetchResult:
        check_allowed(url)
        if check_robots and not self.robots_allowed(url):
            raise SourceBoundaryError(f"disallowed by robots.txt: {url}")
        redirects: list[str] = []
        attempt = 0
        current = url
        while True:
            self._throttle()
            self.requests_made += 1
            try:
                resp = self.client.request(method, current, data=data, headers=headers)
            except httpx.HTTPError as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 20))
                continue
            if resp.status_code in (301, 302, 303, 307, 308):
                target = absolutise(resp.headers.get("location", ""), current)
                check_allowed(target)  # verify every redirect destination before following
                redirects.append(target)
                if len(redirects) > 5:
                    raise SourceBoundaryError(f"too many redirects from {url}")
                current = target
                if resp.status_code == 303:
                    method, data = "GET", None
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                attempt += 1
                if attempt > self.max_retries:
                    return self._result(current, resp, redirects)
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                time.sleep(min(delay, 30))
                continue
            if len(resp.content) > max_bytes:
                raise SourceBoundaryError(f"response too large from {current}")
            return self._result(current, resp, redirects)

    @staticmethod
    def _result(url, resp, redirects) -> FetchResult:
        return FetchResult(url=url, status=resp.status_code, content=resp.content,
                           content_type=resp.headers.get("content-type", ""),
                           last_modified=resp.headers.get("last-modified"), redirects=redirects)

    def get(self, url: str, **kw) -> FetchResult:
        return self._request("GET", url, **kw)

    def post(self, url: str, data: dict, headers: dict | None = None) -> FetchResult:
        return self._request("POST", url, data=data, headers=headers)
