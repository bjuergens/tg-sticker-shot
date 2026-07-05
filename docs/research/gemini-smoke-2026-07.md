# Real-API smoke test — 2026-07-05

Full pipeline run against the real Gemini API (`gemini-2.5-flash-image`,
review critic `gemini-2.5-flash`). Input: one 390×512 JPEG character sheet
(red-haired masked figure in a pinstripe coat holding a mushroom), style guide
"chibi themed mushroom wizard", framing `vary`. ~28 API calls total
(3 refs + 12 stickers + 12 critiques + 1 earlier key check), zero failures,
zero refusals, zero redos.

## Findings

- **Identity consistency: very good.** All 3 refs and all 12 stickers kept the
  spiky red hair, face mask, high-collar pinstripe coat, and orange shirt from
  a single source image. The two-stage ref architecture (sources → refs →
  stickers) did its job: no drift, and the framing-varied refs prevented the
  one-pose freeze the architecture was built to fix.
- **Emotion legibility: very good.** Every emotion read clearly at a glance,
  including prompt-fragment details (tears of joy, snot bubble + "zzz",
  hands-on-cheeks scream). Notable: the character's face mask did not block
  expressions — the model drew mouths *on/through* the mask.
- **White background prompting works.** Backgrounds are near-uniform white
  (slight gradients/vignetting in places) — good enough for the planned
  post-processing removal, not clean enough to skip it.
- **IP/recognizable-character handling:** not conclusively tested (the source
  is an obscure character), but a reference-image-only approach with no name
  in the prompt produced zero refusals.
- **Style guide is treated as *art style*, not costume/theme.** "chibi themed
  mushroom wizard" yielded chibi proportions, but the mushroom prop from the
  source was dropped everywhere (the ref prompts forbid weapons/props and only
  inject the guide as "Art style: …"). If a theme prop should survive, it has
  to be in the source-visible outfit or the ref prompts — worth a note in
  user-facing docs, not a bug.
- **JPEG sources work despite the PNG label.** `ingest` stores bytes verbatim
  and the backend declares `mime_type: image/png` for everything; a real JPEG
  source was accepted anyway (converted to PNG for this test out of caution
  first — a later quick check with the raw JPEG is cheap if it ever matters).
- **AI review (`shot review`) end-to-end on real API:** all 12 critiques came
  back as parseable strict JSON on the first try (no markdown fences), scores
  10/10/10 except two 9s on emotion (🤔 eyebrow not raised, 🤦). Threshold 6
  flagged nothing, so auto-redo had nothing to do. The critic skews generous —
  if review should be a stricter gate, raise `--threshold` (8 would have still
  passed everything here) or harden the rubric wording in `core_review.py`.
- **Latency:** roughly 10–20 s per generation, ~1–3 s per critique; a full
  12-sticker set lands in a few minutes.

Conclusion: Stage-1 POC works against the real API end-to-end, including the
redo/review round. Main open quality item remains post-processing
(transparency, resize, size cap).
