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

## Getting a Gemini API key (Nano Banana)

Image generation uses Google's *Nano Banana* model
(`gemini-2.5-flash-image`) via the Gemini API.

1. Go to [Google AI Studio](https://aistudio.google.com/apikey) and sign
   in with any Google account.
2. Accept the terms on first visit, then click **Create API key**
   (in a new or existing Google Cloud project — either works).
3. Copy the key (starts with `AIza…`) and export it:

   ```sh
   export GEMINI_API_KEY="AIza..."
   ```

Optional: override the model with `GEMINI_MODEL`
(default: `gemini-2.5-flash-image`).

Verify the key with one cheap real generation:

```sh
uv run pytest -m gemini_smoke
```

Notes:

- **Billing:** new projects get a free-tier image quota of effectively
  zero — the first request 429s with `...FreeTier` quota errors even
  though text models work. Enable billing on the key's Google Cloud
  project ([Set up billing in AI Studio](https://aistudio.google.com/apikey))
  to use Nano Banana; an image costs roughly $0.04
  ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
- On the free tier Google may use your prompts and images to improve its
  models, so don't send anything sensitive.
- Treat the key like a password — never commit it.

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
