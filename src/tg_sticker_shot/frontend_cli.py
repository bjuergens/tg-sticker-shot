"""Typer-based CLI. Entry point: `shot` (see [project.scripts] in pyproject.toml).

Subcommands mirror the pipeline stages so each is debuggable in isolation:
ingest → refs → batch (→ redo / review) → status.
"""

from enum import StrEnum
from typing import Annotated

import typer

from tg_sticker_shot import __version__, core_pipeline, core_review
from tg_sticker_shot.api_base import BackendError, ImageBackend
from tg_sticker_shot.core_persistence import ProjectStateError, open_project
from tg_sticker_shot.core_review import ReviewError

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


# Quality-tier shorthands for --model; any other value is passed through
# verbatim, so new Gemini models need no code change here.
MODEL_ALIASES = {
    "flash": "gemini-2.5-flash-image",  # Nano Banana — cheap, the default
    "pro": "gemini-3-pro-image",  # Nano Banana Pro — best quality, ~4x price
    "lite": "gemini-3.1-flash-lite-image",  # Nano Banana 2 Lite — cheapest
}

ProjectOpt = Annotated[str, typer.Option("--project", help="Project directory.")]
BackendOpt = Annotated[Backend, typer.Option("--backend", help="Image generation backend.")]
FramingOpt = Annotated[
    Framing,
    typer.Option("--framing", help="Framing of the generated refs; vary = one of each."),
]
ModelOpt = Annotated[
    str | None,
    typer.Option(
        "--model",
        help="Image model: alias (flash, pro, lite) or full Gemini model ID. "
        "Default: GEMINI_MODEL env var or flash. Locked per project.",
    ),
]


def _make_backend(backend: Backend, model: str | None = None) -> ImageBackend:
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
    return GeminiBackend(settings, model=MODEL_ALIASES.get(model, model) if model else None)


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
    model: ModelOpt = None,
) -> None:
    """Generate the canonical reference images from the sources (records style + framing)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.generate_refs(
                proj, _make_backend(backend, model), style_guide, framing.value
            )
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")
    for name in report.skipped:
        typer.echo(f"⚠️ skipped {name} (exists)")


@app.command()
def batch(
    project: ProjectOpt = ".",
    backend: BackendOpt = Backend.gemini,
    model: ModelOpt = None,
) -> None:
    """Generate the remaining stickers (idempotent: existing results are skipped)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.generate_batch(proj, _make_backend(backend, model))
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")
    for emoji in report.skipped:
        typer.echo(f"⚠️ skipped {emoji} (result exists)")


@app.command()
def redo(
    emojis: Annotated[list[str], typer.Argument(help="Emoji(s) of the stickers to regenerate.")],
    project: ProjectOpt = ".",
    backend: BackendOpt = Backend.gemini,
    model: ModelOpt = None,
    hint: Annotated[
        str | None,
        typer.Option(
            "--hint",
            help="Extra prompt instructions, e.g. 'mouth wide open, more exaggerated'.",
        ),
    ] = None,
    good: Annotated[
        list[str] | None,
        typer.Option(
            "--good",
            help="Emoji of an existing good sticker to add as an extra reference (repeatable).",
        ),
    ] = None,
) -> None:
    """Force-regenerate the given stickers (overwrites existing results)."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_pipeline.redo_stickers(
                proj, _make_backend(backend, model), emojis, hint=hint, good=good
            )
    except (ProjectStateError, BackendError) as error:
        raise _fail(error) from error
    for name in report.generated:
        typer.echo(f"✅ generated {name}")


@app.command()
def review(
    project: ProjectOpt = ".",
    backend: BackendOpt = Backend.gemini,
    model: ModelOpt = None,
    threshold: Annotated[
        int,
        typer.Option("--threshold", help="Flag stickers with any score below this (1-10)."),
    ] = 6,
    max_redo: Annotated[
        int,
        typer.Option("--max-redo", help="Regenerate at most this many stickers per run."),
    ] = 5,
    no_redo: Annotated[
        bool,
        typer.Option("--no-redo", help="Report only, regenerate nothing."),
    ] = False,
) -> None:
    """AI-review all stickers and regenerate the worst offenders."""
    try:
        proj = open_project(project, create=False)
        with proj.lock():
            report = core_review.review_set(
                proj,
                _make_backend(backend, model),
                threshold=threshold,
                max_redo=max_redo,
                redo=not no_redo,
            )
    except (ProjectStateError, BackendError, ReviewError) as error:
        raise _fail(error) from error
    for rev in report.reviews:
        line = f"{rev.emoji} identity {rev.identity} emotion {rev.emotion} quality {rev.quality}"
        if rev.issues:
            line += f" — {rev.issues}"
        typer.echo(line)
    for rev in report.flagged:
        if rev.emoji in report.redone:
            suffix = f" (hint: {rev.redo_hint})" if rev.redo_hint else ""
            typer.echo(f"✅ redone {rev.emoji}{suffix}")
        else:
            suggestion = f"shot redo {rev.emoji}"
            if rev.redo_hint:
                suggestion += f' --hint "{rev.redo_hint}"'
            typer.echo(f"⚠️ flagged {rev.emoji} — {suggestion}")
    if not report.flagged:
        typer.echo(f"✅ all {len(report.reviews)} stickers pass (threshold {threshold})")


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
    typer.echo(f"model: {state.model or '(none)'}")
    typer.echo(f"results: {len(state.result_emojis)} {' '.join(state.result_emojis)}".rstrip())
    missing = core_pipeline.missing_emotions(proj)
    typer.echo(f"missing: {len(missing)} {' '.join(e.emoji for e in missing)}".rstrip())


@app.command()
def version() -> None:
    """Print the tg-sticker-shot version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
