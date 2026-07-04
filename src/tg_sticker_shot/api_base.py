"""Image-generation backend Protocol. Implementations: api_gemini.py, api_fake.py."""

from typing import Protocol


class BackendError(Exception):
    """The backend failed to produce an image (HTTP error, refusal, bad response)."""


class ImageBackend(Protocol):
    name: str

    def generate(self, refs: list[bytes], prompt: str) -> bytes:
        """Generate one PNG image from reference images and a prompt."""
        ...
