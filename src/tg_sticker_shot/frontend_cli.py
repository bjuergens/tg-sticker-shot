"""Typer-based CLI. Entry point: `shot` (see [project.scripts] in pyproject.toml).

Subcommands mirror the pipeline stages so each is debuggable in isolation:
ingest → style → batch → status.
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


ProjectOpt = Annotated[str, typer.Option("--project", help="Project directory.")]
BackendOpt = Annotated[Backend, typer.Option("--backend", help="Image generation backend.")]


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
        list[str], typer.Argument(help="Reference image files to copy into the project.")
    ],
    project: ProjectOpt = ".",
) -> None:
    """Take reference images into the project."""
    try:
        proj = open_project(project, create=True)
        with proj.lock():
            stored = core_pipeline.ingest(proj, images)
    except ProjectStateError as error:
        raise _fail(error) from error
    for name in stored:
        typer.echo(f"✅ stored {name}")


@app.command()
def style(
    style_guide: Annotated[
        str,
        typer.Argument(help="Free-text style description, e.g. 'chibi, bold outlines'."),
    ],
    project: ProjectOpt = ".",
    backend: BackendOpt = Backend.gemini,
) -> None:
    """Generate sample stickers in the given style (records the style guide)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.generate_style_samples(proj, _make_backend(backend), style_guide)
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
    typer.echo(f"references: {state.reference_count}")
    typer.echo(f"samples: {state.sample_count}")
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
