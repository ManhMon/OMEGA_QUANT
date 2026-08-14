from email.message import Message
import os

import pytest

from omega.data.official_watermark import (
    _OFFICIAL_SOURCE_URLS,
    STATUS_CANDIDATE_DATE_MISMATCH,
    STATUS_RECEIPT_INVALID,
    WatermarkContractError,
    _OfficialSourceResponse,
    _acquire_official_source,
    _structured_response_matches,
)


class FakeResponse:
    def __init__(self, body, url=None, status=200, content_type="text/html"):
        self.body = body
        self.url = url or _OFFICIAL_SOURCE_URLS["HSX"]
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self):
        return self.body


def opener_for(response, expected_url=_OFFICIAL_SOURCE_URLS["HSX"]):
    def opener(request, timeout, context):
        assert request.full_url == expected_url
        assert timeout == 30
        assert context.verify_mode == 2
        return response
    return opener


def test_official_source_response_is_validated_before_receipt_use(monkeypatch):
    monkeypatch.setenv("VCI_API_TOKEN", "test-token")
    monkeypatch.setattr("omega.data.official_watermark.urlopen", opener_for(FakeResponse(b'{"success":true,"data":[{"date":"2026-07-28","exchange":"HSX"}]}', content_type="application/json")))
    result = _acquire_official_source(
        "HSX", "2026-07-28",
    )
    assert isinstance(result, _OfficialSourceResponse)
    assert result.status == 200
    assert result.content_type == "application/json"


def test_caller_cannot_override_official_source():
    with pytest.raises(TypeError):
        _acquire_official_source("HSX", "2026-07-28", official_urls={})


def test_http_official_endpoint_is_rejected(monkeypatch):
    with pytest.raises(WatermarkContractError) as exc:
        from omega.data.official_watermark import _require_official_url
        _require_official_url("HSX", "http://official.example/hsx")
    assert exc.value.status == "url_not_allowed"


@pytest.mark.parametrize("response", [
    FakeResponse(b'{"success":true}', status=401),
    FakeResponse(b'{"success":true}', status=404),
    FakeResponse(b'{"success":true,"data":[{"date":"2026-07-28","exchange":"HSX"}]}', status=500),
    FakeResponse(b'{"success":true,"data":[{"date":"2026-07-28","exchange":"HSX"}]}', url="https://evil.example/redirect", content_type="application/json"),
    FakeResponse(b'{"success":true,"data":[{"date":"2026-07-28","exchange":"HSX"}]}', content_type="text/html"),
])
def test_unsafe_official_response_fails_closed(response):
    os.environ["VCI_API_TOKEN"] = "test-token"
    import omega.data.official_watermark as module
    module.urlopen = opener_for(response)
    with pytest.raises(WatermarkContractError) as exc:
         _acquire_official_source("HSX", "2026-07-28")
    assert exc.value.status == STATUS_RECEIPT_INVALID


def test_nonmatching_official_page_fails_closed():
    os.environ["VCI_API_TOKEN"] = "test-token"
    import omega.data.official_watermark as module
    module.urlopen = opener_for(FakeResponse(b'{"success":true,"data":[{"date":"2026-07-27","exchange":"HSX"}]}', content_type="application/json"))
    with pytest.raises(WatermarkContractError) as exc:
        _acquire_official_source("HSX", "2026-07-28")
    assert exc.value.status == STATUS_CANDIDATE_DATE_MISMATCH


def test_invalid_json_fails_closed():
    os.environ["VCI_API_TOKEN"] = "test-token"
    import omega.data.official_watermark as module
    module.urlopen = opener_for(FakeResponse(b"not-json", content_type="application/json"))
    with pytest.raises(WatermarkContractError) as exc:
        _acquire_official_source("HSX", "2026-07-28")
    assert exc.value.status == STATUS_RECEIPT_INVALID


def test_structured_response_requires_exact_date_and_exchange():
    assert _structured_response_matches(
        {"success": True, "data": [{"date": "2026-07-28", "exchange": "HSX"}]},
        "HSX", "2026-07-28"
    )
    assert not _structured_response_matches(
        {"success": True, "data": [{"date": "2026-07-28", "exchange": "HNX"}]},
        "HSX", "2026-07-28"
    )
    assert not _structured_response_matches(
        {"success": True, "data": [{"date": "2026-07-28Tinvalid", "exchange": "HSX"}]},
        "HSX", "2026-07-28",
    )


def test_text_marker_is_not_authoritative():
    assert not _structured_response_matches("HSX 2026-07-28", "HSX", "2026-07-28")
