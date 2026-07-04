# tg-sticker-shot

**Sticker Handling & Output Toolkit for Telegram.** AI-assisted Telegram
sticker set generator: reference images of a character in, full sticker set
out (PNGs named by emoji). GPU work happens via image gen API (Gemini);
locally only orchestration.

Roadmap and architecture decisions: `docs/todo.md` (deviations recorded
inline there). Review checklist: `REVIEW.md`.

## Tooling

Python ≥ 3.11, `uv` for everything. Common commands:

- `uv sync --all-extras` — create/refresh the dev environment
- `uv run pytest` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run basedpyright` — typecheck
- `uv run shot --help` — run the CLI from the checkout
- `uvx --from git+https://github.com/bjuergens/tg-sticker-shot shot` — run the published tool

## Conventions

- Flat package, prefixed filenames: `frontend_*`, `api_*`, `core_*` in
  `src/tg_sticker_shot/`. No subpackages.
- All filesystem access goes through `core_persistence.py`; only that module
  imports `pathlib`.
- Config/secrets via env vars (pydantic-settings), never in the repo.

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
