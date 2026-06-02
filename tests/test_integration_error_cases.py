"""Dedicated integration tests for all FR-04 error cases, non-UTF-8 HTML, and 5MB boundary."""

from unittest.mock import patch

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from app.extractor import extract_metadata
from app.main import app
from app.validator import ValidationError

_5MB = 5 * 1024 * 1024  # 5,242,880 bytes — the hard body-size limit


def _pass(*_a: object, **_k: object) -> None:
    """Bypass real DNS/IP validation in tests that mock httpx."""


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── FR-04: Invalid URL → 422 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",           # no scheme
        "http://",             # scheme present but no hostname
        "ftp://example.com",   # wrong scheme
        "javascript:alert(1)", # code injection scheme
        "file:///etc/passwd",  # filesystem scheme
    ],
)
def test_invalid_url_returns_422_with_error_detail(
    client: TestClient, url: str
) -> None:
    r = client.post("/api/inspect", json={"url": url})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Invalid URL"
    assert body["error_detail"], "error_detail must be non-empty"


# ── FR-04: Forbidden Target → 422 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",         # IPv4 loopback
        "http://192.168.1.100",     # RFC 1918 class C
        "http://10.10.10.10",       # RFC 1918 class A
        "http://169.254.169.254",   # link-local / AWS metadata endpoint
    ],
)
def test_forbidden_target_returns_422_with_detail(
    client: TestClient, url: str
) -> None:
    r = client.post("/api/inspect", json={"url": url})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Forbidden Target"
    detail = body["error_detail"].lower()
    assert "private" in detail or "reserved" in detail


def test_ssrf_via_redirect_hop_returns_422(client: TestClient) -> None:
    """Initial URL passes validation; redirect destination is a private IP → 422."""
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                301, headers={"location": "http://192.168.0.1"}
            )
        )

        def _selective(url: str) -> None:
            if "192.168" in url:
                raise ValidationError(
                    "Forbidden Target", "Resolves to a private IP address."
                )

        with patch("app.fetcher.validate_url", side_effect=_selective):
            r = client.post("/api/inspect", json={"url": "https://example.com"})

    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Forbidden Target"
    assert body["error_detail"]


# ── FR-04: DNS Failure → 502 ──────────────────────────────────────────────────


def test_dns_failure_returns_502_with_error_detail(client: TestClient) -> None:
    with respx.mock:
        respx.get("https://nxdomain.invalid/").mock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://nxdomain.invalid"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "DNS Failure"
    assert body["error_detail"]


# ── FR-04: Connection Timeout → 504 ──────────────────────────────────────────


def test_connection_timeout_returns_504_with_seconds_in_detail(
    client: TestClient,
) -> None:
    with respx.mock:
        respx.get("https://slow.example.com/").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://slow.example.com"})

    assert r.status_code == 504
    body = r.json()
    assert body["error"] == "Connection Timeout"
    assert "10" in body["error_detail"]  # references the 10-second timeout ceiling


# ── FR-04: Non-HTML Response → 502 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "content_type",
    [
        "application/pdf",
        "image/jpeg",
        "application/json",
        "application/octet-stream",
    ],
)
def test_non_html_content_type_returns_502_with_type_in_detail(
    client: TestClient, content_type: str
) -> None:
    with respx.mock:
        respx.get("https://example.com/file").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": content_type},
                content=b"\x00\x01\x02",
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/file"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "Non-HTML Response"
    assert content_type in body["error_detail"]  # actual MIME type must appear in message
    assert body["upstream_status_code"] == 200
    assert body["upstream_content_type"] == content_type


# ── FR-04: Excessive Redirects → 502 ─────────────────────────────────────────


def test_excessive_redirects_returns_502_with_chain_and_hop_limit_in_detail(
    client: TestClient,
) -> None:
    """11-hop redirect chain: correct error, chain length, and meaningful detail."""
    with respx.mock:
        for i in range(11):
            respx.get(f"https://example.com/r/{i}").mock(
                return_value=httpx.Response(
                    301,
                    headers={"location": f"https://example.com/r/{i + 1}"},
                )
            )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/r/0"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "Excessive Redirects"
    assert len(body["redirect_chain"]) == 11
    assert "10" in body["error_detail"]  # references the 10-hop ceiling


