"""Pydantic request and response models."""

from typing import Optional

from pydantic import BaseModel


class InspectRequest(BaseModel):
    """POST /api/inspect request body."""

    url: str


class RedirectHopResponse(BaseModel):
    """One hop in a redirect chain."""

    url: str
    status_code: int


class OGTagsResponse(BaseModel):
    """Open Graph tag values."""

    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None


class TwitterTagsResponse(BaseModel):
    """Twitter Card tag values."""

    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    card: Optional[str] = None


class InspectResponse(BaseModel):
    """Successful metadata inspection result (HTTP 200)."""

    url_submitted: str
    final_url: str
    status_code: int
    content_type: Optional[str] = None
    redirect_chain: list[RedirectHopResponse] = []
    redirect_excessive: bool = False
    title: Optional[str] = None
    meta_description: Optional[str] = None
    og: OGTagsResponse = OGTagsResponse()
    twitter: TwitterTagsResponse = TwitterTagsResponse()
    canonical_url: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response body (HTTP 422 / 502 / 504)."""

    error: str
    error_detail: Optional[str] = None
    upstream_status_code: Optional[int] = None
    upstream_content_type: Optional[str] = None
    redirect_chain: list[RedirectHopResponse] = []
