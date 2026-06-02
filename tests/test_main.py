"""Integration tests for FastAPI routes."""

from unittest.mock import patch

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from app.main import app


def _pass(*_a: object, **_k: object) -> None:
    """No-op validate_url substitute — bypasses real DNS in route tests."""


def _html_response(
    status: int = 200,
    body: bytes = b"<html><head><title>Test</title></head><body></body></html>",
    content_type: str = "text/html; charset=utf-8",
) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"content-type": content_type},
        content=body,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ---- Health check ----


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---- Static file ----


def test_index_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ---- Empty URL → 422 Invalid URL ----


def test_empty_url_returns_422(client: TestClient) -> None:
    r = client.post("/api/inspect", json={"url": ""})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Invalid URL"
    assert body["error_detail"]


# ---- SSRF URL → 422 Forbidden Target ----


def test_ssrf_url_returns_422(client: TestClient) -> None:
    r = client.post("/api/inspect", json={"url": "http://127.0.0.1"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Forbidden Target"
    assert body["error_detail"]


# ---- Non-HTTP scheme → 422 Invalid URL ----


def test_ftp_url_returns_422(client: TestClient) -> None:
    r = client.post("/api/inspect", json={"url": "ftp://example.com"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Invalid URL"
    assert body["error_detail"]


# ---- Whitespace stripping ----


def test_whitespace_stripped_before_validation(client: TestClient) -> None:
    """Leading/trailing whitespace is stripped; padded SSRF URL is still blocked."""
    r = client.post("/api/inspect", json={"url": "  http://127.0.0.1  "})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Forbidden Target"


# ---- Success → 200 InspectResponse with all FR-02 fields ----


def test_success_returns_inspect_response(client: TestClient) -> None:
    html = (
        b"<html><head>"
        b"<title>Example Domain</title>"
        b'<meta name="description" content="An example page.">'
        b'<meta property="og:title" content="Example OG">'
        b'<link rel="canonical" href="https://example.com/">'
        b"</head><body></body></html>"
    )
    with respx.mock:
        # httpx 0.28+ normalises https://example.com → https://example.com/
        respx.get("https://example.com/").mock(return_value=_html_response(body=html))
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com"})

    assert r.status_code == 200
    body = r.json()
    assert body["url_submitted"] == "https://example.com"
    assert body["final_url"] == "https://example.com"
    assert body["status_code"] == 200
    assert body["title"] == "Example Domain"
    assert body["meta_description"] == "An example page."
    assert body["og"]["title"] == "Example OG"
    assert body["canonical_url"] == "https://example.com/"
    assert "twitter" in body
    assert "redirect_chain" in body
    assert body["error"] is None
    assert body["error_detail"] is None


# ---- Non-HTML content-type → 502 ----


def test_non_html_returns_502(client: TestClient) -> None:
    with respx.mock:
        respx.get("https://example.com/doc.pdf").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF",
            )
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://example.com/doc.pdf"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "Non-HTML Response"
    assert body["upstream_status_code"] == 200
    assert body["upstream_content_type"] == "application/pdf"


# ---- Connection timeout → 504 ----


def test_timeout_returns_504(client: TestClient) -> None:
    with respx.mock:
        respx.get("https://slow.example.com/").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://slow.example.com"})

    assert r.status_code == 504
    body = r.json()
    assert body["error"] == "Connection Timeout"
    assert body["error_detail"]


# ---- DNS / connect failure → 502 ----


def test_dns_failure_returns_502(client: TestClient) -> None:
    with respx.mock:
        respx.get("https://unreachable.invalid/").mock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
        with patch("app.fetcher.validate_url", side_effect=_pass):
            r = client.post("/api/inspect", json={"url": "https://unreachable.invalid"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "DNS Failure"
    assert body["error_detail"]


# ---- Excessive redirects (11 hops) → 502 ----


def test_excessive_redirects_returns_502(client: TestClient) -> None:
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
