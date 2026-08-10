"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.extractor import extract_metadata
from app.fetcher import fetch_url
from app.models import (
    ErrorResponse,
    InspectRequest,
    InspectResponse,
    OGTagsResponse,
    RedirectHopResponse,
    TwitterTagsResponse,
)

app = FastAPI(title="URL Inspector", version="1.0")

# Resolved from this module's location, not the process working directory.
# A relative "static/index.html" only works when the server happens to be
# started from the repository root, which is not guaranteed by every container
# runtime or process supervisor.
_STATIC_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"

# Error codes that indicate a client-side problem → 422
_CLIENT_ERRORS = {"Invalid URL", "Forbidden Target"}
# Error codes that indicate an upstream/server-side problem → 502
_SERVER_ERRORS = {
    "DNS Failure",
    "Excessive Redirects",
    "Response Too Large",
    "Fetch Failed",
}
# Error codes that indicate a timeout → 504
_TIMEOUT_ERRORS = {"Connection Timeout"}


def _hop_list(hops: list) -> list[RedirectHopResponse]:
    return [RedirectHopResponse(url=h.url, status_code=h.status_code) for h in hops]


@app.get("/health")
async def health() -> JSONResponse:
    """Return service health status."""
    return JSONResponse({"status": "ok"})


@app.get("/")
async def index() -> FileResponse:
    """Serve the frontend single-page application."""
    return FileResponse(_STATIC_INDEX)


@app.post("/api/inspect")
async def inspect(request: InspectRequest) -> JSONResponse:
    """Inspect a URL and return its metadata."""
    url = request.url.strip()

    result = await fetch_url(url)

    if result.error in _CLIENT_ERRORS:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=result.error,
                error_detail=result.error_detail,
            ).model_dump(),
        )

    if result.error in _TIMEOUT_ERRORS:
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                error=result.error,
                error_detail=result.error_detail,
            ).model_dump(),
        )

    if result.error in _SERVER_ERRORS:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=result.error,
                error_detail=result.error_detail,
                upstream_status_code=result.status_code,
                upstream_content_type=result.content_type,
                redirect_chain=_hop_list(result.redirect_chain),
            ).model_dump(),
        )

    if result.error is not None:
        # Unrecognised error code — surface as 502 rather than silently succeed.
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=result.error,
                error_detail=result.error_detail,
            ).model_dump(),
        )

    # Successful fetch — check content type before parsing HTML.
    ct = result.content_type or ""
    if not ct.startswith("text/html"):
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="Non-HTML Response",
                error_detail=(
                    f"The URL returned content-type: {ct or 'unknown'}."
                    " Metadata is not available."
                ),
                upstream_status_code=result.status_code,
                upstream_content_type=result.content_type,
                redirect_chain=_hop_list(result.redirect_chain),
            ).model_dump(),
        )

    metadata = extract_metadata(result.body or b"")

    return JSONResponse(
        status_code=200,
        content=InspectResponse(
            url_submitted=result.url_submitted,
            final_url=result.final_url or result.url_submitted,
            status_code=result.status_code or 0,
            content_type=result.content_type,
            redirect_chain=_hop_list(result.redirect_chain),
            redirect_excessive=result.redirect_excessive,
            title=metadata.title,
            meta_description=metadata.meta_description,
            og=OGTagsResponse(
                title=metadata.og.title,
                description=metadata.og.description,
                image=metadata.og.image,
                url=metadata.og.url,
                type=metadata.og.type,
            ),
            twitter=TwitterTagsResponse(
                title=metadata.twitter.title,
                description=metadata.twitter.description,
                image=metadata.twitter.image,
                card=metadata.twitter.card,
            ),
            canonical_url=metadata.canonical_url,
        ).model_dump(),
    )
