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
_SAMPLE_RE = re.compile(r"sample_(.+)_(\d+)\.png")


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

    def save_sample(self, style: str, index: int, data: bytes) -> str:
        name = f"sample_{style}_{index}.png"
        (self._dir / name).write_bytes(data)
        return name

    def load_samples(self, style: str) -> list[bytes]:
        return [
            path.read_bytes()
            for sample_style, _, path in self._indexed_samples()
            if sample_style == style
        ]

    def has_sample(self, style: str, index: int) -> bool:
        return (self._dir / f"sample_{style}_{index}.png").is_file()

    def list_sample_styles(self) -> list[str]:
        return sorted({style for style, _, _ in self._indexed_samples()})

    def _indexed_samples(self) -> list[tuple[str, int, Path]]:
        """All samples as (style, index, path), sorted by style then index.

        Parses full filenames (never glob-prefix matches) so a style named
        'chibi' can't pick up samples of a style named 'chibi_v2'.
        """
        entries: list[tuple[str, int, Path]] = []
        for path in self._dir.glob("sample_*.png"):
            match = _SAMPLE_RE.fullmatch(path.name)
            if match is None:
                raise ProjectStateError(
                    f"unexpected file '{path.name}' in project '{self._dir}' — "
                    "expected sample_<style>_<n>.png"
                )
            entries.append((match.group(1), int(match.group(2)), path))
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
        samples_per_style: dict[str, int] = {}
        for style, _, _ in self._indexed_samples():
            samples_per_style[style] = samples_per_style.get(style, 0) + 1
        return ProjectStatus(
            reference_count=len(self._indexed_references()),
            samples_per_style=samples_per_style,
            chosen_style=chosen if isinstance(chosen, str) else None,
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
