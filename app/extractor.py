"""BeautifulSoup4 metadata extraction from HTML."""

from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class OGTags:
    """Open Graph meta tag values."""

    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None


@dataclass
class TwitterTags:
    """Twitter Card meta tag values."""

    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    card: Optional[str] = None


@dataclass
class MetadataResult:
    """Extracted metadata from an HTML document."""

    title: Optional[str] = None
    meta_description: Optional[str] = None
    og: OGTags = field(default_factory=OGTags)
    twitter: TwitterTags = field(default_factory=TwitterTags)
    canonical_url: Optional[str] = None


def _get_meta_content(soup: BeautifulSoup, attr: str, value: str) -> Optional[str]:
    """Return content of first <meta> where attr matches value (case-insensitive)."""
    tag = soup.find("meta", attrs={attr: lambda v: v and v.lower() == value})
    if tag is None:
        return None
    content = tag.get("content")
    if content is None:
        return None
    stripped = str(content).strip()
    return stripped if stripped else None


def extract_metadata(html: bytes) -> MetadataResult:
    """Extract metadata from raw HTML bytes.

    Never raises — returns whatever was successfully extracted. Missing fields
    are None. Malformed HTML is handled gracefully by lxml's lenient parser.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return MetadataResult()

    result = MetadataResult()

    # <title>
    title_tag = soup.find("title")
    if title_tag is not None:
        text = title_tag.get_text().strip()
        result.title = text if text else None

    # <meta name="description">
    result.meta_description = _get_meta_content(soup, "name", "description")

    # OG tags — matched via property attribute
    result.og = OGTags(
        title=_get_meta_content(soup, "property", "og:title"),
        description=_get_meta_content(soup, "property", "og:description"),
        image=_get_meta_content(soup, "property", "og:image"),
        url=_get_meta_content(soup, "property", "og:url"),
        type=_get_meta_content(soup, "property", "og:type"),
    )

    # Twitter Card tags — matched via name attribute (also check property as fallback)
    def _twitter(key: str) -> Optional[str]:
        val = _get_meta_content(soup, "name", f"twitter:{key}")
        if val is None:
            val = _get_meta_content(soup, "property", f"twitter:{key}")
        return val

    result.twitter = TwitterTags(
        title=_twitter("title"),
        description=_twitter("description"),
        image=_twitter("image"),
        card=_twitter("card"),
    )

    # <link rel="canonical">
    canonical_tag = soup.find("link", attrs={"rel": lambda v: v and "canonical" in [r.lower() for r in (v if isinstance(v, list) else [v])]})
    if canonical_tag is not None:
        href = canonical_tag.get("href")
        if href:
            stripped = str(href).strip()
            result.canonical_url = stripped if stripped else None

    return result
