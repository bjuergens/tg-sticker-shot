"""Typer-based CLI. Entry point: `shot` (see [project.scripts] in pyproject.toml)."""

import typer

from tg_sticker_shot import __version__

app = typer.Typer(
    help="tg-sticker-shot — Sticker Handling & Output Toolkit for Telegram.",
    no_args_is_help=True,
)


@app.command()
def hello(name: str = "world") -> None:
    """Say hello (skeleton smoke command)."""
    typer.echo(f"hello {name}")


@app.command()
def version() -> None:
    """Print the tg-sticker-shot version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
