# TODO

**tg-sticker-shot** — *Sticker Handling & Output Toolkit* for Telegram.

AI-assisted Telegram sticker set generator. User provides reference images of a
character (e.g. Guts from Berserk), picks a style from generated samples
(e.g. chibi), system generates the full sticker set: PNGs named by emoji, ready
to be turned into a Telegram sticker set.

License: AGPL-3. GPU work happens via image gen API (Gemini / Nano Banana),
nothing runs locally except orchestration and (later) post-processing.

This plan was made during an explorative brainstorming phase. Deviate where it
makes sense — the architecture decisions below capture *intent* (flexibility,
testability, simplicity), not law. Record notable deviations/decisions inline
here.

Deviations so far:

- The flat folder lives at `src/tg_sticker_shot/` instead of literally `src/`
  — code must be an installable package for `uvx --from git+<repo-url> shot`
  to work. Intent (one flat folder, prefixed filenames, no subpackages) kept.
- The optional manual Gemini smoke CI job is deferred until `api_gemini.py`
  exists (Stage 1) — nothing to smoke-test yet. *Resolved in Stage 1:* smoke
  test lives in `tests/test_gemini.py` behind the `gemini_smoke` pytest marker
  (deselected by default), CI job `gemini-smoke` runs it on `workflow_dispatch`
  with the `GEMINI_API_KEY` repo secret.
- Stage 1 prompts ask for a plain white background (easy to remove in the
  post-processing stage) instead of prompting for transparency directly —
  whether model-native transparency works is part of the open manual smoke
  research below.

## Naming (decided)

- Repo: `tg-sticker-shot`
- CLI command: `shot` (via `[project.scripts]`; package name and command may
  differ, that's intended)
- Telegram bot (later): "Chibi Upload Machine" — pick an available BotFather
  handle in that spirit when the bot stage starts
- README tagline: "tg-sticker-shot — Sticker Handling & Output Toolkit for
  Telegram. CLI: `shot`."

## Architecture decisions (agreed so far)

- **One repo, one flat `src/` folder, prefixed filenames** instead of packages:
  `frontend_cli.py`, `api_gemini.py`, `api_fake.py`, `core_persistence.py`,
  `core_pipeline.py`, ... Refactor into packages later only if it hurts.
- **Persistence is concentrated in `core_persistence.py`.** Interface speaks
  domain terms (`save_reference(project, ...)`, `load_results(project)`), never
  leaks `Path` objects to callers. Only this module imports `pathlib`. Storage
  is a flat *project directory* with prefixed files: `reference_1.png`,
  `sample_<style>_<n>.png`, `result_<emoji>.png`. CLI defaults to cwd or
  `--project`; the future bot maps user_id → project dir. Same shape everywhere.
- **Emoji directly in result filenames** for now (`result_😂.png`). Known
  risks: shell/git/CI ergonomics, multi-emoji-per-sticker unsupported. Pivot to
  semantic names + manifest.json if it bites.
- **Image backend behind a minimal Protocol**: roughly
  `generate(refs: list[bytes], prompt: str) -> bytes`. Implementations:
  `api_gemini.py` (real, via httpx preferred over vendor SDK if practical) and
  `api_fake.py` (returns fixture PNGs — enables full pipeline tests with no
  secrets/mocking).
- **Styles are data, not code**: `styles.yaml` (prompt templates) and
  `emotions.yaml` (emotion → emoji + prompt fragment). Chosen style and inputs
  are stored in the project dir so batch generation is reproducible.
- **Consistency strategy**: generate/keep an anchor + style samples; batch
  generation always references the original refs + chosen style samples, never
  chains output→output (prevents drift). Prefer letting refs carry character
  identity over name-dropping IP in prompts (fewer refusals).
- **Config/secrets** via env vars (pydantic-settings). Never in repo.

## Stage 0 — Skeleton

- [x] `pyproject.toml` with uv, `src/` layout, `[project.scripts]` entry point
      `shot = ...` so `uvx --from git+<repo-url> shot` works
- [x] Optional dependency extras planned: `[bot]`, `[matting]` (empty for now)
- [x] typer-based `frontend_cli.py` with a hello/version command
- [x] pytest + pytest-asyncio setup, one trivial passing test
- [x] ruff (lint + format)
- [x] typechecker (basedpyright) — runs in CI as a **blocking** job
      (originally planned non-blocking; gated from the start instead)
- [x] GitHub Actions: uv-cached workflow → sync, ruff, pytest. No secrets
      needed (everything fake/mocked). Optional: manual `workflow_dispatch`
      smoke job hitting real Gemini with one cheap generation
- [x] `CLAUDE.md`: project intent, architecture decisions above, commands
      (test/lint/run), conventions (prefix scheme, persistence rules)
- [x] `.gitignore`, `LICENSE` (AGPL-3), minimal `README.md`

## Stage 1 — POC (CLI)

- [x] `core_persistence.py`: project-dir handling, save/load refs, samples,
      results, chosen style, run metadata
- [x] Backend Protocol + `api_fake.py` (fixture PNGs) + `api_gemini.py`
- [x] `styles.yaml` (2–3 starter styles: chibi, pixel art, ...) and
      `emotions.yaml` (~10–20 emotions with emoji + prompt fragment)
- [x] CLI subcommands mirroring pipeline stages (debuggable in isolation):
  - [x] `ingest` — take reference images into project
  - [x] `styles` — generate 2–3 sample stickers per style
  - [x] `select` — record chosen style
  - [x] `batch` — generate remaining stickers (refs + style samples as
        references, per-emotion prompts, idempotent: skip existing results)
  - [x] `status` — show project state
- [x] Pipeline integration test running ingest→batch end-to-end on FakeBackend
- [ ] Manual smoke test against real Gemini API, including: does it handle
      recognizable IP characters (Guts) via reference images? Does
      transparent-background prompting work? Record findings in docs/research/
      (automated entry point exists: `uv run pytest -m gemini_smoke`)
- [x] Concurrency: one lock per project dir (matters once the bot exists;
      cheap to add now)

## Follow-up (after POC)

- [ ] **Post-processing** (`post` stage): transparency (prefer model-native;
      rembg via `[matting]` extra only as fallback — pulls heavy onnxruntime),
      white outline via alpha dilation (opencv-python-headless), resize to
      512×512, enforce ≤512 KB, PNG/WEBP
- [ ] **Telegram bot** (`[bot]` extra, aiogram 3): thin FSM over the same core
      (upload refs → style keyboard → progress → done). Allowlist of users, no
      payment initially. Long polling on VPS, Docker Compose.
  - [ ] Auto-create/publish sticker set via Bot API
        (`createNewStickerSet`/`addStickerToSet`)
  - [ ] Handler tests via aiogram MockedSession / aiogram_tests (offline,
        CI-friendly). Skip real-Telegram e2e or make it manual-only.
- [ ] **Pack/export** for CLI users: manifest + instructions (or bot-assisted
      upload)
- [ ] Consider fal.ai (or second backend) as alternative — should be one new
      `api_*.py` file if the Protocol held up
- [ ] Consider pivot: emoji filenames → semantic names + manifest.json
- [ ] Publish to PyPI (currently: install via git URL)
- [ ] Maybe: Telegram payment API experiment (convenience-payment only; AGPL
      keeps self-hosting free)
