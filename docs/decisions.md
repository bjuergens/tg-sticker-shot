# Decisions

Notable deviations from / refinements of the plan in `todo-1.md`.

## 2026-07-04 — Package dir under `src/` instead of literally flat `src/`

The plan says "one flat `src/` folder" with files like `src/frontend_cli.py`.
For `uvx --from git+<repo-url> shot` to work, the code must be an installable
package — top-level modules named `frontend_cli` etc. would collide in
site-packages and can't be built cleanly. So the flat folder lives one level
down: `src/tg_sticker_shot/frontend_cli.py`, `src/tg_sticker_shot/api_*.py`,
... The intent (one flat folder, prefixed filenames, no subpackages) is kept.

## 2026-07-04 — Manual Gemini smoke job deferred

Stage 0 lists an optional manual `workflow_dispatch` smoke job hitting the real
Gemini API. Deferred until `api_gemini.py` exists (Stage 1) — there is nothing
to smoke-test yet.
