"""HTTP fetch engine with manual redirect loop and body size cap."""

from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.validator import ValidationError, validate_url

_MAX_REDIRECT_HOPS = 10
_BODY_LIMIT = 5 * 1024 * 1024  # 5 MB
_USER_AGENT = "url-inspector/1.0"
_TIMEOUT = 10.0


@dataclass
class RedirectHop:
    """One hop in a redirect chain."""

    url: str
    status_code: int


@dataclass
class FetchResult:
    """Complete result of a fetch_url call."""

    url_submitted: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    body: bytes | None
    redirect_chain: list[RedirectHop] = field(default_factory=list)
    redirect_excessive: bool = False
    error: str | None = None
    error_detail: str | None = None


def _too_large_result(
    url_submitted: str,
    current_url: str,
    status_code: int | None,
    content_type: str | None,
    redirect_chain: list[RedirectHop],
) -> FetchResult:
    return FetchResult(
        url_submitted=url_submitted,
        final_url=current_url,
        status_code=status_code,
        content_type=content_type,
        body=None,
        redirect_chain=redirect_chain,
        redirect_excessive=False,
        error="Response Too Large",
        error_detail="Response body exceeds the 5MB limit.",
    )


async def fetch_url(url: str) -> FetchResult:
    """Fetch a URL with SSRF validation, manual redirect following, and a 5MB body cap.

    Every redirect destination is validated before following. follow_redirects is
    explicitly False on the httpx client — redirects are handled in the loop below.
    Justification for function length: the redirect loop, body streaming, and six
    distinct error conditions form a single state machine. Splitting them across
    helpers would fragment the control flow and make the states harder to audit.
    """
    url_submitted = url
    redirect_chain: list[RedirectHop] = []
    current_url = url

    try:
        validate_url(url)
    except ValidationError as exc:
        return FetchResult(
            url_submitted=url_submitted,
            final_url=None,
            status_code=None,
            content_type=None,
            body=None,
            error=exc.error_code,
            error_detail=exc.detail,
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            while True:
                async with client.stream("GET", current_url) as response:
                    redirect_chain.append(
                        RedirectHop(url=current_url, status_code=response.status_code)
                    )

                    if not response.is_redirect:
                        ct = response.headers.get("content-type")
                        cl_str = response.headers.get("content-length")
                        if cl_str:
                            try:
                                if int(cl_str) > _BODY_LIMIT:
                                    return _too_large_result(
                                        url_submitted, current_url,
                                        response.status_code, ct, redirect_chain,
                                    )
                            except ValueError:
                                pass

                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            total += len(chunk)
                            if total > _BODY_LIMIT:
                                return _too_large_result(
                                    url_submitted, current_url,
                                    response.status_code, ct, redirect_chain,
                                )
                            chunks.append(chunk)

                        return FetchResult(
                            url_submitted=url_submitted,
                            final_url=current_url,
                            status_code=response.status_code,
                            content_type=ct,
                            body=b"".join(chunks),
                            redirect_chain=redirect_chain,
                        )

                    location = response.headers.get("location")

                if len(redirect_chain) > _MAX_REDIRECT_HOPS:
                    return FetchResult(
                        url_submitted=url_submitted,
                        final_url=current_url,
                        status_code=None,
                        content_type=None,
                        body=None,
                        redirect_chain=redirect_chain,
                        redirect_excessive=True,
                        error="Excessive Redirects",
                        error_detail=f"Redirect chain exceeded {_MAX_REDIRECT_HOPS} hops.",
                    )

                if not location:
                    return FetchResult(
                        url_submitted=url_submitted,
                        final_url=current_url,
                        status_code=redirect_chain[-1].status_code,
                        content_type=None,
                        body=b"",
                        redirect_chain=redirect_chain,
                    )

                resolved = urljoin(current_url, location)

                try:
                    validate_url(resolved)
                except ValidationError as exc:
                    return FetchResult(
                        url_submitted=url_submitted,
                        final_url=resolved,
                        status_code=None,
                        content_type=None,
                        body=None,
                        redirect_chain=redirect_chain,
                        error=exc.error_code,
                        error_detail=exc.detail,
                    )

                current_url = resolved

    except httpx.TimeoutException:
        return FetchResult(
            url_submitted=url_submitted,
            final_url=current_url,
            status_code=None,
            content_type=None,
            body=None,
            redirect_chain=redirect_chain,
            error="Connection Timeout",
            error_detail="The request timed out after 10 seconds.",
        )

    except httpx.ConnectError:
        return FetchResult(
            url_submitted=url_submitted,
            final_url=None,
            status_code=None,
            content_type=None,
            body=None,
            redirect_chain=redirect_chain,
            error="DNS Failure",
            error_detail="Failed to connect to the host.",
        )

    except httpx.HTTPError as exc:
        # Every remaining transport failure — malformed HTTP from the upstream
        # server (RemoteProtocolError), a dropped read, an outbound proxy
        # refusal. Without this, such errors escape fetch_url and FastAPI
        # renders a bare 500 with a traceback, breaking the structured-error
        # contract that every other failure path here upholds. Inspecting
        # arbitrary user-supplied URLs means badly-behaved servers are the
        # normal case, not the exception.
        return FetchResult(
            url_submitted=url_submitted,
            final_url=current_url,
            status_code=None,
            content_type=None,
            body=None,
            redirect_chain=redirect_chain,
            error="Fetch Failed",
            error_detail=f"The request failed: {type(exc).__name__}.",
        )
