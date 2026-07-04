"""Fake image backend: returns a fixture PNG, records calls.

Enables full pipeline tests (and offline CLI runs) with no secrets and no mocking.
"""

# A valid 1x1 transparent PNG.
FIXTURE_PNG = bytes.fromhex(
    "89504e470d0a1a0a"  # signature
    "0000000d49484452000000010000000108060000001f15c489"  # IHDR 1x1 RGBA
    "0000000d4944415478da63f8ffff3f0300080101ba34dc7c"  # IDAT
    "0000000049454e44ae426082"  # IEND
)


class FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def generate(self, refs: list[bytes], prompt: str) -> bytes:
        self.calls.append((len(refs), prompt))
        return FIXTURE_PNG
