"""Tests for app.validator."""

import socket
from unittest.mock import patch

import pytest

from app.validator import ValidationError, validate_url


class TestValidUrlsAccepted:
    """Valid URLs pass through without raising."""

    def test_https_public_domain(self) -> None:
        validate_url("https://google.com")

    def test_http_public_domain(self) -> None:
        validate_url("http://example.com")


class TestInvalidScheme:
    """Non-HTTP/HTTPS and malformed URLs are rejected with error_code='Invalid URL'."""

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ftp://example.com",
            "not-a-url",
            "",
        ],
    )
    def test_rejects_invalid_url(self, url: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_url(url)
        assert exc_info.value.error_code == "Invalid URL"


class TestSsrfBlocked:
    """Private and reserved IP ranges are blocked with error_code='Forbidden Target'."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1",
            "http://localhost",
            "http://[::1]",
            "http://192.168.1.1",
            "http://10.0.0.1",
            "http://172.16.0.1",
            "http://169.254.169.254",
            "http://0.0.0.0",
        ],
    )
    def test_blocks_private_and_reserved_ips(self, url: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_url(url)
        assert exc_info.value.error_code == "Forbidden Target"


class TestDnsFailure:
    """DNS resolution failure produces error_code='DNS Failure'."""

    def test_dns_failure_raises(self) -> None:
        with patch(
            "app.validator.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            with pytest.raises(ValidationError) as exc_info:
                validate_url("http://this-host-does-not-exist.invalid")
        assert exc_info.value.error_code == "DNS Failure"


def test_deliberate_failure_for_ci_test():
    """Deliberate failing test to verify CI catches test failures. Reverted after verification."""
    assert 1 == 2, "deliberate failure"
