import json

import pytest
from filelock import Timeout

from tg_sticker_shot import core_persistence
from tg_sticker_shot.api_fake import FIXTURE_PNG
from tg_sticker_shot.core_persistence import ProjectStateError, open_project


def test_references_roundtrip(tmp_path) -> None:
    source = tmp_path / "guts.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"))

    assert project.add_reference_from_file(str(source)) == "reference_1.png"
    assert project.add_reference_from_file(str(source)) == "reference_2.png"
    assert project.load_references() == [FIXTURE_PNG, FIXTURE_PNG]


def test_add_reference_missing_file_fails(tmp_path) -> None:
    project = open_project(str(tmp_path))
    with pytest.raises(ProjectStateError, match="not found"):
        project.add_reference_from_file(str(tmp_path / "nope.png"))


def test_load_references_empty_fails(tmp_path) -> None:
    project = open_project(str(tmp_path))
    with pytest.raises(ProjectStateError, match="no reference images"):
        project.load_references()


def test_samples_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path))
    assert project.save_sample("chibi", 1, b"a") == "sample_chibi_1.png"
    project.save_sample("chibi", 2, b"b")
    project.save_sample("pixel-art", 1, b"c")

    assert project.load_samples("chibi") == [b"a", b"b"]
    assert project.load_samples("watercolor") == []
    assert project.list_sample_styles() == ["chibi", "pixel-art"]


def test_results_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path))
    assert not project.has_result("😂")
    assert project.save_result("😂", b"img") == "result_😂.png"
    assert project.has_result("😂")
    assert project.list_results() == ["😂"]


def test_chosen_style(tmp_path) -> None:
    project = open_project(str(tmp_path))
    with pytest.raises(ProjectStateError, match="no style chosen"):
        project.load_chosen_style()
    project.save_chosen_style("chibi")
    assert project.load_chosen_style() == "chibi"


def test_record_run_appends(tmp_path) -> None:
    project = open_project(str(tmp_path))
    project.record_run("styles", {"backend": "fake"})
    project.record_run("batch", {"backend": "fake"})
    runs = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["runs"]
    assert [run["stage"] for run in runs] == ["styles", "batch"]
    assert all("timestamp" in run for run in runs)


def test_status(tmp_path) -> None:
    source = tmp_path / "ref.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"))
    project.add_reference_from_file(str(source))
    project.save_sample("chibi", 1, b"a")
    project.save_chosen_style("chibi")
    project.save_result("😂", b"img")

    state = project.status()
    assert state.reference_count == 1
    assert state.samples_per_style == {"chibi": 1}
    assert state.chosen_style == "chibi"
    assert state.result_emojis == ["😂"]


def test_lock_is_exclusive(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(core_persistence, "_LOCK_TIMEOUT_SECONDS", 0)
    project_a = open_project(str(tmp_path))
    project_b = open_project(str(tmp_path))
    with project_a.lock():
        with pytest.raises(Timeout):
            with project_b.lock():
                pass


def test_reference_ordering_is_numeric(tmp_path) -> None:
    """reference_10 must sort after reference_2, not between 1 and 2."""
    source = tmp_path / "ref.png"
    project = open_project(str(tmp_path / "proj"))
    for index in range(1, 11):
        source.write_bytes(f"img{index}".encode())
        project.add_reference_from_file(str(source))
    assert project.load_references()[-1] == b"img10"
