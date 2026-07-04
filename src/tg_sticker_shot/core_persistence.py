"""All filesystem access for project directories lives here.

Only this module imports pathlib. The API speaks domain terms (references,
samples, results, chosen style) and hands out bytes/str, never Path objects.

Project directory layout (flat, prefixed files):
    reference_<n>.png
    sample_<style>_<n>.png
    result_<emoji>.png
    project.json          (chosen style + run metadata)
    .shot.lock            (inter-process lock)
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

_PROJECT_FILE = "project.json"
_LOCK_FILE = ".shot.lock"
_LOCK_TIMEOUT_SECONDS = 10


class ProjectStateError(Exception):
    """The project directory is not in the state an operation requires."""


@dataclass(frozen=True)
class ProjectStatus:
    reference_count: int
    samples_per_style: dict[str, int]
    chosen_style: str | None
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
        index = len(self._reference_paths()) + 1
        name = f"reference_{index}.png"
        (self._dir / name).write_bytes(source_path.read_bytes())
        return name

    def load_references(self) -> list[bytes]:
        paths = self._reference_paths()
        if not paths:
            raise ProjectStateError(
                f"no reference images in project '{self._dir}' — run `shot ingest` first"
            )
        return [p.read_bytes() for p in paths]

    def _reference_paths(self) -> list[Path]:
        return sorted(self._dir.glob("reference_*.png"), key=_trailing_index)

    # -- style samples -------------------------------------------------------

    def save_sample(self, style: str, index: int, data: bytes) -> str:
        name = f"sample_{style}_{index}.png"
        (self._dir / name).write_bytes(data)
        return name

    def load_samples(self, style: str) -> list[bytes]:
        paths = sorted(self._dir.glob(f"sample_{style}_*.png"), key=_trailing_index)
        return [p.read_bytes() for p in paths]

    def list_sample_styles(self) -> list[str]:
        styles = {p.stem.removeprefix("sample_").rsplit("_", 1)[0] for p in self._sample_paths()}
        return sorted(styles)

    def _sample_paths(self) -> list[Path]:
        return sorted(self._dir.glob("sample_*.png"))

    # -- results -------------------------------------------------------------

    def save_result(self, emoji: str, data: bytes) -> str:
        name = f"result_{emoji}.png"
        (self._dir / name).write_bytes(data)
        return name

    def has_result(self, emoji: str) -> bool:
        return (self._dir / f"result_{emoji}.png").is_file()

    def list_results(self) -> list[str]:
        return sorted(p.stem.removeprefix("result_") for p in self._dir.glob("result_*.png"))

    # -- chosen style / run metadata (project.json) ----------------------------

    def save_chosen_style(self, style: str) -> None:
        self._update_project_file(chosen_style=style)

    def load_chosen_style(self) -> str:
        style = self._read_project_file().get("chosen_style")
        if not isinstance(style, str):
            raise ProjectStateError(
                f"no style chosen in project '{self._dir}' — run `shot select` first"
            )
        return style

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
        chosen = self._read_project_file().get("chosen_style")
        return ProjectStatus(
            reference_count=len(self._reference_paths()),
            samples_per_style={
                style: sum(1 for _ in self._dir.glob(f"sample_{style}_*.png"))
                for style in self.list_sample_styles()
            },
            chosen_style=chosen if isinstance(chosen, str) else None,
            result_emojis=self.list_results(),
        )

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Exclusive per-project lock; fails loudly if another process holds it."""
        with FileLock(str(self._dir / _LOCK_FILE), timeout=_LOCK_TIMEOUT_SECONDS):
            yield


def open_project(directory: str) -> Project:
    """Open (creating if needed) the project directory."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return Project(path)


def _trailing_index(path: Path) -> int:
    """Numeric sort key for names like reference_10.png (avoids 1,10,2 ordering)."""
    return int(path.stem.rsplit("_", 1)[1])
