from typer.testing import CliRunner

from tg_sticker_shot import __version__
from tg_sticker_shot.frontend_cli import app

runner = CliRunner()


def test_hello() -> None:
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "hello world" in result.output


def test_hello_with_name() -> None:
    result = runner.invoke(app, ["hello", "--name", "guts"])
    assert result.exit_code == 0
    assert "hello guts" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


async def test_asyncio_setup_works() -> None:
    """Trivial async test proving pytest-asyncio auto mode is wired up."""
    assert True
