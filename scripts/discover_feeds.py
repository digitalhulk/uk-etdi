"""Probe candidate official sites for structured event data (JSON-LD Event, RSS/Atom, ICS). Polite: robots checked, 1 req/site."""
import sys, json, re, concurrent.futures as cf
import httpx
from urllib import robotparser
from urllib.parse import urlparse, urljoin
UA = "UK-ETDI/1.0 (+event coverage research; polite)"
def robots_ok(url):
    p = urlparse(url); rp = robotparser.RobotFileParser()
    try:
        r = httpx.get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=10, follow_redirects=True, headers={"User-Agent": UA})
        if r.status_code >= 400: return True
        rp.parse(r.text.splitlines()); return rp.can_fetch(UA, url)
    except Exception: return True
def probe(url):
    out = {"url": url}
    try:
        if not robots_ok(url): out["status"] = "ROBOTS_DISALLOW"; return out
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": UA, "Accept": "text/html,application/xml,text/calendar,*/*"})
        out["code"] = r.status_code; out["final"] = str(r.url)
        if r.status_code != 200: out["status"] = f"HTTP{r.status_code}"; return out
        t = r.text; ct = r.headers.get("content-type", "")
        if "calendar" in ct or t.startswith("BEGIN:VCALENDAR"):
            out["status"] = "ICS"; out["n"] = t.count("BEGIN:VEVENT"); return out
        if "xml" in ct or t.lstrip().startswith("<?xml") or "<rss" in t[:500]:
            out["status"] = "RSS"; out["n"] = t.count("<item") + t.count("<entry"); return out
        n = 0
        for m in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', t, re.S | re.I):
            try:
                d = json.loads(m, strict=False)
            except Exception: continue
            stack = d if isinstance(d, list) else [d]
            while stack:
                x = stack.pop()
                if isinstance(x, dict):
                    ty = x.get("@type"); ty = " ".join(ty) if isinstance(ty, list) else str(ty or "")
                    if "Event" in ty and x.get("startDate"): n += 1
                    stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
                elif isinstance(x, list): stack.extend(x)
        feeds = re.findall(r'<link[^>]+type=["\'](application/(?:rss|atom)\+xml|text/calendar)["\'][^>]+href=["\']([^"\']+)', t, re.I)
        ics = re.findall(r'href=["\']([^"\']+\.ics[^"\']*)', t, re.I)[:3]
        out["jsonld_events"] = n; out["feeds"] = [urljoin(str(r.url), h) for _, h in feeds][:3]; out["ics_links"] = [urljoin(str(r.url), h) for h in ics]
        out["status"] = "JSONLD" if n else ("HAS_FEED_LINK" if feeds or ics else "HTML_ONLY")
    except Exception as e:
        out["status"] = "ERR " + type(e).__name__
    return out
if __name__ == "__main__":
    urls = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
    with cf.ThreadPoolExecutor(8) as ex:
        for o in ex.map(probe, urls):
            print(json.dumps(o))
