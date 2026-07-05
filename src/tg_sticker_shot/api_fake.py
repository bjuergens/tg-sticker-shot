"""Fake image backend: returns a fixture PNG, records calls.

Enables full pipeline tests (and offline CLI runs) with no secrets and no mocking.
"""

import json
import struct
import zlib


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data))
    )


# A valid 1x1 transparent PNG, built chunk by chunk so lengths and CRCs are
# correct by construction (the smoke test sends it to the real Gemini API).
FIXTURE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))  # 1x1, 8-bit RGBA
    + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))  # filter byte + 1 RGBA pixel
    + _png_chunk(b"IEND", b"")
)


# Default critique verdict: everything passes (tests preload critique_responses
# to simulate bad stickers).
GOOD_CRITIQUE = json.dumps(
    {"identity": 9, "emotion": 9, "quality": 9, "issues": "", "redo_hint": ""}
)


class FakeBackend:
    name = "fake"
    model_id = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.critique_calls: list[tuple[int, str]] = []
        self.critique_responses: list[str] = []

    def generate(self, refs: list[bytes], prompt: str) -> bytes:
        self.calls.append((len(refs), prompt))
        return FIXTURE_PNG

    def critique(self, images: list[bytes], prompt: str) -> str:
        self.critique_calls.append((len(images), prompt))
        if self.critique_responses:
            return self.critique_responses.pop(0)
        return GOOD_CRITIQUE
