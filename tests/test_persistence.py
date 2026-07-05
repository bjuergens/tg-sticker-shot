import json

import pytest
from filelock import Timeout

from tg_sticker_shot import core_persistence
from tg_sticker_shot.api_fake import FIXTURE_PNG
from tg_sticker_shot.core_persistence import ProjectStateError, open_project


def test_sources_roundtrip(tmp_path) -> None:
    source = tmp_path / "guts.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)

    assert project.add_source_from_file(str(source)) == "source_1.png"
    assert project.add_source_from_file(str(source)) == "source_2.png"
    assert project.load_sources() == [FIXTURE_PNG, FIXTURE_PNG]


def test_add_source_missing_file_fails(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="not found"):
        project.add_source_from_file(str(tmp_path / "nope.png"))


def test_load_sources_empty_fails(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="no source images"):
        project.load_sources()


def test_source_index_gap_never_overwrites(tmp_path) -> None:
    """Deleting source_1 must not make the next ingest overwrite source_2."""
    source = tmp_path / "ref.png"
    project = open_project(str(tmp_path / "proj"), create=True)
    source.write_bytes(b"first")
    project.add_source_from_file(str(source))
    source.write_bytes(b"second")
    project.add_source_from_file(str(source))
    (tmp_path / "proj" / "source_1.png").unlink()

    source.write_bytes(b"third")
    assert project.add_source_from_file(str(source)) == "source_3.png"
    assert project.load_sources() == [b"second", b"third"]


def test_stray_source_file_fails_loudly(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    (tmp_path / "source_backup.png").write_bytes(b"stray")
    with pytest.raises(ProjectStateError, match="source_backup.png"):
        project.load_sources()


def test_refs_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert project.save_ref("bust", 1, b"a") == "ref_bust_1.png"
    project.save_ref("bust", 2, b"b")

    assert project.load_refs() == [b"a", b"b"]
    assert project.has_ref("bust", 2)
    assert not project.has_ref("bust", 3)
    assert not project.has_ref("half", 1)


def test_refs_load_in_canonical_framing_order(tmp_path) -> None:
    """bust refs come first regardless of save order (batch prompt stability)."""
    project = open_project(str(tmp_path), create=True)
    project.save_ref("full", 1, b"full")
    project.save_ref("half", 1, b"half")
    project.save_ref("bust", 1, b"bust")
    assert project.load_refs() == [b"bust", b"half", b"full"]


def test_save_ref_unknown_framing_fails(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    with pytest.raises(ProjectStateError, match="unknown framing"):
        project.save_ref("torso", 1, b"a")


def test_stray_ref_file_fails_loudly(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    (tmp_path / "ref_note.png").write_bytes(b"stray")
    with pytest.raises(ProjectStateError, match="ref_note.png"):
        project.load_refs()


def test_results_roundtrip(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert not project.has_result("😂")
    assert project.save_result("😂", b"img") == "result_😂.png"
    assert project.has_result("😂")
    assert project.list_results() == ["😂"]


def test_style_guide(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert project.load_style_guide_or_none() is None
    project.save_style_guide("chibi, bold outlines")
    assert project.load_style_guide_or_none() == "chibi, bold outlines"


def test_framing(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    assert project.load_framing_or_none() is None
    project.save_framing("vary")
    assert project.load_framing_or_none() == "vary"


def test_record_run_appends(tmp_path) -> None:
    project = open_project(str(tmp_path), create=True)
    project.record_run("refs", {"backend": "fake"})
    project.record_run("batch", {"backend": "fake"})
    runs = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["runs"]
    assert [run["stage"] for run in runs] == ["refs", "batch"]
    assert all("timestamp" in run for run in runs)


def test_status(tmp_path) -> None:
    source = tmp_path / "ref.png"
    source.write_bytes(FIXTURE_PNG)
    project = open_project(str(tmp_path / "proj"), create=True)
    project.add_source_from_file(str(source))
    project.save_ref("bust", 1, b"a")
    project.save_style_guide("chibi")
    project.save_result("😂", b"img")

    state = project.status()
    assert state.source_count == 1
    assert state.ref_count == 1
    assert state.style_guide == "chibi"
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


def test_source_ordering_is_numeric(tmp_path) -> None:
    """source_10 must sort after source_2, not between 1 and 2."""
    source = tmp_path / "ref.png"
    project = open_project(str(tmp_path / "proj"), create=True)
    for index in range(1, 11):
        source.write_bytes(f"img{index}".encode())
        project.add_source_from_file(str(source))
    assert project.load_sources()[-1] == b"img10"
