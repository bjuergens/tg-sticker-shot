from tg_sticker_shot.core_styles import load_emotions, load_styles


def test_styles_load_and_are_well_formed() -> None:
    styles = load_styles()
    assert len(styles) >= 2
    for name, style in styles.items():
        assert style.name == name
        assert style.prompt.strip()


def test_emotions_load_and_are_well_formed() -> None:
    emotions = load_emotions()
    assert 10 <= len(emotions) <= 20
    for emotion in emotions:
        assert emotion.name.strip()
        assert emotion.emoji.strip()
        assert emotion.prompt_fragment.strip()


def test_emotion_emojis_are_unique() -> None:
    emojis = [emotion.emoji for emotion in load_emotions()]
    assert len(emojis) == len(set(emojis))
