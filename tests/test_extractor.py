"""Tests for app.extractor."""

from pathlib import Path


from app.extractor import MetadataResult, extract_metadata

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestFullMetadata:
    """All metadata fields present and populated."""

    def setup_method(self):
        self.result = extract_metadata(load_fixture("full_metadata.html"))

    def test_returns_metadata_result(self):
        assert isinstance(self.result, MetadataResult)

    def test_title(self):
        assert self.result.title == "Full Metadata Test Page"

    def test_meta_description(self):
        assert self.result.meta_description == "A test page with all metadata fields populated."

    def test_og_title(self):
        assert self.result.og.title == "OG Title Value"

    def test_og_description(self):
        assert self.result.og.description == "OG description value."

    def test_og_image(self):
        assert self.result.og.image == "https://example.com/image.png"

    def test_og_url(self):
        assert self.result.og.url == "https://example.com/page"

    def test_og_type(self):
        assert self.result.og.type == "article"

    def test_twitter_card(self):
        assert self.result.twitter.card == "summary_large_image"

    def test_twitter_title(self):
        assert self.result.twitter.title == "Twitter Title Value"

    def test_twitter_description(self):
        assert self.result.twitter.description == "Twitter description value."

    def test_twitter_image(self):
        assert self.result.twitter.image == "https://example.com/twitter-image.png"

    def test_canonical_url(self):
        assert self.result.canonical_url == "https://example.com/canonical"


class TestPartialMetadata:
    """Only title and description present; OG and Twitter fields should be None."""

    def setup_method(self):
        self.result = extract_metadata(load_fixture("partial_metadata.html"))

    def test_title(self):
        assert self.result.title == "Partial Metadata Page"

    def test_meta_description(self):
        assert self.result.meta_description == "Only a description and title; no OG or Twitter tags."

    def test_og_title_is_none(self):
        assert self.result.og.title is None

    def test_og_description_is_none(self):
        assert self.result.og.description is None

    def test_og_image_is_none(self):
        assert self.result.og.image is None

    def test_og_url_is_none(self):
        assert self.result.og.url is None

    def test_og_type_is_none(self):
        assert self.result.og.type is None

    def test_twitter_title_is_none(self):
        assert self.result.twitter.title is None

    def test_twitter_description_is_none(self):
        assert self.result.twitter.description is None

    def test_twitter_image_is_none(self):
        assert self.result.twitter.image is None

    def test_twitter_card_is_none(self):
        assert self.result.twitter.card is None

    def test_canonical_url_is_none(self):
        assert self.result.canonical_url is None


class TestEmptyHTML:
    """Minimal HTML with no metadata — all fields should be None."""

    def setup_method(self):
        self.result = extract_metadata(load_fixture("empty.html"))

    def test_returns_metadata_result(self):
        assert isinstance(self.result, MetadataResult)

    def test_title_is_none(self):
        assert self.result.title is None

    def test_meta_description_is_none(self):
        assert self.result.meta_description is None

    def test_og_is_all_none(self):
        og = self.result.og
        assert og.title is None
        assert og.description is None
        assert og.image is None
        assert og.url is None
        assert og.type is None

    def test_twitter_is_all_none(self):
        tw = self.result.twitter
        assert tw.title is None
        assert tw.description is None
        assert tw.image is None
        assert tw.card is None

    def test_canonical_url_is_none(self):
        assert self.result.canonical_url is None


class TestMalformedHTML:
    """Malformed HTML must not raise; extractor returns whatever it can."""

    def test_does_not_raise(self):
        html = load_fixture("malformed.html")
        result = extract_metadata(html)
        assert isinstance(result, MetadataResult)

    def test_extracts_title_from_malformed(self):
        html = load_fixture("malformed.html")
        result = extract_metadata(html)
        # lxml is lenient; it will recover title if it can
        assert result.title == "Malformed Title"

    def test_extracts_description_from_malformed(self):
        html = load_fixture("malformed.html")
        result = extract_metadata(html)
        assert result.meta_description == "Malformed page description"

    def test_extracts_og_title_from_malformed(self):
        html = load_fixture("malformed.html")
        result = extract_metadata(html)
        assert result.og.title == "Malformed OG Title"


class TestMissingFieldsAreNone:
    """Explicitly confirm that missing fields return None, not empty string."""

    def test_missing_title_is_none_not_empty(self):
        html = b"<html><head></head><body></body></html>"
        result = extract_metadata(html)
        assert result.title is None
        assert result.title != ""

    def test_missing_og_url_is_none_not_empty(self):
        html = b"<html><head><meta property='og:title' content='T'></head></html>"
        result = extract_metadata(html)
        assert result.og.url is None

    def test_empty_content_attribute_is_none(self):
        html = b"<html><head><meta name='description' content=''></head></html>"
        result = extract_metadata(html)
        assert result.meta_description is None

    def test_whitespace_only_title_is_none(self):
        html = b"<html><head><title>   </title></head></html>"
        result = extract_metadata(html)
        assert result.title is None


class TestCaseInsensitivity:
    """Meta attribute matching must be case-insensitive."""

    def test_og_property_uppercase(self):
        html = b"<html><head><meta property='OG:TITLE' content='Upper OG'></head></html>"
        result = extract_metadata(html)
        assert result.og.title == "Upper OG"

    def test_meta_name_mixed_case(self):
        html = b"<html><head><meta name='Description' content='Mixed Case Desc'></head></html>"
        result = extract_metadata(html)
        assert result.meta_description == "Mixed Case Desc"

    def test_twitter_name_uppercase(self):
        html = b"<html><head><meta name='TWITTER:CARD' content='summary'></head></html>"
        result = extract_metadata(html)
        assert result.twitter.card == "summary"


class TestTwitterPropertyFallback:
    """Twitter tags can use property= instead of name=; extractor must handle both."""

    def test_twitter_via_property_attribute(self):
        html = b"<html><head><meta property='twitter:title' content='Prop Twitter Title'></head></html>"
        result = extract_metadata(html)
        assert result.twitter.title == "Prop Twitter Title"


class TestRawBytesInput:
    """extract_metadata accepts bytes, including bytes with encoding declarations."""

    def test_utf8_bytes(self):
        # charset meta tag required so lxml decodes bytes as UTF-8, not Latin-1
        html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>UTF-8 Título</title></head></html>'.encode("utf-8")
        result = extract_metadata(html)
        assert result.title == "UTF-8 Título"

    def test_empty_bytes_does_not_raise(self):
        result = extract_metadata(b"")
        assert isinstance(result, MetadataResult)
        assert result.title is None
