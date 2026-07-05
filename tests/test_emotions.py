from tg_sticker_shot.core_emotions import load_emotions


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
