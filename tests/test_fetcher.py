"""Tests for app.fetcher."""

from unittest.mock import patch

import httpx
import pytest
import respx

from app.fetcher import RedirectHop, fetch_url
from app.validator import ValidationError


def _html(status: int = 200, body: bytes = b"<html></html>") -> httpx.Response:
    return httpx.Response(
        status,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body,
    )


def _pass(*_a: object, **_k: object) -> None:
    """No-op validate_url substitute."""


# ---- Successful fetch ----


@pytest.mark.asyncio
@respx.mock
async def test_successful_fetch_returns_body() -> None:
    body = b"<html><head><title>Hello</title></head></html>"
    respx.get("https://example.com").mock(return_value=_html(body=body))
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert result.error is None
    assert result.status_code == 200
    assert result.content_type == "text/html; charset=utf-8"
    assert result.body == body
    assert result.final_url == "https://example.com"
    assert result.redirect_excessive is False


@pytest.mark.asyncio
@respx.mock
async def test_successful_fetch_chain_has_one_entry() -> None:
    respx.get("https://example.com").mock(return_value=_html())
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert result.redirect_chain == [RedirectHop(url="https://example.com", status_code=200)]


# ---- Redirect chain ----


@pytest.mark.asyncio
@respx.mock
async def test_redirect_chain_captured() -> None:
    respx.get("https://example.com").mock(
        return_value=httpx.Response(301, headers={"location": "https://www.example.com"})
    )
    respx.get("https://www.example.com").mock(return_value=_html())
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert result.error is None
    assert result.final_url == "https://www.example.com"
    assert len(result.redirect_chain) == 2
    assert result.redirect_chain[0] == RedirectHop(url="https://example.com", status_code=301)
    assert result.redirect_chain[1] == RedirectHop(url="https://www.example.com", status_code=200)


@pytest.mark.asyncio
@respx.mock
async def test_follow_redirects_false_confirmed_by_chain() -> None:
    """Two chain entries proves follow_redirects=False; auto-follow would give one."""
    respx.get("https://example.com").mock(
        return_value=httpx.Response(302, headers={"location": "https://www.example.com"})
    )
    respx.get("https://www.example.com").mock(return_value=_html())
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert len(result.redirect_chain) == 2
    assert result.redirect_chain[0].status_code == 302


# ---- Excessive redirects ----


@pytest.mark.asyncio
@respx.mock
async def test_excessive_redirects() -> None:
    """11 redirect hops triggers error; all 11 hops are in the chain."""
    for i in range(11):
        respx.get(f"https://example.com/r/{i}").mock(
            return_value=httpx.Response(
                301, headers={"location": f"https://example.com/r/{i + 1}"}
            )
        )
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com/r/0")
    assert result.error == "Excessive Redirects"
    assert result.redirect_excessive is True
    assert len(result.redirect_chain) == 11
    assert result.status_code is None


@pytest.mark.asyncio
@respx.mock
async def test_exactly_10_redirects_succeeds() -> None:
    """10 redirects followed by a 200 is within the limit."""
    for i in range(10):
        respx.get(f"https://example.com/r/{i}").mock(
            return_value=httpx.Response(
                301, headers={"location": f"https://example.com/r/{i + 1}"}
            )
        )
    respx.get("https://example.com/r/10").mock(return_value=_html())
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com/r/0")
    assert result.error is None
    assert len(result.redirect_chain) == 11
    assert result.redirect_excessive is False


# ---- DNS failure ----


@pytest.mark.asyncio
@respx.mock
async def test_dns_failure() -> None:
    respx.get("https://unreachable.invalid").mock(
        side_effect=httpx.ConnectError("Name or service not known")
    )
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://unreachable.invalid")
    assert result.error == "DNS Failure"
    assert result.status_code is None
    assert result.body is None


# ---- Connection timeout ----


@pytest.mark.asyncio
@respx.mock
async def test_connection_timeout() -> None:
    respx.get("https://slow.example.com").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://slow.example.com")
    assert result.error == "Connection Timeout"
    assert result.status_code is None
    assert result.body is None


# ---- Content-Length > 5MB ----


@pytest.mark.asyncio
@respx.mock
async def test_content_length_too_large() -> None:
    """Content-Length header > 5MB returns error without reading body."""
    six_mb = 6 * 1024 * 1024
    respx.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": str(six_mb)},
            content=b"",
        )
    )
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert result.error == "Response Too Large"
    assert result.body is None
    assert result.status_code == 200


# ---- Streamed body > 5MB ----


@pytest.mark.asyncio
@respx.mock
async def test_streamed_body_too_large() -> None:
    """No Content-Length header; streamed body exceeds 5MB limit."""
    respx.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * (6 * 1024 * 1024),
        )
    )
    with patch("app.fetcher.validate_url", side_effect=_pass):
        result = await fetch_url("https://example.com")
    assert result.error == "Response Too Large"
    assert result.body is None
    assert result.status_code == 200


# ---- SSRF-blocked redirect hop ----


@pytest.mark.asyncio
@respx.mock
async def test_ssrf_blocked_redirect_hop() -> None:
    """Initial URL passes; redirect destination is a private IP."""
    respx.get("https://example.com").mock(
        return_value=httpx.Response(301, headers={"location": "http://192.168.1.1"})
    )

    def fake_validate(url: str) -> None:
        if "192.168" in url:
            raise ValidationError("Forbidden Target", "Resolves to private IP.")

    with patch("app.fetcher.validate_url", side_effect=fake_validate):
        result = await fetch_url("https://example.com")
    assert result.error == "Forbidden Target"
    assert len(result.redirect_chain) == 1
    assert result.redirect_chain[0].status_code == 301
    assert result.status_code is None


# ---- Initial URL validation ----


@pytest.mark.asyncio
async def test_initial_url_invalid_scheme() -> None:
    """Invalid scheme rejected before any HTTP call is made."""
    result = await fetch_url("ftp://example.com")
    assert result.error == "Invalid URL"
    assert result.redirect_chain == []


@pytest.mark.asyncio
async def test_initial_url_ssrf_blocked() -> None:
    """Private IP in initial URL blocked before any HTTP call."""
    result = await fetch_url("http://192.168.1.1")
    assert result.error == "Forbidden Target"
    assert result.redirect_chain == []

