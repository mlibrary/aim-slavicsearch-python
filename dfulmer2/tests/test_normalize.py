"""Tests for report_bibs.normalize.Normalizer."""
import pytest

from report_bibs.normalize import Normalizer


# ----- char_norm_unicode --------------------------------------------------

def test_char_norm_unicode_strips_combining_marks():
    # café → cafe (combining acute is stripped by NFKD+\p{M})
    assert Normalizer.char_norm_unicode('café') == 'cafe'


def test_char_norm_unicode_maps_l_with_stroke():
    assert Normalizer.char_norm_unicode('słownik') == 'slownik'


def test_char_norm_unicode_maps_d_with_stroke():
    # Perl only maps lowercase đ (U+0111); uppercase Đ stays as-is, matching
    # slvr_report.pl line 682 (`s/\x{111}/d/g;` — no uppercase substitution).
    assert Normalizer.char_norm_unicode('đorđe') == 'dorde'


def test_char_norm_unicode_passes_ascii_through():
    assert Normalizer.char_norm_unicode('hello') == 'hello'


# ----- title --------------------------------------------------------------

def test_title_lowercases_and_drops_stopwords():
    assert Normalizer.title('The Cat & The Hat /') == 'cat hat'


def test_title_strips_punctuation_and_diacritics():
    assert Normalizer.title('Café: A Novel?') == 'cafe novel'


def test_title_keeps_words_not_in_stopword_list():
    # 'tale' / 'love' aren't stopwords; 'a' / 'of' are
    assert Normalizer.title('A tale of love') == 'tale love'


# ----- author -------------------------------------------------------------

def test_author_with_100_tag_truncates_to_last_first_initial():
    # Comma + first-initial extraction, then comma stripped by punct removal
    assert Normalizer.author('Smith, John Adam', '100') == 'smith j'


def test_author_with_100_tag_handles_short_first_name():
    assert Normalizer.author('Smith, J. A.', '100') == 'smith j'


def test_author_without_100_tag_keeps_full_name():
    assert Normalizer.author('Smith, John Adam', '110') == 'smith john adam'


def test_author_no_comma_no_truncation():
    assert Normalizer.author('Anonymous', '100') == 'anonymous'


# ----- date ---------------------------------------------------------------

def test_date_extracts_first_four_digit_year():
    assert Normalizer.date('2024.') == '2024'
    assert Normalizer.date('1999-2001') == '1999'
    assert Normalizer.date('  2024  ') == '2024'


def test_date_falls_back_to_digits_and_u():
    # No 4-digit run, so the fallback keeps digits, 'u', and '-'
    assert Normalizer.date('uuuu') == 'uuuu'
    assert Normalizer.date('199u') == '199u'


# ----- ISBN / ISSN --------------------------------------------------------

def test_isbn_strips_dashes_spaces_apostrophes():
    assert Normalizer.isbn("978-1-234-56789-0") == '9781234567890'
    assert Normalizer.isbn("978 1234 56789 0") == '9781234567890'
    assert Normalizer.isbn("978'1'234'56789'0") == '9781234567890'


def test_isbn_lowercases_x_check_digit():
    assert Normalizer.isbn('123456789X') == '123456789x'


def test_issn_is_alias_of_isbn():
    assert Normalizer.issn('1234-5678') == '12345678'


# ----- OCLC ---------------------------------------------------------------

def test_oclc_strips_prefix_and_returns_int():
    assert Normalizer.oclc('ocm00012345') == 12345
    assert Normalizer.oclc('ocn1234567890') == 1234567890


def test_oclc_returns_zero_when_no_digits():
    assert Normalizer.oclc('') == 0
    assert Normalizer.oclc('not a number') == 0


# ----- LCCN ---------------------------------------------------------------

def test_lccn_extracts_digit_run_as_string():
    assert Normalizer.lccn('lccn 12345') == '12345'
    assert Normalizer.lccn('no digits') == ''


# ----- for_type dispatch --------------------------------------------------

def test_for_type_dispatches_to_correct_method():
    assert Normalizer.for_type('978-1-234-56789-0', 'ISBN') == '9781234567890'
    assert Normalizer.for_type('2024.', 'DATE') == '2024'
    assert Normalizer.for_type('Smith, John Adam', 'AUTHOR', '100') == 'smith j'
    assert Normalizer.for_type('The Cat & The Hat /', 'TITLE') == 'cat hat'
    assert Normalizer.for_type('ocm00012345', 'OCLC') == 12345


def test_for_type_raises_on_unknown_type():
    with pytest.raises(ValueError):
        Normalizer.for_type('foo', 'UNKNOWN')
