"""Collector contract. Every collector: health_check(), collect(config), parse(payload), normalize(event).
Built-in: SSRF-safe fetching (scheme/host/IP/redirect validation), timeouts, retries with backoff, robots.txt,
per-host politeness delay, structured metrics, shared JSON-LD / iCal / RSS extraction helpers."""
from __future__ import annotations

import json
import re
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings, load_config
from app.core.logging import get_logger, log_event
from app.core.netsafe import UnsafeURL, validate_url
from app.schemas.normalized import NormalizedEvent

MAX_BODY_BYTES = 6_000_000
MAX_REDIRECTS = 5
POLITE_DELAY_S = 0.6
_last_hit: dict[str, float] = {}


class CollectorDisabled(Exception):
    """Raised when a collector cannot run (e.g. missing API key). Reported as DISABLED, not FAILED."""


@dataclass
class HealthResult:
    status: str  # HEALTHY / DEGRADED / FAILED / DISABLED
    message: str = ""
    response_ms: int | None = None


@dataclass
class CollectResult:
    source_key: str
    events: list[NormalizedEvent] = field(default_factory=list)
    raw_payloads: list[dict[str, Any]] = field(default_factory=list)
    status: str = "HEALTHY"
    error: str | None = None
    response_ms: int | None = None
    warnings: list[str] = field(default_factory=list)
    endpoints_attempted: int = 0
    endpoints_ok: int = 0
    blocked: list[str] = field(default_factory=list)  # 401/403/robots — never aggressively retried


def allowed_domains() -> tuple[str, ...] | None:
    cfg = load_config("sources.yaml")
    doms = cfg.get("allowed_domains")
    return tuple(d.lower() for d in doms) if doms else None


