"""SSRF-safe outbound URL policy.

All collectors fetch through `validate_url()` before any request and after every redirect hop:
  * scheme must be http/https
  * hostname must not be an IP literal in private / loopback / link-local / multicast / reserved ranges
  * hostname must resolve (A/AAAA) only to public addresses
  * optional domain allowlist (config/sources.yaml -> allowed_domains) enforced when `enforce_allowlist` is on
"""
from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal", "instance-data"}


class UnsafeURL(Exception):
    pass


def _is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified
                or (a.version == 6 and a.ipv4_mapped is not None and not _is_public_ip(str(a.ipv4_mapped))))


@lru_cache(maxsize=2048)
def _resolve(host: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"DNS resolution failed for {host}: {exc}") from exc
    return tuple(sorted({i[4][0] for i in infos}))


def host_allowed(host: str, allowed_domains: tuple[str, ...] | None) -> bool:
    if not allowed_domains:
        return True
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def validate_url(url: str, allowed_domains: tuple[str, ...] | None = None, resolve: bool = True) -> str:
    """Returns the URL if safe, raises UnsafeURL otherwise."""
    p = urlparse(url)
    if p.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURL(f"scheme not allowed: {p.scheme!r}")
    host = (p.hostname or "").lower().rstrip(".")
    if not host or host in BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal") or host.endswith(".local"):
        raise UnsafeURL(f"host not allowed: {host!r}")
    if p.username or p.password:
        raise UnsafeURL("credentials in URL not allowed")
    try:
        ipaddress.ip_address(host)
        if not _is_public_ip(host):
            raise UnsafeURL(f"private/loopback IP literal: {host}")
        is_ip = True
    except ValueError:
        is_ip = False
    if not host_allowed(host, allowed_domains):
        raise UnsafeURL(f"host {host} not in allowlist")
    if resolve and not is_ip:
        for ip in _resolve(host):
            if not _is_public_ip(ip):
                raise UnsafeURL(f"{host} resolves to non-public address {ip}")
    return url
