"""Review-stage tests on FakeBackend: verdict parsing, offender selection, auto-redo."""

import json

import pytest

from tg_sticker_shot import core_pipeline, core_review
from tg_sticker_shot.api_fake import FIXTURE_PNG, FakeBackend
from tg_sticker_shot.core_emotions import load_emotions
from tg_sticker_shot.core_persistence import FRAMINGS, Project, ProjectStateError, open_project
from tg_sticker_shot.core_pipeline import VARY
from tg_sticker_shot.core_review import ReviewError, parse_review

STYLE_GUIDE = "chibi, bold outlines"


def _verdict(
    identity: int = 9,
    emotion: int = 9,
    quality: int = 9,
    issues: str = "",
    redo_hint: str = "",
) -> str:
    return json.dumps(
        {
            "identity": identity,
            "emotion": emotion,
            "quality": quality,
            "issues": issues,
            "redo_hint": redo_hint,
        }
    )


@pytest.fixture
def project(tmp_path) -> Project:
    """A project with refs and a full set of results."""
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    backend = FakeBackend()
    core_pipeline.ingest(project, [str(source)])
    core_pipeline.generate_refs(project, backend, STYLE_GUIDE, VARY)
    core_pipeline.generate_batch(project, backend)
    return project


# -- parse_review ---------------------------------------------------------


def test_parse_review_plain_json() -> None:
    review = parse_review("😂", _verdict(identity=3, issues="wrong outfit", redo_hint="fix hat"))
    assert review.emoji == "😂"
    assert review.identity == 3
    assert review.worst_score == 3
    assert review.issues == "wrong outfit"
    assert review.redo_hint == "fix hat"


def test_parse_review_tolerates_markdown_fence() -> None:
    review = parse_review("😂", f"```json\n{_verdict(quality=5)}\n```")
    assert review.quality == 5


def test_parse_review_garbage_fails() -> None:
    with pytest.raises(ReviewError, match="not valid JSON"):
        parse_review("😂", "the sticker looks great!")


def test_parse_review_non_object_fails() -> None:
    with pytest.raises(ReviewError, match="not a JSON object"):
        parse_review("😂", "[1, 2, 3]")


def test_parse_review_missing_or_bad_score_fails() -> None:
    with pytest.raises(ReviewError, match="'emotion'"):
        parse_review("😂", json.dumps({"identity": 9, "quality": 9}))
    with pytest.raises(ReviewError, match="'identity'"):
        parse_review("😂", json.dumps({"identity": 11, "emotion": 9, "quality": 9}))
    with pytest.raises(ReviewError, match="'identity'"):
        parse_review("😂", json.dumps({"identity": True, "emotion": 9, "quality": 9}))


def test_parse_review_non_string_issues_fails() -> None:
    with pytest.raises(ReviewError, match="issues/redo_hint"):
        parse_review("😂", json.dumps({"identity": 9, "emotion": 9, "quality": 9, "issues": 1}))


# -- review_set -----------------------------------------------------------


def test_review_all_good_flags_nothing(project: Project) -> None:
    backend = FakeBackend()
    emotions = load_emotions()
    report = core_review.review_set(project, backend, threshold=6, max_redo=5, redo=True)

    assert [review.emoji for review in report.reviews] == [e.emoji for e in emotions]
    assert report.flagged == []
    assert report.redone == []
    assert backend.calls == []  # nothing regenerated
    # Each critique sees the refs plus the one candidate, and names the emotion.
    assert {count for count, _ in backend.critique_calls} == {len(FRAMINGS) + 1}
    for emotion, (_, prompt) in zip(emotions, backend.critique_calls, strict=True):
        assert emotion.name in prompt
        assert emotion.prompt_fragment in prompt


def test_review_redoes_offender_with_hint(project: Project) -> None:
    backend = FakeBackend()
    backend.critique_responses = [
        _verdict(identity=3, issues="wrong outfit", redo_hint="keep the red scarf")
        if emotion.emoji == "😢"
        else _verdict()
        for emotion in load_emotions()
    ]
    report = core_review.review_set(project, backend, threshold=6, max_redo=5, redo=True)

    assert [review.emoji for review in report.flagged] == ["😢"]
    assert report.redone == ["😢"]
    count, prompt = backend.calls[-1]
    assert count == len(FRAMINGS)  # redo via refs only, no good results implied
    assert "Additional instructions: keep the red scarf." in prompt


def test_review_caps_redos_worst_first(project: Project) -> None:
    worst_scores = {"😂": 4, "😡": 2, "😍": 3}
    backend = FakeBackend()
    backend.critique_responses = [
        _verdict(emotion=worst_scores[e.emoji]) if e.emoji in worst_scores else _verdict()
        for e in load_emotions()
    ]
    report = core_review.review_set(project, backend, threshold=6, max_redo=2, redo=True)

    assert [review.emoji for review in report.flagged] == ["😡", "😍"]
    assert report.redone == ["😡", "😍"]
    assert len(backend.calls) == 2


def test_review_no_redo_reports_only(project: Project) -> None:
    backend = FakeBackend()
    backend.critique_responses = [
        _verdict(quality=2) if e.emoji == "😂" else _verdict() for e in load_emotions()
    ]
    report = core_review.review_set(project, backend, threshold=6, max_redo=5, redo=False)

    assert [review.emoji for review in report.flagged] == ["😂"]
    assert report.redone == []
    assert backend.calls == []


def test_review_without_results_fails(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    core_pipeline.ingest(project, [str(source)])
    core_pipeline.generate_refs(project, FakeBackend(), STYLE_GUIDE, VARY)
    with pytest.raises(ProjectStateError, match="no results to review"):
        core_review.review_set(project, FakeBackend(), threshold=6, max_redo=5, redo=True)


def test_review_without_refs_fails(tmp_path) -> None:
    project = open_project(str(tmp_path / "proj"), create=True)
    with pytest.raises(ProjectStateError, match="no reference images"):
        core_review.review_set(project, FakeBackend(), threshold=6, max_redo=5, redo=True)
