"""Load bundled styles.yaml / emotions.yaml. Styles and emotions are data, not code."""

from dataclasses import dataclass
from importlib import resources

import yaml


class StyleDataError(Exception):
    """A bundled yaml file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Style:
    name: str
    prompt: str


@dataclass(frozen=True)
class Emotion:
    name: str
    emoji: str
    prompt_fragment: str


def load_styles() -> dict[str, Style]:
    """Style name → Style, from the bundled styles.yaml."""
    styles: dict[str, Style] = {}
    for entry in _load_entries("styles.yaml", required_keys=("name", "prompt")):
        style = Style(name=entry["name"], prompt=entry["prompt"])
        if style.name in styles:
            raise StyleDataError(f"styles.yaml: duplicate style name '{style.name}'")
        styles[style.name] = style
    return styles


def load_emotions() -> list[Emotion]:
    """All emotions from the bundled emotions.yaml, in file order."""
    emotions: list[Emotion] = []
    seen: set[str] = set()
    for entry in _load_entries("emotions.yaml", required_keys=("name", "emoji", "prompt_fragment")):
        emotion = Emotion(
            name=entry["name"], emoji=entry["emoji"], prompt_fragment=entry["prompt_fragment"]
        )
        for key in (emotion.name, emotion.emoji):
            if key in seen:
                raise StyleDataError(f"emotions.yaml: duplicate entry '{key}'")
            seen.add(key)
        emotions.append(emotion)
    return emotions


def _load_entries(filename: str, required_keys: tuple[str, ...]) -> list[dict[str, str]]:
    text = resources.files("tg_sticker_shot").joinpath(filename).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, list) or not loaded:
        raise StyleDataError(f"{filename}: expected a non-empty list of entries")
    entries: list[dict[str, str]] = []
    for entry in loaded:
        if not isinstance(entry, dict):
            raise StyleDataError(f"{filename}: expected mapping entries, got {entry!r}")
        for key in required_keys:
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise StyleDataError(f"{filename}: entry {entry!r} needs non-empty '{key}'")
        entries.append({key: entry[key] for key in required_keys})
    return entries
