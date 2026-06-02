"""URL scheme validation and SSRF IP range checks."""

import ipaddress
import socket
import sys
from urllib.parse import urlparse


class ValidationError(Exception):
    """Raised when a URL fails validation checks."""

    def __init__(self, error_code: str, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


# All networks blocked to prevent SSRF — validated per-hop in the fetch engine too.
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback (IPv4)
    ipaddress.ip_network("::1/128"),         # Loopback (IPv6)
    ipaddress.ip_network("10.0.0.0/8"),      # RFC 1918 private
    ipaddress.ip_network("172.16.0.0/12"),   # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918 private
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / AWS EC2 metadata endpoint
    ipaddress.ip_network("fe80::/10"),       # Link-local (IPv6)
    ipaddress.ip_network("fc00::/7"),        # Unique local (IPv6)
    ipaddress.ip_network("0.0.0.0/8"),       # Unspecified
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT shared address space
]


def validate_url(url: str) -> None:
    """Validate a URL for correct scheme and SSRF-safe destination.

    Raises ValidationError if the URL is invalid or resolves to a forbidden target.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            error_code="Invalid URL",
            detail=f"URL scheme must be http or https, got: {parsed.scheme!r}",
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError(
            error_code="Invalid URL",
            detail="URL must include a valid hostname.",
        )

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValidationError(
            error_code="DNS Failure",
            detail=f"DNS resolution failed for {hostname!r}: {exc}",
        ) from exc

    for _family, _socktype, _proto, _canonname, sockaddr in resolved:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValidationError(
                    error_code="Forbidden Target",
                    detail=f"The URL resolves to a private or reserved IP address ({ip_str}).",
                )
