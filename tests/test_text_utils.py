import pytest

from utils.text_utils import clean_text, simple_match_score


def test_clean_text_basic():
    assert clean_text("Hello, WORLD!") == "hello world"
    assert clean_text("  Multiple   spaces\nand\ttabs ") == "multiple spaces and tabs"


def test_simple_match_score_full_and_partial():
    text = "We build data pipelines using Python and SQL"
    assert simple_match_score(text, "python") == pytest.approx(1.0)
    # two-word query, one common -> score 0.5
    assert simple_match_score(text, "python sql") == pytest.approx(1.0)
    # no overlap
    assert simple_match_score(text, "javascript") == pytest.approx(0.0)


def test_simple_match_score_empty_query():
    assert simple_match_score("some text", "") == pytest.approx(0.0)
