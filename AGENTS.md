# tg-sticker-shot

**Sticker Handling & Output Toolkit for Telegram.** AI-assisted Telegram
sticker set generator: user provides reference images of a character, picks a
style from generated samples, system generates the full sticker set (PNGs named
by emoji). GPU work happens via an image gen API (Gemini / Nano Banana);
nothing runs locally except orchestration and (later) post-processing.

The roadmap lives in `todo-1.md`. Notable deviations and decisions go in
`docs/decisions.md`. Code review checklist: `REVIEW.md`.

## Tooling

Python ≥ 3.11, `uv` for everything (deps, venv, running). Common commands:

- `uv sync --all-extras` — create/refresh the dev environment
- `uv run pytest` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run basedpyright` — typecheck (non-blocking during exploration)
- `uv run shot --help` — run the CLI from the checkout (entry point: `shot`)
- `uvx --from git+https://github.com/bjuergens/tg-sticker-shot shot` — run
  straight from the repo URL

## Architecture decisions

- **Flat package, prefixed filenames** instead of subpackages:
  `src/tg_sticker_shot/` contains `frontend_cli.py`, `api_gemini.py`,
  `api_fake.py`, `core_persistence.py`, `core_pipeline.py`, ... Refactor into
  packages later only if it hurts.
- **Persistence is concentrated in `core_persistence.py`.** Its interface
  speaks domain terms (`save_reference(project, ...)`,
  `load_results(project)`) and never leaks `Path` objects to callers. Only
  this module imports `pathlib`. Storage is a flat *project directory* with
  prefixed files: `reference_1.png`, `sample_<style>_<n>.png`,
  `result_<emoji>.png`. CLI defaults to cwd or `--project`; the future bot
  maps user_id → project dir.
- **Emoji directly in result filenames** for now (`result_😂.png`). Pivot to
  semantic names + manifest.json if shell/git/CI ergonomics bite.
- **Image backend behind a minimal Protocol**: roughly
  `generate(refs: list[bytes], prompt: str) -> bytes`. Implementations:
  `api_gemini.py` (real, httpx preferred over vendor SDK) and `api_fake.py`
  (returns fixture PNGs — enables full pipeline tests with no secrets or
  mocking).
- **Styles are data, not code**: `styles.yaml` (prompt templates) and
  `emotions.yaml` (emotion → emoji + prompt fragment). Chosen style and inputs
  are stored in the project dir so batch generation is reproducible.
- **Consistency strategy**: batch generation always references the original
  refs + chosen style samples, never chains output→output (prevents drift).
  Prefer letting refs carry character identity over name-dropping IP in
  prompts (fewer refusals).
- **Config/secrets** via env vars (pydantic-settings). Never in the repo.

## Conventions

- File-name prefixes group related modules: `frontend_*`, `api_*`, `core_*`.
- Tests live in `tests/`; pytest-asyncio runs in auto mode (plain `async def`
  test functions work).
- CI (`.github/workflows/ci.yml`): ruff + pytest are blocking; basedpyright is
  a separate non-blocking job during exploration.
- License is AGPL-3.0-or-later.

# General 

This section is the same for multiple projects. 

## Principles

- 📏 Big functions are fine. Extract when there's reuse or the established abstractions call for it.
- ⏳ No premature performance optimization.
- 📋 Plans define what and done when, not how. Challenge a plan when it fights reality; don't silently deviate.
- 🔊 Fail loudly. Throw errors, don't swallow them. Log failures clearly. If something is wrong, the developer should know immediately, not discover it later through subtle misbehavior.

## Emoji

Use consistently in code, commits, and logging.

### Commits

Human-made commits usually contain no emoji, while agent-made commits do.

`<emoji> <type>: <description>`

- ✨ feat: new feature
- 🐛 fix: bug fix
- 🔧 config: configuration changes
- 📦 deps: dependency changes
- 🧪 test: tests
- 📝 docs: documentation
- 🧹 refactor: cleanup (no behavior change)


### Logging

- ✅ success operations
- ❌ errors and failures
- ⚠️ warnings
