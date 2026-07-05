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

## Gemini API key

Image generation uses `gemini-2.5-flash-image` (Nano Banana) via the
Gemini API.

1. Create an API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Enable billing on the key's project — the free tier does not cover
   image generation ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
3. `export GEMINI_API_KEY="..."`

Optional: `GEMINI_MODEL` overrides the model. Verify the key with one
paid generation: `uv run pytest -m gemini_smoke`.

## Development

```sh
uv sync --all-extras   # install everything into .venv
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run basedpyright    # typecheck
uv run shot --help     # run the CLI
```

## License

[AGPL-3.0-or-later](LICENSE)
