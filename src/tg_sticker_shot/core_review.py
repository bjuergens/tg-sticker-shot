"""AI review of the generated sticker set (`shot review`).

A text-out vision call rates every sticker against the refs (identity
consistency, emotion legibility, technical quality); the worst offenders are
regenerated through the same mechanism as `shot redo`, with the critique fed
back as the redo hint.
"""

import json
from dataclasses import dataclass

from tg_sticker_shot import core_pipeline
from tg_sticker_shot.api_base import ImageBackend
from tg_sticker_shot.core_emotions import Emotion, load_emotions
from tg_sticker_shot.core_persistence import Project, ProjectStateError

_SCORE_KEYS = ("identity", "emotion", "quality")

_CRITIQUE_PROMPT = (
    "You are reviewing one Telegram sticker candidate. All images before the last "
    "one are the canonical character reference images; the LAST image is the "
    "sticker candidate. The sticker is supposed to express the emotion "
    "'{name}' ({emoji}): {fragment}. "
    "Rate the candidate from 1 (unusable) to 10 (perfect) on: "
    "identity — same character, outfit and colors as the reference images; "
    "emotion — clearly reads as '{name}' even at small sticker size; "
    "quality — plain solid white background, no artifacts, no text or watermark, "
    "well framed single character. "
    "Reply with ONLY this JSON object and nothing else, no markdown: "
    '{{"identity": <n>, "emotion": <n>, "quality": <n>, '
    '"issues": "<short description of the problems, empty if none>", '
    '"redo_hint": "<one short instruction to improve a regeneration, empty if none>"}}'
)


class ReviewError(Exception):
    """The review model returned something that is not a valid review."""


@dataclass(frozen=True)
class StickerReview:
    emoji: str
    identity: int
    emotion: int
    quality: int
    issues: str
    redo_hint: str

    @property
    def worst_score(self) -> int:
        return min(self.identity, self.emotion, self.quality)


@dataclass(frozen=True)
class ReviewReport:
    reviews: list[StickerReview]  # one per existing result, emotions.yaml order
    flagged: list[StickerReview]  # offenders below threshold, worst first, capped
    redone: list[str]  # emojis actually regenerated (empty with redo=False)


def critique_prompt(emotion: Emotion) -> str:
    return _CRITIQUE_PROMPT.format(
        name=emotion.name, emoji=emotion.emoji, fragment=emotion.prompt_fragment
    )


def parse_review(emoji: str, text: str) -> StickerReview:
    """Parse the critique model's JSON verdict; fails loudly on garbage."""
    raw = text.strip()
    if raw.startswith("```"):  # tolerate a markdown fence despite the prompt
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0]
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReviewError(f"review of {emoji} is not valid JSON: {text!r}") from error
    if not isinstance(loaded, dict):
        raise ReviewError(f"review of {emoji} is not a JSON object: {text!r}")
    scores: dict[str, int] = {}
    for key in _SCORE_KEYS:
        value = loaded.get(key)
        if type(value) is not int or not 1 <= value <= 10:
            raise ReviewError(f"review of {emoji} needs integer 1-10 '{key}': {text!r}")
        scores[key] = value
    issues = loaded.get("issues", "")
    redo_hint = loaded.get("redo_hint", "")
    if not isinstance(issues, str) or not isinstance(redo_hint, str):
        raise ReviewError(f"review of {emoji} has non-string issues/redo_hint: {text!r}")
    return StickerReview(emoji=emoji, issues=issues, redo_hint=redo_hint, **scores)


def review_set(
    project: Project,
    backend: ImageBackend,
    threshold: int,
    max_redo: int,
    redo: bool,
) -> ReviewReport:
    """Review every existing result; regenerate the worst offenders (if redo).

    An offender is any sticker whose worst score is below the threshold; at
    most max_redo of them (worst first) are flagged/regenerated per run.
    Single pass: redone stickers are not re-reviewed — rerun `shot review`.
    """
    refs = project.load_refs()
    if not refs:
        raise ProjectStateError("no reference images in project — run `shot refs` first")
    reviews: list[StickerReview] = []
    for emotion in load_emotions():
        if not project.has_result(emotion.emoji):
            continue
        images = [*refs, project.load_result(emotion.emoji)]
        verdict = backend.critique(images, critique_prompt(emotion))
        reviews.append(parse_review(emotion.emoji, verdict))
    if not reviews:
        raise ProjectStateError("no results to review — run `shot batch` first")
    offenders = sorted(
        (review for review in reviews if review.worst_score < threshold),
        key=lambda review: review.worst_score,
    )
    flagged = offenders[:max_redo]
    redone: list[str] = []
    if redo:
        for review in flagged:
            core_pipeline.redo_stickers(
                project, backend, [review.emoji], hint=review.redo_hint or None
            )
            redone.append(review.emoji)
    project.record_run(
        "review",
        {
            "backend": backend.name,
            "threshold": threshold,
            "reviewed": len(reviews),
            "flagged": [review.emoji for review in flagged],
            "redone": redone,
        },
    )
    return ReviewReport(reviews=reviews, flagged=flagged, redone=redone)
