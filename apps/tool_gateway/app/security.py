from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    pass


def _validate_ip(value: str) -> None:
    ip = ipaddress.ip_address(value)
    if not ip.is_global:
        raise UnsafeUrlError(f"destination address is not public: {ip}")


def validate_url_syntax(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL hostname is required")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise UnsafeUrlError("only standard HTTP ports are allowed")
    return parsed.hostname


def resolve_public_addresses(hostname: str) -> set[str]:
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"hostname cannot be resolved: {hostname}") from exc
    addresses = {record[4][0] for record in records}
    if not addresses:
        raise UnsafeUrlError(f"hostname has no addresses: {hostname}")
    for address in addresses:
        _validate_ip(address)
    return addresses


async def validate_external_url(url: str) -> None:
    hostname = validate_url_syntax(url)
    try:
        _validate_ip(hostname)
    except ValueError:
        await asyncio.to_thread(resolve_public_addresses, hostname)
