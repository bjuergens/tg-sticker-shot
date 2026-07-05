"""Pipeline stages: ingest → refs → batch → status.

Each stage is a plain function over (Project, ImageBackend) so the CLI stays
thin and the whole pipeline is testable without typer or network access.

Two-stage generation: `refs` distills the user-provided sources + style guide
into canonical reference images; `batch` generates every sticker from those
refs alone (sources are never referenced again).
"""

from dataclasses import dataclass

from tg_sticker_shot.api_base import ImageBackend
from tg_sticker_shot.core_emotions import Emotion, load_emotions
from tg_sticker_shot.core_persistence import FRAMINGS, Project, ProjectStateError

# `shot refs --framing vary` generates the first spec of every framing;
# a single framing generates all of its specs.
VARY = "vary"
FRAMING_CHOICES = (*FRAMINGS, VARY)

_BUST = (
    "Composition: bust shot only — head and shoulders, cropped at the chest, "
    "face large and fully visible, no weapons. "
)
_HALF = (
    "Composition: half-body shot — cropped at the waist, upper body and hands "
    "fully visible, face large and readable, no weapons. "
)
_FULL = "Composition: full-body shot — entire figure visible head to toe, bold clear silhouette. "

# Concrete camera/pose language, distinct angles per framing — the model
# copies input-image composition and ignores vague "pick a new pose" prompts.
REF_SPECS: dict[str, list[str]] = {
    "bust": [
        _BUST + "Angle: three-quarter view from the left, head upright, "
        "calm neutral expression, eyes on the viewer.",
        _BUST + "Angle: three-quarter view from the right, chin slightly lowered, "
        "faint confident smirk, eyes looking slightly off to the side.",
    ],
    "half": [
        _HALF + "Angle: three-quarter view from the left, arms crossed, calm neutral expression.",
        _HALF + "Angle: three-quarter view from the right, one hand raised "
        "in a relaxed open gesture, faint smirk.",
        _HALF + "Angle: frontal view, hands on hips, head upright, "
        "neutral expression, eyes on the viewer.",
    ],
    "full": [
        _FULL + "Angle: frontal view, relaxed standing pose, arms at the sides, "
        "neutral expression.",
        _FULL + "Angle: three-quarter view from the left, mid-stride walking pose.",
        _FULL + "Angle: three-quarter view from the right, dynamic action stance.",
        _FULL + "Angle: seen from behind, head turned back over the shoulder toward the viewer.",
    ],
}

REF_BOILERPLATE = (
    "Character reference image of the character shown in the input images, "
    "for use as a drawing reference for stickers. "
    "Keep the character's identity, outfit and colors consistent with the input images. "
    "Single centered character, plain solid white background, no text, no watermark."
)

# Shared prompt boilerplate for every sticker generation.
STICKER_BOILERPLATE = (
    "Telegram sticker of the character shown in the reference images. "
    "Keep the character's identity, outfit and colors consistent with the references. "
    "Single centered character, plain solid white background suitable for background "
    "removal, no text, no watermark."
)

# Batch prompts carry no style text — the refs carry the style.
STYLE_FROM_REFS = (
    "Match the art style of the reference images exactly (linework, proportions, coloring)."
)


@dataclass(frozen=True)
class StageReport:
    generated: list[str]
    skipped: list[str]


def ingest(project: Project, image_files: list[str]) -> list[str]:
    """Copy user-provided source images into the project. Returns the stored filenames."""
    return [project.add_source_from_file(source) for source in image_files]


def ref_specs_for(framing: str) -> list[tuple[str, int, str]]:
    """(framing, index, composition) triples for one refs run."""
    if framing == VARY:
        return [(name, 1, REF_SPECS[name][0]) for name in FRAMINGS]
    if framing not in REF_SPECS:
        raise ProjectStateError(f"unknown framing '{framing}' — expected one of {FRAMING_CHOICES}")
    return [(framing, index, spec) for index, spec in enumerate(REF_SPECS[framing], start=1)]


def generate_refs(
    project: Project, backend: ImageBackend, style_guide: str, framing: str
) -> StageReport:
    """Generate the canonical reference images from the sources in the given style.

    Records the style guide and framing in the project. Idempotent per ref: a
    run that died halfway resumes with the missing refs. A different style
    guide or framing on a project that already has refs is an error, not a
    silent restyle.
    """
    sources = project.load_sources()
    specs = ref_specs_for(framing)  # validate the framing before recording anything
    recorded_guide = project.load_style_guide_or_none()
    if recorded_guide is not None and recorded_guide != style_guide:
        raise ProjectStateError(
            f"project already has style guide '{recorded_guide}' — rerun with the same guide, "
            "or start a new project for a different style"
        )
    recorded_framing = project.load_framing_or_none()
    if recorded_framing is not None and recorded_framing != framing:
        raise ProjectStateError(
            f"project already has framing '{recorded_framing}' — rerun with the same framing, "
            "or start a new project for a different framing"
        )
    project.save_style_guide(style_guide)
    project.save_framing(framing)
    generated: list[str] = []
    skipped: list[str] = []
    for ref_framing, index, composition in specs:
        if project.has_ref(ref_framing, index):
            skipped.append(f"ref_{ref_framing}_{index}.png")
            continue
        prompt = f"{REF_BOILERPLATE} Art style: {style_guide}. {composition}"
        image = backend.generate(sources, prompt)
        generated.append(project.save_ref(ref_framing, index, image))
    project.record_run(
        "refs",
        {
            "backend": backend.name,
            "style_guide": style_guide,
            "framing": framing,
            "generated": len(generated),
        },
    )
    return StageReport(generated=generated, skipped=skipped)


def generate_batch(project: Project, backend: ImageBackend) -> StageReport:
    """Generate result_<emoji>.png per emotion; idempotent (skips existing results).

    Stickers reference the refs only — never sources or previous results
    (chaining output→output causes identity drift).
    """
    refs = project.load_refs()
    if not refs:
        raise ProjectStateError("no reference images in project — run `shot refs` first")
    generated: list[str] = []
    skipped: list[str] = []
    for emotion in load_emotions():
        if project.has_result(emotion.emoji):
            skipped.append(emotion.emoji)
            continue
        image = backend.generate(refs, _emotion_prompt(emotion))
        generated.append(project.save_result(emotion.emoji, image))
    project.record_run("batch", {"backend": backend.name, "generated": len(generated)})
    return StageReport(generated=generated, skipped=skipped)


def missing_emotions(project: Project) -> list[Emotion]:
    """Emotions that have no result yet (for status output)."""
    return [emotion for emotion in load_emotions() if not project.has_result(emotion.emoji)]


def _emotion_prompt(emotion: Emotion) -> str:
    return f"{STICKER_BOILERPLATE} {STYLE_FROM_REFS} Expression: {emotion.prompt_fragment}."
