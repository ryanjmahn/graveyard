from graveyard.models import Entry
from graveyard.search import search_entries


def entry(id, attempt="x", why_failed="y", created_at="2026-01-01T00:00:00+00:00", **fields):
    return Entry(id=id, attempt=attempt, why_failed=why_failed, created_at=created_at, **fields)


def ids(entries, query, **kwargs):
    return [e.id for e in search_entries(entries, query, **kwargs)]


def test_field_ranking_order():
    entries = [
        entry(1, error_snippet="numpy"),
        entry(2, why_failed="numpy"),
        entry(3, attempt="numpy"),
        entry(4, area="numpy"),
        entry(5, tags=["numpy"]),
    ]
    assert ids(entries, "numpy") == [5, 4, 3, 2, 1]


def test_case_insensitive():
    assert ids([entry(1, attempt="NumPy")], "NUMPY") == [1]
    assert ids([entry(1, tags=["NUMPY"])], "numpy") == [1]


def test_no_match_is_empty():
    assert ids([entry(1, attempt="numpy")], "torch") == []


def test_whole_word_beats_part_of_a_word_in_same_field():
    entries = [entry(1, attempt="pytorch upgrade"), entry(2, attempt="torch upgrade")]
    assert ids(entries, "torch") == [2, 1]


def test_part_of_a_word_matches_for_longer_terms():
    assert ids([entry(1, tags=["dependencies"])], "dep") == [1]


def test_short_terms_only_match_whole_words():
    entries = [entry(1, attempt="a hard decision"), entry(2, attempt="fails in ci")]
    assert ids(entries, "ci") == [2]


def test_more_words_matched_beats_one_strong_match():
    entries = [entry(1, tags=["numpy"]), entry(2, attempt="numpy broke torch")]
    assert ids(entries, "numpy torch") == [2, 1]


def test_stopwords_dont_match_everything():
    entries = [entry(1, attempt="numpy to the moon"), entry(2, attempt="went to the store")]
    assert ids(entries, "fix the numpy to") == [1]


def test_query_of_only_stopwords_still_searches():
    assert ids([entry(1, attempt="the thing"), entry(2, attempt="thing")], "the") == [1]


def test_punctuation_only_query_matches_nothing():
    assert ids([entry(1)], "!!!") == []


def test_ties_are_newest_first():
    entries = [
        entry(1, attempt="numpy", created_at="2026-01-01T00:00:00+00:00"),
        entry(2, attempt="numpy", created_at="2026-03-01T00:00:00+00:00"),
        entry(3, attempt="numpy", created_at="2026-02-01T00:00:00+00:00"),
    ]
    assert ids(entries, "numpy") == [2, 3, 1]


def test_note_is_not_searched():
    assert ids([entry(1, note="numpy")], "numpy") == []


def test_revived_entries_are_still_found():
    assert ids([entry(1, attempt="numpy", status="revived")], "numpy") == [1]


def test_area_filter():
    entries = [entry(1, attempt="numpy", area="src/api"), entry(2, attempt="numpy", area="deps")]
    assert ids(entries, "numpy", area="SRC") == [1]


def test_tags_filter_matches_any():
    entries = [
        entry(1, attempt="numpy", tags=["a"]),
        entry(2, attempt="numpy", tags=["B"]),
        entry(3, attempt="numpy", tags=["c"]),
        entry(4, attempt="numpy"),
    ]
    assert sorted(ids(entries, "numpy", tags=["a", "b"])) == [1, 2]
