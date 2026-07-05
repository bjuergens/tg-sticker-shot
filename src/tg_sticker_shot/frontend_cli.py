"""Typer-based CLI. Entry point: `shot` (see [project.scripts] in pyproject.toml).

Subcommands mirror the pipeline stages so each is debuggable in isolation:
ingest → refs → batch → status.
"""

from enum import StrEnum
from typing import Annotated

import typer

from tg_sticker_shot import __version__, core_pipeline
from tg_sticker_shot.api_base import BackendError, ImageBackend
from tg_sticker_shot.core_persistence import ProjectStateError, open_project

app = typer.Typer(
    help="tg-sticker-shot — Sticker Handling & Output Toolkit for Telegram.",
    no_args_is_help=True,
)


class Backend(StrEnum):
    fake = "fake"
    gemini = "gemini"


class Framing(StrEnum):
    bust = "bust"
    half = "half"
    full = "full"
    vary = "vary"


ProjectOpt = Annotated[str, typer.Option("--project", help="Project directory.")]
BackendOpt = Annotated[Backend, typer.Option("--backend", help="Image generation backend.")]
FramingOpt = Annotated[
    Framing,
    typer.Option(
        "--framing",
        help="Ref framing: bust (2 refs), half (3), full (4), or vary (one of each).",
    ),
]


def _make_backend(backend: Backend) -> ImageBackend:
    if backend is Backend.fake:
        from tg_sticker_shot.api_fake import FakeBackend

        return FakeBackend()
    from pydantic import ValidationError

    from tg_sticker_shot.api_gemini import GeminiBackend
    from tg_sticker_shot.core_config import Settings

    try:
        settings = Settings()  # pyright: ignore[reportCallIssue] — fields come from env
    except ValidationError as error:
        raise BackendError(
            "gemini backend needs the GEMINI_API_KEY environment variable"
        ) from error
    return GeminiBackend(settings)


def _fail(error: Exception) -> typer.Exit:
    typer.echo(f"❌ {error}", err=True)
    return typer.Exit(code=1)


@app.command()
def ingest(
    images: Annotated[
        list[str], typer.Argument(help="Source image files to copy into the project.")
    ],
    project: ProjectOpt = ".",
) -> None:
    """Take user-provided source images into the project."""
    try:
        proj = open_project(project, create=True)
        with proj.lock():
            stored = core_pipeline.ingest(proj, images)
    except ProjectStateError as error:
        raise _fail(error) from error
    for name in stored:
        typer.echo(f"✅ stored {name}")


@app.command()
def refs(
    style_guide: Annotated[
        str,
        typer.Argument(help="Free-text style description, e.g. 'chibi, bold outlines'."),
    ],
    project: ProjectOpt = ".",
    backend: BackendOpt = Backend.gemini,
    framing: FramingOpt = Framing.vary,
) -> None:
    """Generate the canonical reference images from the sources (records style + framing)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.generate_refs(
                proj, _make_backend(backend), style_guide, framing.value
            )
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")
    for name in report.skipped:
        typer.echo(f"⚠️ skipped {name} (exists)")


@app.command()
def batch(project: ProjectOpt = ".", backend: BackendOpt = Backend.gemini) -> None:
    """Generate the remaining stickers (idempotent: existing results are skipped)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.generate_batch(proj, _make_backend(backend))
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")
    for emoji in report.skipped:
        typer.echo(f"⚠️ skipped {emoji} (result exists)")


@app.command()
def status(project: ProjectOpt = ".") -> None:
    """Show project state (read-only: never creates the directory)."""
    try:
        proj = open_project(project, create=False)
        state = proj.status()
    except ProjectStateError as error:
        raise _fail(error) from error
    typer.echo(f"sources: {state.source_count}")
    typer.echo(f"refs: {state.ref_count}")
    typer.echo(f"style guide: {state.style_guide or '(none)'}")
    typer.echo(f"results: {len(state.result_emojis)} {' '.join(state.result_emojis)}".rstrip())
    missing = core_pipeline.missing_emotions(proj)
    typer.echo(f"missing: {len(missing)} {' '.join(e.emoji for e in missing)}".rstrip())


@app.command()
def version() -> None:
    """Print the tg-sticker-shot version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