class Collector:
    name: str = "base"
    requires_key: str | None = None
    max_retries: int = 3
    source_confidence: str = "TRUSTED"  # OFFICIAL / TRUSTED / SECONDARY / UNVERIFIED — override per collector

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.settings = get_settings()
        self.log = get_logger(f"collector.{self.name}")
        self.filters: dict[str, Any] = {}  # city / category filters injected by CLI

    # ---- HTTP -------------------------------------------------------------------------------------------
    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.http_timeout_seconds, follow_redirects=False,
                            headers={"User-Agent": self.settings.http_user_agent,
                                     "Accept": "application/json, application/ld+json, text/calendar, application/rss+xml, text/html;q=0.9, */*;q=0.8"})

    def _polite(self, url: str) -> None:
        host = urlparse(url).netloc
        delay = max(POLITE_DELAY_S, crawl_delay(url, self.settings.http_user_agent))
        wait = _last_hit.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()

    def fetch(self, url: str, params: dict | None = None, check_robots: bool = False) -> httpx.Response:
        """SSRF-safe GET with manual redirect following (each hop validated), retries and robots.txt."""
        validate_url(url, allowed_domains())
        if check_robots and not robots_allowed(url, self.settings.http_user_agent):
            raise PermissionError(f"robots.txt disallows {url}")
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with self._client() as client:
                    cur, hops = url, 0
                    while True:
                        self._polite(cur)
                        resp = client.get(cur, params=params if cur == url else None)
                        if resp.is_redirect and hops < MAX_REDIRECTS:
                            nxt = str(resp.next_request.url) if resp.next_request else resp.headers.get("location", "")
                            validate_url(nxt, allowed_domains())
                            cur, hops = nxt, hops + 1
                            continue
                        break
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                resp.raise_for_status()
                if len(resp.content) > MAX_BODY_BYTES:
                    raise RuntimeError(f"response too large ({len(resp.content)} bytes)")
                return resp
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last = exc
                self.log.warning("attempt %s/%s failed for %s: %s", attempt, self.max_retries, url, exc)
                time.sleep(min(2 ** attempt, 8))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403, 404, 406, 410):
                    raise  # blocked / gone: do not retry
                last = exc
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"fetch failed after {self.max_retries} attempts: {last}")

    def safe_fetch(self, url: str, result: CollectResult, label: str | None = None, check_robots: bool = True) -> httpx.Response | None:
        """fetch() that records outcomes on the CollectResult instead of raising. Returns None on failure."""
        result.endpoints_attempted += 1
        label = label or url
        try:
            r = self.fetch(url, check_robots=check_robots)
            result.endpoints_ok += 1
            return r
        except PermissionError as exc:
            result.blocked.append(label); result.warnings.append(f"{label}: {exc}")
        except UnsafeURL as exc:
            result.warnings.append(f"{label}: unsafe URL ({exc})")
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            (result.blocked if code in (401, 403, 406) else result.warnings).append(label)
            result.warnings.append(f"{label}: HTTP {code}")
        except Exception as exc:
            result.warnings.append(f"{label}: {type(exc).__name__}: {str(exc)[:120]}")
        return None

    # ---- Shared extractors ----------------------------------------------------------------------------------
    _LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
    EVENT_TYPES = ("Event", "MusicEvent", "SportsEvent", "Festival", "TheaterEvent", "EducationEvent", "BusinessEvent", "ComedyEvent",
                   "ExhibitionEvent", "DanceEvent", "ScreeningEvent", "SocialEvent", "ChildrensEvent", "LiteraryEvent", "FoodEvent", "VisualArtsEvent")

    @classmethod
    def extract_jsonld_events(cls, html: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for block in cls._LD_RE.findall(html):
            try:
                data = json.loads(block.strip(), strict=False)
            except json.JSONDecodeError:
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                it = stack.pop()
                if isinstance(it, dict):
                    t = it.get("@type", "")
                    types = t if isinstance(t, list) else [t]
                    if any(str(x).split("/")[-1] in cls.EVENT_TYPES or str(x).endswith("Event") for x in types):
                        out.append(it)
                    for k in ("@graph", "subEvent", "itemListElement", "mainEntity"):
                        v = it.get(k)
                        if isinstance(v, list):
                            stack.extend(x.get("item", x) if isinstance(x, dict) else x for x in v)
                        elif isinstance(v, dict):
                            stack.append(v.get("item", v))
                elif isinstance(it, list):
                    stack.extend(it)
        return out

    @staticmethod
    def detail_links(html: str, base_url: str, pattern: str) -> list[str]:
        p = urlparse(base_url)
        root = f"{p.scheme}://{p.netloc}"
        links = set()
        for href in re.findall(r'href=["\']([^"\'#?]+)', html):
            if re.search(pattern, href):
                links.add(href if href.startswith("http") else root + (href if href.startswith("/") else "/" + href))
        return sorted(l for l in links if urlparse(l).netloc == p.netloc)

    # ---- Contract --------------------------------------------------------------------------------------------
    def api_key(self) -> str | None:
        if not self.requires_key:
            return None
        return getattr(self.settings, self.requires_key.lower(), "") or None

    def health_check(self) -> HealthResult:
        if self.requires_key and not self.api_key():
            return HealthResult("DISABLED", f"{self.requires_key} not configured")
        return HealthResult("HEALTHY", "ready")

    def collect(self, config: dict[str, Any] | None = None) -> CollectResult:  # pragma: no cover
        raise NotImplementedError

    def parse(self, payload: Any) -> Iterable[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def normalize(self, event: dict[str, Any]) -> NormalizedEvent | None:  # pragma: no cover
        raise NotImplementedError

    def run(self, run_id: int | None = None) -> CollectResult:
        started = time.perf_counter()
        if self.requires_key and not self.api_key():
            return CollectResult(self.name, status="DISABLED", error=f"{self.requires_key} not configured")
        try:
            result = self.collect(self.config)
        except CollectorDisabled as exc:
            return CollectResult(self.name, status="DISABLED", error=str(exc))
        except Exception as exc:
            self.log.exception("collector %s failed", self.name)
            return CollectResult(self.name, status="FAILED", error=f"{type(exc).__name__}: {exc}"[:500])
        result.response_ms = int((time.perf_counter() - started) * 1000)
        for ev in result.events:
            ev.source_confidence = ev.source_confidence or self.source_confidence
        if result.status == "HEALTHY":
            if result.endpoints_attempted == 0 and not result.events:
                result.status = "EMPTY"  # nothing configured/enabled for this source (registry has no active targets)
            elif result.endpoints_attempted and result.endpoints_ok == 0:
                # every endpoint blocked (401/403/406/robots) → BLOCKED: never retried aggressively; anything else → FAILED
                result.status = "BLOCKED" if result.blocked and len(result.blocked) >= result.endpoints_attempted else "FAILED"
                result.error = "; ".join(result.warnings)[:500] or "all endpoints failed"
            elif result.warnings:
                result.status = "DEGRADED"
        log_event(self.log, run_id=run_id, source=self.name, stage="collect", status=result.status, duration_ms=result.response_ms,
                  events=len(result.events), endpoints=f"{result.endpoints_ok}/{result.endpoints_attempted}", blocked=len(result.blocked))
        return result


@lru_cache(maxsize=256)
def _robots(base: str) -> robotparser.RobotFileParser | None:
    rp = robotparser.RobotFileParser()
    try:
        validate_url(f"{base}/robots.txt", allowed_domains())
        resp = httpx.get(f"{base}/robots.txt", timeout=10, follow_redirects=True, headers={"User-Agent": get_settings().http_user_agent})
        if resp.status_code >= 400:
            return None
        rp.parse(resp.text.splitlines())
        return rp
    except Exception:
        return None


def crawl_delay(url: str, user_agent: str) -> float:
    """robots.txt Crawl-delay for this host (seconds, capped at 10); 0 when unspecified."""
    p = urlparse(url)
    rp = _robots(f"{p.scheme}://{p.netloc}")
    if rp is None:
        return 0.0
    try:
        d = rp.crawl_delay(user_agent.split("/")[0]) or rp.crawl_delay("*")
    except Exception:
        d = None
    return min(float(d or 0), 10.0)


def robots_allowed(url: str, user_agent: str) -> bool:
    p = urlparse(url)
    rp = _robots(f"{p.scheme}://{p.netloc}")
    if rp is None:
        return True
    ua = user_agent.split("/")[0]
    return rp.can_fetch(ua, url) and rp.can_fetch("*", url)
