"""Stage-1 integration test: the full pipeline end-to-end on FakeBackend."""

import pytest

from tg_sticker_shot import core_pipeline
from tg_sticker_shot.api_fake import FIXTURE_PNG, FakeBackend
from tg_sticker_shot.core_emotions import load_emotions
from tg_sticker_shot.core_persistence import FRAMINGS, Project, ProjectStateError, open_project
from tg_sticker_shot.core_pipeline import REF_SPECS, STYLE_FROM_REFS, VARY

STYLE_GUIDE = "chibi, super-deformed, bold outlines"


@pytest.fixture
def project(tmp_path) -> Project:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    core_pipeline.ingest(project, [str(source)])
    return project


def test_full_pipeline(project: Project) -> None:
    backend = FakeBackend()
    emotions = load_emotions()

    ref_report = core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    assert ref_report.generated == ["ref_bust_1.png", "ref_half_1.png", "ref_full_1.png"]
    assert ref_report.skipped == []
    assert len(project.load_refs()) == len(FRAMINGS)
    # Ref prompts carry the user-supplied style guide; refs see the sources only.
    assert all(STYLE_GUIDE in prompt for _, prompt in backend.calls)
    assert {count for count, _ in backend.calls} == {1}

    batch_report = core_pipeline.generate_batch(project, backend)
    assert len(batch_report.generated) == len(emotions)
    for emotion in emotions:
        assert project.has_result(emotion.emoji)

    # Batch prompts use the hardcoded style-from-refs text, not the guide.
    batch_prompts = [prompt for _, prompt in backend.calls[-len(emotions) :]]
    assert all(STYLE_FROM_REFS in prompt for prompt in batch_prompts)
    assert all(STYLE_GUIDE not in prompt for prompt in batch_prompts)
    for emotion, prompt in zip(emotions, batch_prompts, strict=True):
        assert emotion.prompt_fragment in prompt

    # Batch references = the generated refs only, never sources or previous results.
    ref_counts = {count for count, _ in backend.calls[-len(emotions) :]}
    assert ref_counts == {len(FRAMINGS)}


@pytest.mark.parametrize("framing", FRAMINGS)
def test_single_framing_generates_all_its_specs(project: Project, framing: str) -> None:
    backend = FakeBackend()
    report = core_pipeline.generate_refs(project, backend, STYLE_GUIDE, framing)
    assert report.generated == [
        f"ref_{framing}_{index}.png" for index in range(1, len(REF_SPECS[framing]) + 1)
    ]
    # Every spec's composition text ends up in its prompt, in order.
    for spec, (_, prompt) in zip(REF_SPECS[framing], backend.calls, strict=True):
        assert spec in prompt


def test_batch_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    core_pipeline.generate_batch(project, backend)

    calls_before = len(backend.calls)
    report = core_pipeline.generate_batch(project, backend)
    assert report.generated == []
    assert len(report.skipped) == len(load_emotions())
    assert len(backend.calls) == calls_before


def test_refs_stage_is_idempotent(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    calls_before = len(backend.calls)
    report = core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    assert report.generated == []
    assert len(report.skipped) == len(FRAMINGS)
    assert len(backend.calls) == calls_before


def test_refs_resume_after_partial_failure(project: Project) -> None:
    """A backend crash mid-run must not leave the project permanently half-reffed."""

    class FlakyBackend:
        name = "flaky"
        model_id = "fake"  # match FakeBackend so the resume run passes the model lock

        def __init__(self) -> None:
            self.count = 0

        def generate(self, refs: list[bytes], prompt: str) -> bytes:
            self.count += 1
            if self.count == 2:
                raise RuntimeError("backend down")
            return FIXTURE_PNG

        def critique(self, images: list[bytes], prompt: str) -> str:
            raise NotImplementedError

    with pytest.raises(RuntimeError, match="backend down"):
        core_pipeline.generate_refs(project, FlakyBackend(), STYLE_GUIDE, VARY)

    core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, VARY)
    assert len(project.load_refs()) == len(FRAMINGS)


def test_redo_overwrites_and_steers(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    core_pipeline.generate_batch(project, backend)

    report = core_pipeline.redo_stickers(
        project, backend, ["😂"], hint="mouth wide open", good=["😎"]
    )
    assert report.generated == ["result_😂.png"]
    assert report.skipped == []
    assert project.has_result("😂")
    count, prompt = backend.calls[-1]
    assert count == len(FRAMINGS) + 1  # the refs plus one good result
    fragment = next(e.prompt_fragment for e in load_emotions() if e.emoji == "😂")
    assert fragment in prompt
    assert "Additional instructions: mouth wide open." in prompt


def test_redo_without_hint_keeps_standard_prompt(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    core_pipeline.generate_batch(project, backend)

    core_pipeline.redo_stickers(project, backend, ["😂"])
    count, prompt = backend.calls[-1]
    assert count == len(FRAMINGS)
    assert "Additional instructions" not in prompt


def test_redo_unknown_emoji_fails(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    with pytest.raises(ProjectStateError, match="unknown emoji"):
        core_pipeline.redo_stickers(project, backend, ["🦄"])


def test_redo_good_without_result_fails(project: Project) -> None:
    backend = FakeBackend()
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    with pytest.raises(ProjectStateError, match="no result"):
        core_pipeline.redo_stickers(project, backend, ["😂"], good=["😎"])


def test_redo_without_refs_fails(project: Project) -> None:
    with pytest.raises(ProjectStateError, match="no reference images"):
        core_pipeline.redo_stickers(project, FakeBackend(), ["😂"])


def test_changing_model_fails(project: Project) -> None:
    """The image model is locked per project, like the style guide."""
    backend_a = FakeBackend()
    backend_a.model_id = "model-a"
    core_pipeline.generate_refs(project, backend_a, STYLE_GUIDE, VARY)

    backend_b = FakeBackend()
    backend_b.model_id = "model-b"
    with pytest.raises(ProjectStateError, match="already generated with model 'model-a'"):
        core_pipeline.generate_batch(project, backend_b)
    with pytest.raises(ProjectStateError, match="already generated with model 'model-a'"):
        core_pipeline.redo_stickers(project, backend_b, ["😂"])

    core_pipeline.generate_batch(project, backend_a)  # same model is fine


def test_changing_style_guide_fails(project: Project) -> None:
    core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, VARY)
    with pytest.raises(ProjectStateError, match="already has style guide"):
        core_pipeline.generate_refs(project, FakeBackend(), "pixel art", VARY)


def test_changing_framing_fails(project: Project) -> None:
    core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, VARY)
    with pytest.raises(ProjectStateError, match="already has framing"):
        core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, "bust")


def test_unknown_framing_fails(project: Project) -> None:
    with pytest.raises(ProjectStateError, match="unknown framing"):
        core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, "torso")


def test_batch_without_refs_fails(project: Project) -> None:
    """Batch must not silently run without refs (anti-drift rule)."""
    with pytest.raises(ProjectStateError, match="no reference images"):
        core_pipeline.generate_batch(project, FakeBackend())
