"""Stage-1 integration test: the full pipeline end-to-end on FakeBackend."""

import pytest

from tg_sticker_shot import core_pipeline
from tg_sticker_shot.api_fake import FIXTURE_PNG, FakeBackend
from tg_sticker_shot.core_emotions import load_emotions
from tg_sticker_shot.core_persistence import Project, ProjectStateError, open_project
from tg_sticker_shot.core_pipeline import SAMPLE_COUNT, STYLE_FROM_SAMPLES

STYLE_GUIDE = "chibi, super-deformed, bold outlines"


@pytest.fixture
def project(tmp_path) -> Project:
    ref = tmp_path / "ref.png"
    ref.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    core_pipeline.ingest(project, [str(ref)])
    return project


def test_full_pipeline(project: Project) -> None:
    backend = FakeBackend()
    emotions = load_emotions()

    sample_report = core_pipeline.generate_style_samples(project, backend, STYLE_GUIDE)
    assert len(sample_report.generated) == SAMPLE_COUNT
    assert sample_report.skipped == []
    assert len(project.load_samples()) == SAMPLE_COUNT
    # Sample prompts carry the user-supplied style guide.
    assert all(STYLE_GUIDE in prompt for _, prompt in backend.calls)

    batch_report = core_pipeline.generate_batch(project, backend)
    assert len(batch_report.generated) == len(emotions)
    for emotion in emotions:
        assert project.has_result(emotion.emoji)

    # Batch prompts use the hardcoded style-from-samples text, not the guide.
    batch_prompts = [prompt for _, prompt in backend.calls[-len(emotions) :]]
    assert all(STYLE_FROM_SAMPLES in prompt for prompt in batch_prompts)
    assert all(STYLE_GUIDE not in prompt for prompt in batch_prompts)
    for emotion, prompt in zip(emotions, batch_prompts, strict=True):
        assert emotion.prompt_fragment in prompt

    # Batch references = original refs + samples, never previous results.
    ref_counts = {count for count, _ in backend.calls[-len(emotions) :]}
    assert ref_counts == {1 + SAMPLE_COUNT}


def test_batch_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_style_samples(project, backend, STYLE_GUIDE)
    core_pipeline.generate_batch(project, backend)

    calls_before = len(backend.calls)
    report = core_pipeline.generate_batch(project, backend)
    assert report.generated == []
    assert len(report.skipped) == len(load_emotions())
    assert len(backend.calls) == calls_before


def test_style_stage_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_style_samples(project, backend, STYLE_GUIDE)
    calls_before = len(backend.calls)
    report = core_pipeline.generate_style_samples(project, backend, STYLE_GUIDE)
    assert report.generated == []
    assert len(report.skipped) == SAMPLE_COUNT
    assert len(backend.calls) == calls_before


def test_style_samples_resume_after_partial_failure(project: Project) -> None:
    """A backend crash mid-run must not leave the project permanently half-sampled."""

    class FlakyBackend:
        name = "flaky"

        def __init__(self) -> None:
            self.count = 0

        def generate(self, refs: list[bytes], prompt: str) -> bytes:
            self.count += 1
            if self.count == 2:
                raise RuntimeError("backend down")
            return FIXTURE_PNG

    with pytest.raises(RuntimeError, match="backend down"):
        core_pipeline.generate_style_samples(project, FlakyBackend(), STYLE_GUIDE)

    core_pipeline.generate_style_samples(project, FakeBackend(), STYLE_GUIDE)
    assert len(project.load_samples()) == SAMPLE_COUNT


def test_changing_style_guide_fails(project: Project) -> None:
    core_pipeline.generate_style_samples(project, FakeBackend(), STYLE_GUIDE)
    with pytest.raises(ProjectStateError, match="already has style guide"):
        core_pipeline.generate_style_samples(project, FakeBackend(), "pixel art")


def test_batch_without_style_samples_fails(project: Project) -> None:
    """Batch must not silently run without style samples (anti-drift rule)."""
    with pytest.raises(ProjectStateError, match="no style samples"):
        core_pipeline.generate_batch(project, FakeBackend())
