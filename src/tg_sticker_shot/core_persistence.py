"""All filesystem access for project directories lives here.

Only this module imports pathlib. The API speaks domain terms (references,
samples, results, chosen style) and hands out bytes/str, never Path objects.

Project directory layout (flat, prefixed files):
    reference_<n>.png
    sample_<n>.png
    result_<emoji>.png
    project.json          (style guide + run metadata)
    .shot.lock            (inter-process lock)
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

# Strict filename patterns: anything matching the glob prefix but not the full
# pattern (e.g. a stray reference_backup.png) is an error, not silently ignored.
_REFERENCE_RE = re.compile(r"reference_(\d+)\.png")
_SAMPLE_RE = re.compile(r"sample_(\d+)\.png")


class ProjectStateError(Exception):
    """The project directory is not in the state an operation requires."""


@dataclass(frozen=True)
class ProjectStatus:
    reference_count: int
    sample_count: int
    style_guide: str | None
    result_emojis: list[str]


@dataclass
class Project:
    """Handle to one project directory. Create via open_project()."""

    _dir: Path

    # -- references ----------------------------------------------------------

    def add_reference_from_file(self, source: str) -> str:
        """Copy an external image file in as the next reference_<n>.png."""
        source_path = Path(source)
        if not source_path.is_file():
            raise ProjectStateError(f"reference image not found: {source}")
        references = self._indexed_references()
        index = references[-1][0] + 1 if references else 1  # max + 1, gaps never overwrite
        name = f"reference_{index}.png"
        (self._dir / name).write_bytes(source_path.read_bytes())
        return name

    def load_references(self) -> list[bytes]:
        references = self._indexed_references()
        if not references:
            raise ProjectStateError(
                f"no reference images in project '{self._dir}' — run `shot ingest` first"
            )
        return [path.read_bytes() for _, path in references]

    def _indexed_references(self) -> list[tuple[int, Path]]:
        entries: list[tuple[int, Path]] = []
        for path in self._dir.glob("reference_*.png"):
            match = _REFERENCE_RE.fullmatch(path.name)
            if match is None:
                raise ProjectStateError(
                    f"unexpected file '{path.name}' in project '{self._dir}' — "
                    "expected reference_<n>.png"
                )
            entries.append((int(match.group(1)), path))
        return sorted(entries)

    # -- style samples -------------------------------------------------------

    def save_sample(self, index: int, data: bytes) -> str:
        name = f"sample_{index}.png"
        (self._dir / name).write_bytes(data)
        return name

    def load_samples(self) -> list[bytes]:
        return [path.read_bytes() for _, path in self._indexed_samples()]

    def has_sample(self, index: int) -> bool:
        return (self._dir / f"sample_{index}.png").is_file()

    def _indexed_samples(self) -> list[tuple[int, Path]]:
        entries: list[tuple[int, Path]] = []
        for path in self._dir.glob("sample_*.png"):
            match = _SAMPLE_RE.fullmatch(path.name)
            if match is None:
                raise ProjectStateError(
                    f"unexpected file '{path.name}' in project '{self._dir}' — "
                    "expected sample_<n>.png"
                )
            entries.append((int(match.group(1)), path))
        return sorted(entries)

    # -- results -------------------------------------------------------------

    def save_result(self, emoji: str, data: bytes) -> str:
        name = f"result_{emoji}.png"
        (self._dir / name).write_bytes(data)
        return name

    def has_result(self, emoji: str) -> bool:
        return (self._dir / f"result_{emoji}.png").is_file()

    def list_results(self) -> list[str]:
        return sorted(p.stem.removeprefix("result_") for p in self._dir.glob("result_*.png"))

    # -- style guide / run metadata (project.json) -----------------------------

    def save_style_guide(self, style_guide: str) -> None:
        self._update_project_file(style_guide=style_guide)

    def load_style_guide_or_none(self) -> str | None:
        style_guide = self._read_project_file().get("style_guide")
        return style_guide if isinstance(style_guide, str) else None

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
            reference_count=len(self._indexed_references()),
            sample_count=len(self._indexed_samples()),
            style_guide=self.load_style_guide_or_none(),
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
