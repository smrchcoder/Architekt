from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.errors import PublicFacingError


class UnsafeSourceUrlError(PublicFacingError):
    pass


def validate_public_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeSourceUrlError("Only http and https source URLs are allowed")

    if parsed.username or parsed.password:
        raise UnsafeSourceUrlError(
            "Source URLs with embedded credentials are not allowed"
        )

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeSourceUrlError("Source URL must include a hostname")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeSourceUrlError("Local or private source URLs are not allowed")

    direct_ip = _parse_ip(hostname)
    if direct_ip is not None:
        _ensure_public_ip(direct_ip)
        return

    for resolved_ip in _resolve_host_ips(hostname):
        _ensure_public_ip(resolved_ip)


def _parse_ip(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def _resolve_host_ips(hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        addr_info = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return set()

    resolved_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for _, _, _, _, sockaddr in addr_info:
        resolved_ips.add(ipaddress.ip_address(sockaddr[0]))
    return resolved_ips


def _ensure_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if ip.is_global:
        return
    raise UnsafeSourceUrlError("Local or private source URLs are not allowed")
