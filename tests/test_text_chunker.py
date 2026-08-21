import pytest

from studygraph.text_chunker import chunk_text


def test_chunk_text_returns_empty_list_for_blank_text() -> None:
    assert chunk_text(" \n\t ") == []


def test_chunk_text_normalizes_whitespace() -> None:
    chunks = chunk_text("First   paragraph.\n\nSecond paragraph.")

    assert len(chunks) == 1
    assert chunks[0].position == 0
    assert chunks[0].text == "First paragraph. Second paragraph."
    assert chunks[0].character_count == 34


def test_chunk_text_splits_at_word_boundaries_with_overlap() -> None:
    chunks = chunk_text(
        "alpha beta gamma delta epsilon",
        max_characters=16,
        overlap_characters=5,
    )

    assert [chunk.position for chunk in chunks] == [0, 1, 2]
    assert [chunk.text for chunk in chunks] == [
        "alpha beta gamma",
        "gamma delta",
        "delta epsilon",
    ]
    assert all(chunk.character_count <= 16 for chunk in chunks)


def test_chunk_text_rejects_invalid_chunk_size() -> None:
    with pytest.raises(ValueError, match="max_characters"):
        chunk_text("text", max_characters=0)


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_characters"):
        chunk_text("text", max_characters=10, overlap_characters=10)
