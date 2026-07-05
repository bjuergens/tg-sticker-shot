"""Load the bundled emotions.yaml. Emotions are data, not code."""

from dataclasses import dataclass
from importlib import resources

import yaml


class EmotionDataError(Exception):
    """The bundled emotions.yaml is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Emotion:
    name: str
    emoji: str
    prompt_fragment: str


def load_emotions() -> list[Emotion]:
    """All emotions from the bundled emotions.yaml, in file order."""
    text = resources.files("tg_sticker_shot").joinpath("emotions.yaml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, list) or not loaded:
        raise EmotionDataError("emotions.yaml: expected a non-empty list of entries")
    emotions: list[Emotion] = []
    seen: set[str] = set()
    for entry in loaded:
        if not isinstance(entry, dict):
            raise EmotionDataError(f"emotions.yaml: expected mapping entries, got {entry!r}")
        for key in ("name", "emoji", "prompt_fragment"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise EmotionDataError(f"emotions.yaml: entry {entry!r} needs non-empty '{key}'")
        emotion = Emotion(
            name=entry["name"], emoji=entry["emoji"], prompt_fragment=entry["prompt_fragment"]
        )
        for key in (emotion.name, emotion.emoji):
            if key in seen:
                raise EmotionDataError(f"emotions.yaml: duplicate entry '{key}'")
            seen.add(key)
        emotions.append(emotion)
    return emotions
