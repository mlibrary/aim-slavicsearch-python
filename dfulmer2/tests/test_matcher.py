"""Tests for report_bibs.matcher (MatchTypeTable + Matcher)."""
from report_bibs.matcher import Matcher, MatchTypeTable


# ----- MatchTypeTable -----------------------------------------------------

def test_lookup_returns_matched_for_all_yes():
    # First row: any search type, yes/yes/yes -> 'matched'
    assert MatchTypeTable.lookup('OCLC', 'yes', 'yes', 'yes') == 'matched'
    assert MatchTypeTable.lookup('ISBN', 'yes', 'yes', 'yes') == 'matched'


def test_lookup_returns_matched_when_alma_has_no_100():
    # Second row: any search, yes/no 100/yes -> 'matched'
    assert MatchTypeTable.lookup('ISBN', 'yes', 'no 100', 'yes') == 'matched'


def test_lookup_returns_near_match_for_near_author_date():
    assert MatchTypeTable.lookup('TITLE', 'near', 'yes', 'yes') \
        == 'near match (near/author/date)'


def test_lookup_returns_near_match_for_different_edition():
    # yes title, yes author, NO date -> Different edition
    assert MatchTypeTable.lookup('ISBN', 'yes', 'yes', 'no') \
        == 'near match (Different edition)'


def test_lookup_returns_near_match_title_date():
    # yes title, no author, yes date -> Title/Date
    assert MatchTypeTable.lookup('OCLC', 'yes', 'no', 'yes') \
        == 'near match (Title/Date)'


def test_lookup_isbn_specific_row_isbn_author_date():
    # ISBN row: no title, yes author, yes date -> ISBN/author/date
    assert MatchTypeTable.lookup('ISBN', 'no', 'yes', 'yes') \
        == 'near match (ISBN/author/date)'


def test_lookup_isbn_specific_row_doesnt_apply_to_other_searches():
    # Same combo but with TITLE search -> not the ISBN-specific row
    # ('TITLE', 'no', 'yes', 'yes') falls to the 'exclude' row instead.
    assert MatchTypeTable.lookup('TITLE', 'no', 'yes', 'yes') == 'exclude'


def test_lookup_returns_exclude_for_no_no_no():
    assert MatchTypeTable.lookup('ISBN', 'no', 'no', 'no') == 'exclude'


def test_lookup_returns_exclude_for_no_yes_no():
    assert MatchTypeTable.lookup('OCLC', 'no', 'yes', 'no') == 'exclude'


def test_lookup_falls_through_to_exclude():
    # An impossible combination still returns 'exclude' rather than crashing
    assert MatchTypeTable.lookup('UNKNOWN', 'maybe', '?', '?') == 'exclude'


# ----- Matcher.field_match -----------------------------------------------

def test_field_match_equality():
    assert Matcher.field_match('a', 'a') is True
    assert Matcher.field_match('a', 'b') is False
    assert Matcher.field_match('', '') is True


# ----- Matcher.field_match_word ------------------------------------------

def test_field_match_word_full_match_returns_yes():
    assert Matcher.field_match_word('a b c d e', 'a b c d e', 5) == 'yes'


def test_field_match_word_partial_match_returns_near():
    # 4 out of 5 positions match -> > 2.5 → 'near'
    assert Matcher.field_match_word('a b c d e', 'a b c d x', 5) == 'near'


def test_field_match_word_low_overlap_returns_no():
    assert Matcher.field_match_word('a b c d e', 'x y z w v', 5) == 'no'


def test_field_match_word_truncates_limit_for_short_terms():
    # Only 2 words in term_1, so limit is clamped to 2; both match -> yes
    assert Matcher.field_match_word('a b', 'a b', 5) == 'yes'


def test_field_match_word_handles_empty_term_2():
    # When term_2 is empty, every position misses; length 5, no matches -> 'no'
    assert Matcher.field_match_word('a b c d e', '', 5) == 'no'
