"""Gemini image-generation backend via httpx (no vendor SDK).

API key/models come from core_config.Settings (env vars); the CLI may override
the image model per invocation. Fails loudly on HTTP errors, refusals, and
responses without an image — no retries, no fallbacks.
"""

import base64

import httpx

from tg_sticker_shot.api_base import BackendError
from tg_sticker_shot.core_config import Settings

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT_SECONDS = 120


class GeminiBackend:
    name = "gemini"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        model: str | None = None,
    ) -> None:
        self.model_id = model or settings.gemini_model
        self._review_model = settings.gemini_review_model
        self._client = httpx.Client(
            base_url=_BASE_URL,
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    def generate(self, refs: list[bytes], prompt: str) -> bytes:
        return _extract_image(self._generate_content(self.model_id, refs, prompt))

    def critique(self, images: list[bytes], prompt: str) -> str:
        return _extract_text(self._generate_content(self._review_model, images, prompt))

    def _generate_content(self, model: str, images: list[bytes], prompt: str) -> dict[str, object]:
        parts: list[dict[str, object]] = [
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image).decode()}}
            for image in images
        ]
        parts.append({"text": prompt})
        response = self._client.post(
            f"/models/{model}:generateContent",
            json={"contents": [{"parts": parts}]},
        )
        if response.status_code != httpx.codes.OK:
            raise BackendError(
                f"Gemini request failed with HTTP {response.status_code}: {response.text}"
            )
        return response.json()


def _candidate_parts(payload: dict[str, object]) -> list[object]:
    """The parts of the first candidate of a generateContent response."""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise BackendError(f"Gemini returned no candidates (refusal/filter?): {payload}")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    return parts if isinstance(parts, list) else []


def _extract_image(payload: dict[str, object]) -> bytes:
    """Pull the first inline image out of a generateContent response."""
    for part in _candidate_parts(payload):
        if not isinstance(part, dict):
            continue
        # The REST API documents camelCase; accept snake_case too.
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return base64.b64decode(inline["data"])
    raise BackendError(f"Gemini response contained no image part: {payload}")


def _extract_text(payload: dict[str, object]) -> str:
    """Concatenate the text parts of a generateContent response."""
    texts = [
        part["text"]
        for part in _candidate_parts(payload)
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        raise BackendError(f"Gemini response contained no text part: {payload}")
    return "".join(texts)
