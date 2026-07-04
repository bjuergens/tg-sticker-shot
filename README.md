# tg-sticker-shot

**tg-sticker-shot** — *Sticker Handling & Output Toolkit* for Telegram. CLI: `shot`.

AI-assisted Telegram sticker set generator: provide reference images of a
character, pick a style from generated samples, and get a full sticker set as
PNGs named by emoji — ready to be turned into a Telegram sticker set.

## Usage

Run straight from the repo with [uv](https://docs.astral.sh/uv/):

```sh
uvx --from git+https://github.com/bjuergens/tg-sticker-shot shot --help
```

## Development

```sh
uv sync --all-extras   # install everything into .venv
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run basedpyright    # typecheck
uv run shot hello      # run the CLI
```

## License

[AGPL-3.0-or-later](LICENSE)