# ── FR-04: Response Too Large → 502 ──────────────────────────────────────────


def test_content_length_over_5mb_returns_502_with_size_in_detail(
    client: TestClient,
) -> None:
    """Content-Length header > 5MB triggers immediate 502 before reading body."""
    with respx.mock:
        respx.get("https://example.com/huge").mock(
            return_value=httpx.Response(
                200,
                headers={
                    "content-type": "text/html",
                    "content-length": str(_5MB + 1),
                },
                content=b"<html></html>",  # actual body is irrelevant; header is checked first
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/huge"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "Response Too Large"
    assert "5MB" in body["error_detail"]


def test_streamed_body_over_5mb_returns_502_with_size_in_detail(
    client: TestClient,
) -> None:
    """Streamed body exceeding 5MB (no Content-Length header) returns 502."""
    with respx.mock:
        respx.get("https://example.com/big").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"x" * (_5MB + 1),
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/big"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "Response Too Large"
    assert "5MB" in body["error_detail"]


# ── 5MB boundary: exactly at limit is accepted ────────────────────────────────


def test_content_length_exactly_5mb_is_not_rejected(client: TestClient) -> None:
    """Content-Length == 5MB must NOT trigger Response Too Large (boundary is exclusive)."""
    with respx.mock:
        # Non-HTML type confirms the body-size check did not fire;
        # the error here should be Non-HTML Response, not Response Too Large.
        respx.get("https://example.com/exact-cl").mock(
            return_value=httpx.Response(
                200,
                headers={
                    "content-type": "application/octet-stream",
                    "content-length": str(_5MB),
                },
                content=b"",  # actual body irrelevant for the Content-Length header check
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/exact-cl"})

    body = r.json()
    assert body["error"] != "Response Too Large"


def test_streamed_body_exactly_5mb_is_not_rejected(client: TestClient) -> None:
    """Streamed body of exactly 5MB must NOT trigger Response Too Large."""
    with respx.mock:
        respx.get("https://example.com/exact-stream").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "application/octet-stream"},
                content=b"x" * _5MB,
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/exact-stream"})

    body = r.json()
    assert body["error"] != "Response Too Large"


# ── Non-UTF-8 HTML handling ───────────────────────────────────────────────────


def test_extractor_latin1_bytes_no_crash() -> None:
    """Latin-1 encoded bytes are handled without raising; result is returned."""
    # 'é'=0xE9, 'ö'=0xF6 in Latin-1
    html = (
        b"<html><head>"
        b"<meta charset='iso-8859-1'>"
        b"<title>H\xe9llo W\xf6rld</title>"
        b"</head><body></body></html>"
    )
    result = extract_metadata(html)
    assert result is not None


def test_extractor_arbitrary_high_bytes_no_crash() -> None:
    """HTML containing arbitrary byte values (invalid UTF-8) does not crash."""
    html = b"<html><head><title>\x80\x90\xff</title></head><body></body></html>"
    result = extract_metadata(html)
    assert result is not None


def test_api_latin1_html_returns_200_no_crash(client: TestClient) -> None:
    """API returns 200 for a Latin-1 encoded HTML response — no 500 crash."""
    html = (
        b"<html><head>"
        b"<meta charset='iso-8859-1'>"
        b"<title>Caf\xe9</title>"
        b"</head><body></body></html>"
    )
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html; charset=iso-8859-1"},
                content=html,
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com"})

    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None


def test_api_empty_html_body_returns_200_all_fields_null(client: TestClient) -> None:
    """Empty HTML body (0 bytes) is accepted gracefully; all metadata fields are None."""
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"",
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com"})

    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["title"] is None
    assert body["meta_description"] is None
    assert body["og"]["title"] is None
    assert body["twitter"]["card"] is None
    assert body["canonical_url"] is None
