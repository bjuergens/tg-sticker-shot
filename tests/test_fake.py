"""The fixture PNG must be a genuinely valid PNG — the gemini_smoke test sends
it to the real API, and future post-processing will decode generated results."""

import struct
import zlib

from tg_sticker_shot.api_fake import FIXTURE_PNG, FakeBackend


def test_fixture_png_is_structurally_valid() -> None:
    assert FIXTURE_PNG[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    chunk_types: list[bytes] = []
    idat = b""
    while pos < len(FIXTURE_PNG):
        (length,) = struct.unpack(">I", FIXTURE_PNG[pos : pos + 4])
        chunk_type = FIXTURE_PNG[pos + 4 : pos + 8]
        data = FIXTURE_PNG[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", FIXTURE_PNG[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(chunk_type + data), f"bad CRC in {chunk_type!r}"
        chunk_types.append(chunk_type)
        if chunk_type == b"IDAT":
            idat += data
        pos += 12 + length
    assert pos == len(FIXTURE_PNG)  # no trailing garbage
    assert chunk_types == [b"IHDR", b"IDAT", b"IEND"]
    # 1x1 RGBA: one filter byte + 4 channel bytes.
    assert len(zlib.decompress(idat)) == 5


def test_fake_backend_records_calls() -> None:
    backend = FakeBackend()
    assert backend.generate([b"r1", b"r2"], "a prompt") == FIXTURE_PNG
    assert backend.calls == [(2, "a prompt")]
