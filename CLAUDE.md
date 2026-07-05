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

### Running the real pipeline (agent test drive)

When the user supplies reference image(s) and a Gemini API key in chat and
asks to test the pipeline:

- **Key**: pass it inline per command (`GEMINI_API_KEY=... uv run shot ...`).
  Never write it to a file, the repo, or shell config. Remind the user to
  rotate it afterward — a key pasted in chat counts as exposed.
- **Project dir**: use the session scratchpad (e.g. `$SCRATCHPAD/<name>/proj`),
  never a directory inside the repo — generated images must not end up in git.
- **Source images**: uploads land as-is; `ingest` stores bytes verbatim and
  the backend labels everything `image/png`, so convert non-PNG uploads first:
  `uv run --with pillow python -c "from PIL import Image; Image.open(SRC).convert('RGB').save(DST_PNG)"`
- **Run** (default params, default model; ~15 paid generations ≈ $0.60):
  1. `uv run shot ingest <sources...> --project $PROJ`
  2. `GEMINI_API_KEY=... uv run shot refs "<style guide>" --project $PROJ --backend gemini`
  3. `GEMINI_API_KEY=... uv run shot batch --project $PROJ --backend gemini`
  4. `GEMINI_API_KEY=... uv run shot review --project $PROJ --backend gemini`
  5. `uv run shot status --project $PROJ`
- **Show the output**: view images yourself with the `Read` tool (spot-check
  refs before paying for batch); deliver them to the user with `SendUserFile`
  (refs + all `result_*.png`).
- Errors abort a stage loudly by design; report the exact error and stop —
  don't burn more paid calls retrying. `refs`/`batch` are idempotent, so a
  fixed rerun resumes where it died.
- Record notable findings in `docs/research/` (see
  `gemini-smoke-2026-07.md` for the shape).

## Conventions

- Flat package, prefixed filenames: `frontend_*`, `api_*`, `core_*` in
  `src/tg_sticker_shot/`. No subpackages.
- All filesystem access goes through `core_persistence.py`; only that module
  imports `pathlib`.
- Config/secrets via env vars (pydantic-settings), never in the repo.
- Don't worry about migrations for the CLI (project dir layout, file naming,
  project.json schema) — every run starts with empty data.
- Ignore `REVIEW.md` during implementation; it's for reviewing only. Re-read
  it every time you start a new round of reviewing.

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
