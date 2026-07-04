"""Stage-1 integration test: the full pipeline end-to-end on FakeBackend."""

import pytest

from tg_sticker_shot import core_pipeline
from tg_sticker_shot.api_fake import FIXTURE_PNG, FakeBackend
from tg_sticker_shot.core_persistence import Project, ProjectStateError, open_project
from tg_sticker_shot.core_pipeline import SAMPLES_PER_STYLE
from tg_sticker_shot.core_styles import load_emotions, load_styles


@pytest.fixture
def project(tmp_path) -> Project:
    ref = tmp_path / "ref.png"
    ref.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"))
    core_pipeline.ingest(project, [str(ref)])
    return project


def test_full_pipeline(project: Project) -> None:
    backend = FakeBackend()
    styles = load_styles()
    emotions = load_emotions()

    sample_report = core_pipeline.generate_style_samples(project, backend)
    assert len(sample_report.generated) == len(styles) * SAMPLES_PER_STYLE
    assert sample_report.skipped == []
    assert project.list_sample_styles() == sorted(styles)

    core_pipeline.select_style(project, "chibi")

    batch_report = core_pipeline.generate_batch(project, backend)
    assert len(batch_report.generated) == len(emotions)
    for emotion in emotions:
        assert project.has_result(emotion.emoji)

    # Batch prompts carry the chosen style and the emotion fragments.
    batch_prompts = [prompt for _, prompt in backend.calls[-len(emotions) :]]
    assert all(styles["chibi"].prompt in prompt for prompt in batch_prompts)
    for emotion, prompt in zip(emotions, batch_prompts, strict=True):
        assert emotion.prompt_fragment in prompt

    # Batch references = original refs + chosen style samples, never previous results.
    ref_counts = {count for count, _ in backend.calls[-len(emotions) :]}
    assert ref_counts == {1 + SAMPLES_PER_STYLE}


def test_batch_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_style_samples(project, backend)
    core_pipeline.select_style(project, "chibi")
    core_pipeline.generate_batch(project, backend)

    calls_before = len(backend.calls)
    report = core_pipeline.generate_batch(project, backend)
    assert report.generated == []
    assert len(report.skipped) == len(load_emotions())
    assert len(backend.calls) == calls_before


def test_styles_stage_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_style_samples(project, backend)
    calls_before = len(backend.calls)
    report = core_pipeline.generate_style_samples(project, backend)
    assert report.generated == []
    assert sorted(report.skipped) == sorted(load_styles())
    assert len(backend.calls) == calls_before


def test_select_unknown_style_fails(project: Project) -> None:
    with pytest.raises(ProjectStateError, match="unknown style"):
        core_pipeline.select_style(project, "vaporwave")


def test_batch_without_selected_style_fails(project: Project) -> None:
    with pytest.raises(ProjectStateError, match="no style chosen"):
        core_pipeline.generate_batch(project, FakeBackend())
