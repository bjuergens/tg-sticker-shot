from typer.testing import CliRunner

from tg_sticker_shot import __version__
from tg_sticker_shot.api_fake import FIXTURE_PNG
from tg_sticker_shot.core_emotions import load_emotions
from tg_sticker_shot.frontend_cli import Backend, _make_backend, app

STYLE_GUIDE = "chibi, bold outlines"

runner = CliRunner()


def _all_output(result) -> str:
    """stdout + stderr regardless of click version (mix_stderr changed in click 8.2)."""
    try:
        return result.output + result.stderr
    except ValueError:  # older click: stderr already mixed into output
        return result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_full_pipeline_via_cli(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    proj = str(tmp_path / "proj")

    result = runner.invoke(app, ["ingest", str(source), "--project", proj])
    assert result.exit_code == 0
    assert "✅ stored source_1.png" in result.output

    result = runner.invoke(app, ["refs", STYLE_GUIDE, "--project", proj, "--backend", "fake"])
    assert result.exit_code == 0
    assert "✅ generated ref_bust_1.png" in result.output
    assert "✅ generated ref_half_1.png" in result.output
    assert "✅ generated ref_full_1.png" in result.output

    result = runner.invoke(app, ["batch", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 0
    assert "✅ generated result_😂.png" in result.output

    result = runner.invoke(app, ["status", "--project", proj])
    assert result.exit_code == 0
    assert "sources: 1" in result.output
    assert "refs: 3" in result.output
    assert f"style guide: {STYLE_GUIDE}" in result.output
    assert "model: fake" in result.output
    assert f"results: {len(load_emotions())}" in result.output
    assert "missing: 0" in result.output

    # Re-running batch skips everything (idempotent).
    result = runner.invoke(app, ["batch", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 0
    assert "✅ generated" not in result.output
    assert "⚠️ skipped 😂" in result.output


def _project_with_results(tmp_path) -> str:
    """ingest → refs → batch on the fake backend; returns the project dir."""
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    proj = str(tmp_path / "proj")
    for args in (
        ["ingest", str(source), "--project", proj],
        ["refs", STYLE_GUIDE, "--project", proj, "--backend", "fake"],
        ["batch", "--project", proj, "--backend", "fake"],
    ):
        assert runner.invoke(app, args).exit_code == 0
    return proj


def test_redo_via_cli(tmp_path) -> None:
    proj = _project_with_results(tmp_path)
    result = runner.invoke(
        app,
        [
            "redo",
            "😂",
            "😢",
            "--project",
            proj,
            "--backend",
            "fake",
            "--hint",
            "bigger grin",
            "--good",
            "😎",
        ],
    )
    assert result.exit_code == 0
    assert "✅ generated result_😂.png" in result.output
    assert "✅ generated result_😢.png" in result.output


def test_redo_unknown_emoji_fails_via_cli(tmp_path) -> None:
    proj = _project_with_results(tmp_path)
    result = runner.invoke(app, ["redo", "🦄", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 1
    assert "unknown emoji" in _all_output(result)


def test_review_via_cli(tmp_path) -> None:
    proj = _project_with_results(tmp_path)
    result = runner.invoke(app, ["review", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 0
    assert "😂 identity 9 emotion 9 quality 9" in result.output
    assert f"✅ all {len(load_emotions())} stickers pass" in result.output


def test_model_alias_resolution(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_REVIEW_MODEL", raising=False)
    assert _make_backend(Backend.gemini, "pro").model_id == "gemini-3-pro-image"
    assert _make_backend(Backend.gemini, "lite").model_id == "gemini-3.1-flash-lite-image"
    assert _make_backend(Backend.gemini, "custom-model-id").model_id == "custom-model-id"
    assert _make_backend(Backend.gemini, None).model_id == "gemini-2.5-flash-image"


def test_ingest_missing_file_fails(tmp_path) -> None:
    result = runner.invoke(app, ["ingest", str(tmp_path / "nope.png"), "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "❌" in _all_output(result)


def test_refs_without_sources_fails(tmp_path) -> None:
    result = runner.invoke(
        app, ["refs", STYLE_GUIDE, "--project", str(tmp_path), "--backend", "fake"]
    )
    assert result.exit_code == 1
    assert "❌" in _all_output(result)


def test_changing_style_guide_fails(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    proj = str(tmp_path / "proj")
    runner.invoke(app, ["ingest", str(source), "--project", proj])
    runner.invoke(app, ["refs", STYLE_GUIDE, "--project", proj, "--backend", "fake"])

    result = runner.invoke(app, ["refs", "pixel art", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 1
    assert "already has style guide" in _all_output(result)


def test_refs_framing_option(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    proj = str(tmp_path / "proj")
    runner.invoke(app, ["ingest", str(source), "--project", proj])

    result = runner.invoke(
        app,
        ["refs", STYLE_GUIDE, "--project", proj, "--backend", "fake", "--framing", "bust"],
    )
    assert result.exit_code == 0
    assert "✅ generated ref_bust_1.png" in result.output
    assert "✅ generated ref_bust_2.png" in result.output
    assert "ref_half" not in result.output


def test_batch_before_refs_fails(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    proj = str(tmp_path / "proj")
    runner.invoke(app, ["ingest", str(source), "--project", proj])

    result = runner.invoke(app, ["batch", "--project", proj, "--backend", "fake"])
    assert result.exit_code == 1
    assert "no reference images" in _all_output(result)


def test_status_missing_project_dir_fails_and_does_not_create_it(tmp_path) -> None:
    missing = tmp_path / "typo" / "path"
    result = runner.invoke(app, ["status", "--project", str(missing)])
    assert result.exit_code == 1
    assert "not found" in _all_output(result)
    assert not missing.exists()


def test_gemini_backend_without_api_key_fails_cleanly(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = runner.invoke(
        app, ["refs", STYLE_GUIDE, "--project", str(tmp_path), "--backend", "gemini"]
    )
    assert result.exit_code == 1
    assert "GEMINI_API_KEY" in _all_output(result)  # a ❌ message, not a pydantic traceback


async def test_asyncio_setup_works() -> None:
    """Trivial async test proving pytest-asyncio auto mode is wired up."""
    assert True
