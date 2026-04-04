"""Tests for helper functions: _strip_html, _parse_commons_response, _session."""

from app import USER_AGENT, _parse_commons_response, _session, _strip_html


class TestSession:
    def test_commons_session_has_user_agent(self):
        assert _session.headers["User-Agent"] == USER_AGENT


class TestStripHtml:
    def test_removes_simple_tag(self):
        assert _strip_html("<b>bold</b>") == "bold"

    def test_removes_nested_tags(self):
        assert _strip_html("<p><em>text</em></p>") == "text"

    def test_removes_tag_with_attributes(self):
        assert _strip_html('<a href="http://example.com">link</a>') == "link"

    def test_no_tags(self):
        assert _strip_html("plain text") == "plain text"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_self_closing_tag(self):
        assert _strip_html("before<br />after") == "beforeafter"

    def test_attribute_containing_gt(self):
        assert _strip_html('<span title="a > b">text</span>') == "text"

    def test_html_comment(self):
        assert _strip_html("before<!-- comment -->after") == "beforeafter"

    def test_bare_angle_bracket(self):
        assert _strip_html("a < b and c > d") == "a &lt; b and c &gt; d"

    def test_script_tag_content_removed(self):
        assert _strip_html("<script>alert('xss')</script>") == ""


class TestParseCommonsResponse:
    def test_successful_cc_by_sa(self, commons_cc_by_sa):
        result = _parse_commons_response(commons_cc_by_sa)
        assert "error" not in result
        assert result["license_title"] == "CC BY-SA 4.0"
        assert result["license_url"] == "https://creativecommons.org/licenses/by-sa/4.0"
        assert result["file_title"] == "Sempervivum x funckii.jpg"
        assert result["upload_date"] == "2024-01-15"
        assert result["thumb_url"] == "https://upload.wikimedia.org/thumb.jpg"
        assert "Example" in result["credit"]

    def test_cc_by_hyphenated_normalised(self, commons_cc_by):
        """CC-BY-3.0 (hyphenated) should be normalised to CC BY 3.0."""
        result = _parse_commons_response(commons_cc_by)
        assert "error" not in result
        assert result["license_title"] == "CC BY 3.0"

    def test_public_domain(self, commons_public_domain):
        result = _parse_commons_response(commons_public_domain)
        assert result["error"] == "public_domain"
        assert "file_title" in result

    def test_cc0(self, commons_cc0):
        result = _parse_commons_response(commons_cc0)
        assert result["error"] == "cc0"

    def test_missing_file(self, commons_missing_file):
        result = _parse_commons_response(commons_missing_file)
        assert result["error"] == "missing_file"

    def test_gfdl_unsupported(self, commons_gfdl):
        result = _parse_commons_response(commons_gfdl)
        assert result["error"] == "unsupported_license"

    def test_no_license(self, commons_no_license):
        result = _parse_commons_response(commons_no_license)
        assert result["error"] == "no_license"

    def test_no_information(self, commons_no_information):
        result = _parse_commons_response(commons_no_information)
        assert result["error"] == "no_information"

    def test_empty_response(self):
        result = _parse_commons_response({})
        assert result["error"] == "missing_file"

    def test_description_extra_stripped(self, commons_cc_by_sa):
        result = _parse_commons_response(commons_cc_by_sa)
        # HTML should be stripped from description
        assert "<i>" not in result["description_extra"]
        assert "Sempervivum" in result["description_extra"]
