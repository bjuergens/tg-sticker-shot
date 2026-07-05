"""All filesystem access for project directories lives here.

Only this module imports pathlib. The API speaks domain terms (sources,
refs, results, chosen style) and hands out bytes/str, never Path objects.

Project directory layout (flat, prefixed files):
    source_<n>.png            (user-provided input images)
    ref_<framing>_<n>.png     (generated canonical reference images)
    result_<emoji>.png
    project.json              (style guide, framing, model + run metadata)
    .shot.lock                (inter-process lock)
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

_PROJECT_FILE = "project.json"
_LOCK_FILE = ".shot.lock"
_LOCK_TIMEOUT_SECONDS = 10

# Ref framings, in canonical order (load_refs returns bust refs first).
FRAMINGS = ("bust", "half", "full")

# Strict filename patterns: anything matching the glob prefix but not the full
# pattern (e.g. a stray source_backup.png) is an error, not silently ignored.
_SOURCE_RE = re.compile(r"source_(\d+)\.png")
_REF_RE = re.compile(rf"ref_({'|'.join(FRAMINGS)})_(\d+)\.png")


class ProjectStateError(Exception):
    """The project directory is not in the state an operation requires."""


@dataclass(frozen=True)
class ProjectStatus:
    source_count: int
    ref_count: int
    style_guide: str | None
    model: str | None
    result_emojis: list[str]


@dataclass
class Project:
    """Handle to one project directory. Create via open_project()."""

    _dir: Path

    # -- sources (user-provided input images) ---------------------------------

    def add_source_from_file(self, source: str) -> str:
        """Copy an external image file in as the next source_<n>.png."""
        source_path = Path(source)
        if not source_path.is_file():
            raise ProjectStateError(f"source image not found: {source}")
        sources = self._indexed_sources()
        index = sources[-1][0] + 1 if sources else 1  # max + 1, gaps never overwrite
        name = f"source_{index}.png"
        (self._dir / name).write_bytes(source_path.read_bytes())
        return name

    def load_sources(self) -> list[bytes]:
        sources = self._indexed_sources()
        if not sources:
            raise ProjectStateError(
                f"no source images in project '{self._dir}' — run `shot ingest` first"
            )
        return [path.read_bytes() for _, path in sources]

    def _indexed_sources(self) -> list[tuple[int, Path]]:
        entries: list[tuple[int, Path]] = []
        for path in self._dir.glob("source_*.png"):
            match = _SOURCE_RE.fullmatch(path.name)
            if match is None:
                raise ProjectStateError(
                    f"unexpected file '{path.name}' in project '{self._dir}' — "
                    "expected source_<n>.png"
                )
            entries.append((int(match.group(1)), path))
        return sorted(entries)

    # -- refs (generated canonical reference images) ---------------------------

    def save_ref(self, framing: str, index: int, data: bytes) -> str:
        if framing not in FRAMINGS:
            raise ProjectStateError(f"unknown framing '{framing}' — expected one of {FRAMINGS}")
        name = f"ref_{framing}_{index}.png"
        (self._dir / name).write_bytes(data)
        return name

    def load_refs(self) -> list[bytes]:
        return [path.read_bytes() for _, _, path in self._indexed_refs()]

    def has_ref(self, framing: str, index: int) -> bool:
        return (self._dir / f"ref_{framing}_{index}.png").is_file()

    def _indexed_refs(self) -> list[tuple[int, int, Path]]:
        entries: list[tuple[int, int, Path]] = []
        for path in self._dir.glob("ref_*.png"):
            match = _REF_RE.fullmatch(path.name)
            if match is None:
                raise ProjectStateError(
                    f"unexpected file '{path.name}' in project '{self._dir}' — "
                    "expected ref_<framing>_<n>.png"
                )
            entries.append((FRAMINGS.index(match.group(1)), int(match.group(2)), path))
        return sorted(entries)

    # -- results -------------------------------------------------------------

    def save_result(self, emoji: str, data: bytes) -> str:
        name = f"result_{emoji}.png"
        (self._dir / name).write_bytes(data)
        return name

    def load_result(self, emoji: str) -> bytes:
        path = self._dir / f"result_{emoji}.png"
        if not path.is_file():
            raise ProjectStateError(f"no result for {emoji} in project '{self._dir}'")
        return path.read_bytes()

    def has_result(self, emoji: str) -> bool:
        return (self._dir / f"result_{emoji}.png").is_file()

    def list_results(self) -> list[str]:
        return sorted(p.stem.removeprefix("result_") for p in self._dir.glob("result_*.png"))

    # -- style guide / framing / model / run metadata (project.json) -----------

    def save_style_guide(self, style_guide: str) -> None:
        self._update_project_file(style_guide=style_guide)

    def load_style_guide_or_none(self) -> str | None:
        style_guide = self._read_project_file().get("style_guide")
        return style_guide if isinstance(style_guide, str) else None

    def save_framing(self, framing: str) -> None:
        self._update_project_file(framing=framing)

    def load_framing_or_none(self) -> str | None:
        framing = self._read_project_file().get("framing")
        return framing if isinstance(framing, str) else None

    def save_model(self, model: str) -> None:
        self._update_project_file(model=model)

    def load_model_or_none(self) -> str | None:
        model = self._read_project_file().get("model")
        return model if isinstance(model, str) else None

    def record_run(self, stage: str, metadata: dict[str, object]) -> None:
        data = self._read_project_file()
        runs = data.setdefault("runs", [])
        if not isinstance(runs, list):
            raise ProjectStateError(f"corrupt {_PROJECT_FILE}: 'runs' is not a list")
        runs.append({"stage": stage, "timestamp": datetime.now(UTC).isoformat(), **metadata})
        self._write_project_file(data)

    def _update_project_file(self, **entries: object) -> None:
        data = self._read_project_file()
        data.update(entries)
        self._write_project_file(data)

    def _read_project_file(self) -> dict[str, object]:
        path = self._dir / _PROJECT_FILE
        if not path.is_file():
            return {}
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ProjectStateError(f"corrupt {_PROJECT_FILE}: expected a JSON object")
        return loaded

    def _write_project_file(self, data: dict[str, object]) -> None:
        path = self._dir / _PROJECT_FILE
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- status / lock ---------------------------------------------------------

    def status(self) -> ProjectStatus:
        return ProjectStatus(
            source_count=len(self._indexed_sources()),
            ref_count=len(self._indexed_refs()),
            style_guide=self.load_style_guide_or_none(),
            model=self.load_model_or_none(),
            result_emojis=self.list_results(),
        )

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Exclusive per-project lock; fails loudly if another process holds it."""
        with FileLock(str(self._dir / _LOCK_FILE), timeout=_LOCK_TIMEOUT_SECONDS):
            yield


def open_project(directory: str, *, create: bool) -> Project:
    """Open the project directory.

    create=True makes the directory (ingest); create=False fails loudly when it
    is missing, so read-only commands like `status` never mkdir a typo'd path.
    """
    path = Path(directory)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise ProjectStateError(f"project directory not found: {directory}")
    return Project(path)
