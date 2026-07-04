"""Typer-based CLI. Entry point: `shot` (see [project.scripts] in pyproject.toml).

Subcommands mirror the pipeline stages so each is debuggable in isolation:
ingest → styles → select → batch → status.
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
    from tg_sticker_shot.api_gemini import GeminiBackend
    from tg_sticker_shot.core_config import Settings

    return GeminiBackend(Settings())  # pyright: ignore[reportCallIssue] — fields come from env


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
    proj = open_project(project)
    try:
        with proj.lock():
            stored = core_pipeline.ingest(proj, images)
    except ProjectStateError as error:
        raise _fail(error) from error
    for name in stored:
        typer.echo(f"✅ stored {name}")


@app.command()
def styles(project: ProjectOpt = ".", backend: BackendOpt = Backend.gemini) -> None:
    """Generate sample stickers for every style."""
    proj = open_project(project)
    try:
        with proj.lock():
            report = core_pipeline.generate_style_samples(proj, _make_backend(backend))
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")
    for style_name in report.skipped:
        typer.echo(f"⚠️ skipped {style_name} (samples exist)")


@app.command()
def select(
    style: Annotated[str, typer.Argument(help="Style name from styles.yaml.")],
    project: ProjectOpt = ".",
) -> None:
    """Record the chosen style."""
    proj = open_project(project)
    try:
        with proj.lock():
            core_pipeline.select_style(proj, style)
    except ProjectStateError as error:
        raise _fail(error) from error
    typer.echo(f"✅ selected style '{style}'")


@app.command()
def batch(project: ProjectOpt = ".", backend: BackendOpt = Backend.gemini) -> None:
    """Generate the remaining stickers (idempotent: existing results are skipped)."""
    proj = open_project(project)
    try:
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
    """Show project state."""
    proj = open_project(project)
    state = proj.status()
    typer.echo(f"references: {state.reference_count}")
    for style_name, count in state.samples_per_style.items():
        typer.echo(f"samples[{style_name}]: {count}")
    typer.echo(f"chosen style: {state.chosen_style or '(none)'}")
    typer.echo(f"results: {len(state.result_emojis)} {' '.join(state.result_emojis)}".rstrip())
    missing = core_pipeline.missing_emotions(proj)
    typer.echo(f"missing: {len(missing)} {' '.join(e.emoji for e in missing)}".rstrip())


@app.command()
def version() -> None:
    """Print the tg-sticker-shot version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
