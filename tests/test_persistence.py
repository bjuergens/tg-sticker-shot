import json

import pytest
from filelock import Timeout

from tg_sticker_shot import core_persistence
from tg_sticker_shot.api_fake import FIXTURE_PNG
from tg_sticker_shot.core_persistence import ProjectStateError, open_project


def test_references_roundtrip(tmp_path) -> None:
    source = tmp_path / "guts.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)

    assert project.add_reference_from_file(str(source)) == "reference_1.png"
    assert project.add_reference_from_file(str(source)) == "reference_2.png"
    assert project.load_references() == [FIXTURE_PNG, FIXTURE_PNG]


def test_add_reference_missing_file_fails(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="not found"):
        project.add_reference_from_file(str(tmp_path / "nope.png"))


def test_load_references_empty_fails(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="no reference images"):
        project.load_references()


def test_reference_index_gap_never_overwrites(tmp_path) -> None:
    """Deleting reference_1 must not make the next ingest overwrite reference_2."""
    source = tmp_path / "ref.png"
    project = open_project(str(tmp_path / "proj"), create=True)
    source.write_bytes(b"first")
    project.add_reference_from_file(str(source))
    source.write_bytes(b"second")
    project.add_reference_from_file(str(source))
    (tmp_path / "proj" / "reference_1.png").unlink()

    source.write_bytes(b"third")
    assert project.add_reference_from_file(str(source)) == "reference_3.png"
    assert project.load_references() == [b"second", b"third"]


def test_stray_reference_file_fails_loudly(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    (tmp_path / "reference_backup.png").write_bytes(b"stray")
    with pytest.raises(ProjectStateError, match="reference_backup.png"):
        project.load_references()


def test_samples_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert project.save_sample("chibi", 1, b"a") == "sample_chibi_1.png"
    project.save_sample("chibi", 2, b"b")
    project.save_sample("pixel-art", 1, b"c")

    assert project.load_samples("chibi") == [b"a", b"b"]
    assert project.load_samples("watercolor") == []
    assert project.has_sample("chibi", 2)
    assert not project.has_sample("chibi", 3)
    assert project.list_sample_styles() == ["chibi", "pixel-art"]


def test_samples_of_prefix_styles_stay_separate(tmp_path) -> None:
    """Style 'chibi' must not pick up samples of a style named 'chibi_v2'."""
    project = open_project(str(tmp_path), create=True)
    project.save_sample("chibi", 1, b"a")
    project.save_sample("chibi_v2", 1, b"X")

    assert project.load_samples("chibi") == [b"a"]
    assert project.load_samples("chibi_v2") == [b"X"]
    assert project.status().samples_per_style == {"chibi": 1, "chibi_v2": 1}


def test_stray_sample_file_fails_loudly(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    (tmp_path / "sample_note.png").write_bytes(b"stray")
    with pytest.raises(ProjectStateError, match="sample_note.png"):
        project.load_samples("chibi")


def test_results_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert not project.has_result("😂")
    assert project.save_result("😂", b"img") == "result_😂.png"
    assert project.has_result("😂")
    assert project.list_results() == ["😂"]


def test_chosen_style(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="no style chosen"):
        project.load_chosen_style()
    project.save_chosen_style("chibi")
    assert project.load_chosen_style() == "chibi"


def test_record_run_appends(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    project.record_run("styles", {"backend": "fake"})
    project.record_run("batch", {"backend": "fake"})
    runs = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["runs"]
    assert [run["stage"] for run in runs] == ["styles", "batch"]
    assert all("timestamp" in run for run in runs)


def test_status(tmp_path) -> None:
    source = tmp_path / "ref.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    project.add_reference_from_file(str(source))
    project.save_sample("chibi", 1, b"a")
    project.save_chosen_style("chibi")
    project.save_result("😂", b"img")

    state = project.status()
    assert state.reference_count == 1
    assert state.samples_per_style == {"chibi": 1}
    assert state.chosen_style == "chibi"
    assert state.result_emojis == ["😂"]


def test_open_project_without_create_fails_on_missing_dir(tmp_path) -> None:
    with pytest.raises(ProjectStateError, match="not found"):
        open_project(str(tmp_path / "does-not-exist"), create=False)


def test_lock_is_exclusive(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(core_persistence, "_LOCK_TIMEOUT_SECONDS", 0)
    project_a = open_project(str(tmp_path), create=True)
    project_b = open_project(str(tmp_path), create=True)
    with project_a.lock():
        with pytest.raises(Timeout):
            with project_b.lock():
                pass


def test_reference_ordering_is_numeric(tmp_path) -> None:
    """reference_10 must sort after reference_2, not between 1 and 2."""
    source = tmp_path / "ref.png"
    project = open_project(str(tmp_path / "proj"), create=True)
    for index in range(1, 11):
        source.write_bytes(f"img{index}".encode())
        project.add_reference_from_file(str(source))
    assert project.load_references()[-1] == b"img10"
