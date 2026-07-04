"""Pipeline stages: ingest → styles → select → batch → status.

Each stage is a plain function over (Project, ImageBackend) so the CLI stays
thin and the whole pipeline is testable without typer or network access.
"""

from dataclasses import dataclass

from tg_sticker_shot.api_base import ImageBackend
from tg_sticker_shot.core_persistence import Project, ProjectStateError
from tg_sticker_shot.core_styles import Emotion, Style, load_emotions, load_styles

SAMPLES_PER_STYLE = 2

# Shared prompt boilerplate for every generation (samples and batch).
STICKER_BOILERPLATE = (
    "Telegram sticker of the character shown in the reference images. "
    "Keep the character's identity, outfit and colors consistent with the references. "
    "Single centered character, plain solid white background suitable for background "
    "removal, no text, no watermark."
)


@dataclass(frozen=True)
class StageReport:
    generated: list[str]
    skipped: list[str]


def ingest(project: Project, image_files: list[str]) -> list[str]:
    """Copy reference images into the project. Returns the stored filenames."""
    return [project.add_reference_from_file(source) for source in image_files]


def generate_style_samples(project: Project, backend: ImageBackend) -> StageReport:
    """Generate SAMPLES_PER_STYLE sample stickers per style; skip styles that have them."""
    refs = project.load_references()
    generated: list[str] = []
    skipped: list[str] = []
    for style in load_styles().values():
        if project.load_samples(style.name):
            skipped.append(style.name)
            continue
        for index in range(1, SAMPLES_PER_STYLE + 1):
            image = backend.generate(refs, _sample_prompt(style))
            generated.append(project.save_sample(style.name, index, image))
    project.record_run("styles", {"backend": backend.name, "generated": len(generated)})
    return StageReport(generated=generated, skipped=skipped)


def select_style(project: Project, style_name: str) -> None:
    """Record the chosen style; the name must exist in styles.yaml."""
    styles = load_styles()
    if style_name not in styles:
        raise ProjectStateError(
            f"unknown style '{style_name}' — available: {', '.join(sorted(styles))}"
        )
    project.save_chosen_style(style_name)
    project.record_run("select", {"style": style_name})


def generate_batch(project: Project, backend: ImageBackend) -> StageReport:
    """Generate result_<emoji>.png per emotion; idempotent (skips existing results).

    References are always the original refs + the chosen style's samples, never
    previous results — chaining output→output causes identity drift.
    """
    style = load_styles()[project.load_chosen_style()]
    refs = project.load_references() + project.load_samples(style.name)
    generated: list[str] = []
    skipped: list[str] = []
    for emotion in load_emotions():
        if project.has_result(emotion.emoji):
            skipped.append(emotion.emoji)
            continue
        image = backend.generate(refs, _emotion_prompt(style, emotion))
        generated.append(project.save_result(emotion.emoji, image))
    project.record_run("batch", {"backend": backend.name, "generated": len(generated)})
    return StageReport(generated=generated, skipped=skipped)


def missing_emotions(project: Project) -> list[Emotion]:
    """Emotions that have no result yet (for status output)."""
    return [emotion for emotion in load_emotions() if not project.has_result(emotion.emoji)]


def _sample_prompt(style: Style) -> str:
    return f"{STICKER_BOILERPLATE} {style.prompt} Expression: friendly neutral smile."


def _emotion_prompt(style: Style, emotion: Emotion) -> str:
    return f"{STICKER_BOILERPLATE} {style.prompt} Expression: {emotion.prompt_fragment}."
