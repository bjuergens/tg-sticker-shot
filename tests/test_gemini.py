"""Offline tests for the Gemini backend via httpx.MockTransport, plus one
manual real-API smoke test (marker `gemini_smoke`, deselected by default)."""

import base64
import json
import os

import httpx
import pytest

from tg_sticker_shot.api_base import BackendError
from tg_sticker_shot.api_fake import FIXTURE_PNG
from tg_sticker_shot.api_gemini import GeminiBackend
from tg_sticker_shot.core_config import Settings


def _settings() -> Settings:
    return Settings(
        GEMINI_API_KEY="test-key",
        GEMINI_MODEL="test-model",
        GEMINI_REVIEW_MODEL="test-review-model",
    )


def _image_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "here you go"},
                            {"inlineData": {"data": base64.b64encode(FIXTURE_PNG).decode()}},
                        ]
                    }
                }
            ]
        },
    )


def test_request_shape_and_image_extraction() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _image_response()

    backend = GeminiBackend(_settings(), transport=httpx.MockTransport(handler))
    image = backend.generate([FIXTURE_PNG], "a chibi sticker")

    assert image == FIXTURE_PNG
    request = seen[0]
    assert request.url.path.endswith("/models/test-model:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    payload = json.loads(request.content)
    parts = payload["contents"][0]["parts"]
    assert parts[0]["inline_data"]["data"] == base64.b64encode(FIXTURE_PNG).decode()
    assert parts[-1] == {"text": "a chibi sticker"}


def test_model_override_wins_over_settings() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _image_response()

    backend = GeminiBackend(
        _settings(), transport=httpx.MockTransport(handler), model="override-model"
    )
    assert backend.model_id == "override-model"
    backend.generate([FIXTURE_PNG], "prompt")
    assert seen[0].url.path.endswith("/models/override-model:generateContent")


def test_critique_uses_review_model_and_extracts_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"identity"'}, {"text": ": 9}"}]}}]
            },
        )

    backend = GeminiBackend(_settings(), transport=httpx.MockTransport(handler))
    text = backend.critique([FIXTURE_PNG], "rate this sticker")

    assert text == '{"identity": 9}'  # text parts are concatenated
    request = seen[0]
    assert request.url.path.endswith("/models/test-review-model:generateContent")
    payload = json.loads(request.content)
    parts = payload["contents"][0]["parts"]
    assert parts[0]["inline_data"]["data"] == base64.b64encode(FIXTURE_PNG).decode()
    assert parts[-1] == {"text": "rate this sticker"}


def test_critique_without_text_part_raises() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"data": base64.b64encode(FIXTURE_PNG).decode()}}
                            ]
                        }
                    }
                ]
            },
        )
    )
    backend = GeminiBackend(_settings(), transport=transport)
    with pytest.raises(BackendError, match="no text part"):
        backend.critique([FIXTURE_PNG], "prompt")


def test_snake_case_inline_data_is_accepted() -> None:
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"inline_data": {"data": base64.b64encode(FIXTURE_PNG).decode()}}]
                    }
                }
            ]
        },
    )
    backend = GeminiBackend(_settings(), transport=httpx.MockTransport(lambda _: response))
    assert backend.generate([], "prompt") == FIXTURE_PNG


def test_http_error_raises() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(429, text="quota exceeded"))
    backend = GeminiBackend(_settings(), transport=transport)
    with pytest.raises(BackendError, match="HTTP 429"):
        backend.generate([FIXTURE_PNG], "prompt")


def test_no_candidates_raises() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
    )
    backend = GeminiBackend(_settings(), transport=transport)
    with pytest.raises(BackendError, match="no candidates"):
        backend.generate([FIXTURE_PNG], "prompt")


def test_no_image_part_raises() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "I cannot do that"}]}}]},
        )
    )
    backend = GeminiBackend(_settings(), transport=transport)
    with pytest.raises(BackendError, match="no image part"):
        backend.generate([FIXTURE_PNG], "prompt")


@pytest.mark.gemini_smoke
def test_real_gemini_smoke() -> None:
    """Manual smoke test against the real API: uv run pytest -m gemini_smoke.

    Requires GEMINI_API_KEY in the environment; costs one cheap generation.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    backend = GeminiBackend(Settings())  # pyright: ignore[reportCallIssue]
    image = backend.generate(
        [FIXTURE_PNG],
        "A single cute cartoon smiley sticker, plain white background, no text.",
    )
    assert image.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8"))  # PNG or JPEG
