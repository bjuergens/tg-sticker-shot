"""Gemini image-generation backend via httpx (no vendor SDK).

API key/model come from core_config.Settings (env vars). Fails loudly on HTTP
errors, refusals, and responses without an image — no retries, no fallbacks.
"""

import base64

import httpx

from tg_sticker_shot.api_base import BackendError
from tg_sticker_shot.core_config import Settings

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT_SECONDS = 120


class GeminiBackend:
    name = "gemini"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._model = settings.gemini_model
        self._client = httpx.Client(
            base_url=_BASE_URL,
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    def generate(self, refs: list[bytes], prompt: str) -> bytes:
        parts: list[dict[str, object]] = [
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref).decode()}}
            for ref in refs
        ]
        parts.append({"text": prompt})
        response = self._client.post(
            f"/models/{self._model}:generateContent",
            json={"contents": [{"parts": parts}]},
        )
        if response.status_code != httpx.codes.OK:
            raise BackendError(
                f"Gemini request failed with HTTP {response.status_code}: {response.text}"
            )
        return _extract_image(response.json())


def _extract_image(payload: dict[str, object]) -> bytes:
    """Pull the first inline image out of a generateContent response."""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise BackendError(f"Gemini returned no candidates (refusal/filter?): {payload}")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    for part in parts if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        # The REST API documents camelCase; accept snake_case too.
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return base64.b64decode(inline["data"])
    raise BackendError(f"Gemini response contained no image part: {payload}")
