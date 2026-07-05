"""Pipeline stages: ingest → style → batch → status.

Each stage is a plain function over (Project, ImageBackend) so the CLI stays
thin and the whole pipeline is testable without typer or network access.

The style is a free-text guide the user supplies once: it steers the sample
generation, the samples are stored in the project, and every later generation
takes its style from the reference + sample images alone (hardcoded prompt).
"""

from dataclasses import dataclass

from tg_sticker_shot.api_base import ImageBackend
from tg_sticker_shot.core_emotions import Emotion, load_emotions
from tg_sticker_shot.core_persistence import Project, ProjectStateError

SAMPLE_COUNT = 2

# Shared prompt boilerplate for every generation (samples and batch).
STICKER_BOILERPLATE = (
    "Telegram sticker of the character shown in the reference images. "
    "Keep the character's identity, outfit and colors consistent with the references. "
    "Single centered character, plain solid white background suitable for background "
    "removal, no text, no watermark."
)

# Batch prompts carry no style text — the style comes from the sample images.
STYLE_FROM_SAMPLES = (
    "Match the art style of the provided sample sticker images exactly "
    "(linework, proportions, coloring)."
)


@dataclass(frozen=True)
class StageReport:
    generated: list[str]
    skipped: list[str]


def ingest(project: Project, image_files: list[str]) -> list[str]:
    """Copy reference images into the project. Returns the stored filenames."""
    return [project.add_reference_from_file(source) for source in image_files]


def generate_style_samples(
    project: Project, backend: ImageBackend, style_guide: str
) -> StageReport:
    """Generate SAMPLE_COUNT sample stickers in the user-supplied style.

    Records the style guide in the project. Idempotent per sample: a run that
    died halfway resumes with the missing indices. A different style guide on
    an already-styled project is an error, not a silent restyle.
    """
    refs = project.load_references()
    recorded = project.load_style_guide_or_none()
    if recorded is not None and recorded != style_guide:
        raise ProjectStateError(
            f"project already has style guide '{recorded}' — rerun with the same guide, "
            "or start a new project for a different style"
        )
    project.save_style_guide(style_guide)
    generated: list[str] = []
    skipped: list[str] = []
    for index in range(1, SAMPLE_COUNT + 1):
        if project.has_sample(index):
            skipped.append(f"sample_{index}.png")
            continue
        image = backend.generate(refs, _sample_prompt(style_guide))
        generated.append(project.save_sample(index, image))
    project.record_run(
        "style", {"backend": backend.name, "style_guide": style_guide, "generated": len(generated)}
    )
    return StageReport(generated=generated, skipped=skipped)


def generate_batch(project: Project, backend: ImageBackend) -> StageReport:
    """Generate result_<emoji>.png per emotion; idempotent (skips existing results).

    References are always the original refs + the style samples, never previous
    results — chaining output→output causes identity drift.
    """
    samples = project.load_samples()
    if not samples:
        raise ProjectStateError(
            "no style samples in project — run `shot style` first "
            "(batch must reference style samples to keep the set consistent)"
        )
    refs = project.load_references() + samples
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


def _sample_prompt(style_guide: str) -> str:
    return f"{STICKER_BOILERPLATE} Art style: {style_guide}. Expression: friendly neutral smile."


def _emotion_prompt(emotion: Emotion) -> str:
    return f"{STICKER_BOILERPLATE} {STYLE_FROM_SAMPLES} Expression: {emotion.prompt_fragment}."
