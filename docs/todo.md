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
- *Simplified after the Stage 1 review:* `styles.yaml` and the `select` stage
  are gone. The user supplies a free-text style guide once (`shot style
  "chibi, bold outlines"`), which drives the sample generation; from then on
  the reference + sample images carry the style and batch uses a hardcoded
  prompt with no style text. `emotions.yaml` stays (`core_emotions.py`).
  Predefined multi-style sampling can return later as UI sugar for the bot.
- *Two-stage ref architecture (2026-07):* `shot style` became `shot refs`:
  user uploads are *sources* (`source_<n>.png`), the refs stage distills
  them + the style guide into generated canonical *refs*
  (`ref_<framing>_<n>.png`), and batch generates stickers from the refs
  alone. Reason: the model copies the composition of its input images, so
  same-pose anchors froze every sticker into one pose; framing-varied refs
  fix it. `--framing bust|half|full|vary` is recorded in project.json;
  changing it mid-project is an error like the style guide.

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
- **Style is a user-supplied string, emotions are data** *(simplified, see
  deviations)*: the style guide is free text given to `shot style` and stored
  in the project dir; `emotions.yaml` (emotion → emoji + prompt fragment)
  stays a bundled data file.
- **Consistency strategy**: generate/keep an anchor + style samples; batch
  generation always references the original refs + style samples, never
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
      results, style guide, run metadata
- [x] Backend Protocol + `api_fake.py` (fixture PNGs) + `api_gemini.py`
- [x] `emotions.yaml` (~10–20 emotions with emoji + prompt fragment);
      styles.yaml dropped in the simplification (see deviations)
- [x] CLI subcommands mirroring pipeline stages (debuggable in isolation):
  - [x] `ingest` — take reference images into project
  - [x] `style` — record the free-text style guide + generate sample stickers
        (replaces the former `styles` + `select` pair)
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

- [ ] **cli qol**: default work folder should be "work", with cli option for overwrite. all env vars, except secrets should be cli args only .  logging and progress: long running commands, should lock what they are doing, maybe info printing progress every couple seconds? or just after each phase or something, so user knows it isnt frozen.  
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
- [ ] **`shot redo <emoji>`** — delete + regenerate one result (workaround
      today: delete the file, rerun batch). Maybe also for refs.
- [ ] **Optional AI quality review** — vision model rates the set (identity
      consistency, emotion legibility at sticker size, artifacts) and
      suggests re-rolls for `shot redo`.
- [ ] Consider fal.ai (or second backend) as alternative — should be one new
      `api_*.py` file if the Protocol held up
- [ ] Consider pivot: emoji filenames → semantic names + manifest.json
- [ ] Publish to PyPI (currently: install via git URL)
- [ ] Maybe: Telegram payment API experiment (convenience-payment only; AGPL
      keeps self-hosting free)
