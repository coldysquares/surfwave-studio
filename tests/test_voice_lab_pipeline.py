from src.voice_lab.ddsp_voice_lab.projects import slugify
from src.voice_lab.ddsp_voice_lab.pipeline import q


def test_slugify():
    assert slugify("Nick Voice 01") == "nick-voice-01"


def test_quote_escape():
    assert q("a'b") == "a\\'b"
