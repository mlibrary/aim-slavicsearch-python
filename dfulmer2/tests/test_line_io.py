"""Tests for report_bibs.line_io (KeyLineParser + Counters)."""
from report_bibs.line_io import Counters, KeyLineParser


# ----- KeyLineParser ------------------------------------------------------

def test_parse_basic_tab_delimited_line():
    line = "SYSNUM:99\tTITLE:Hello\tISBN:1234"
    assert KeyLineParser.parse(line) == {
        'SYSNUM': '99',
        'TITLE': 'Hello',
        'ISBN': '1234',
    }


def test_parse_preserves_colon_in_value():
    # Titles often contain colons; split on FIRST colon only
    line = "TITLE:Hello: World\tISBN:5678"
    parsed = KeyLineParser.parse(line)
    assert parsed['TITLE'] == 'Hello: World'
    assert parsed['ISBN'] == '5678'


def test_parse_handles_empty_value():
    line = "SYSNUM:99\tAUTHOR:\tTITLE:foo"
    assert KeyLineParser.parse(line) == {
        'SYSNUM': '99',
        'AUTHOR': '',
        'TITLE': 'foo',
    }


def test_parse_drops_field_with_no_key():
    # A bare ":value" or a stray tab won't introduce a None key
    line = ":no_key\tSYSNUM:99\t\t"
    assert KeyLineParser.parse(line) == {'SYSNUM': '99'}


def test_parse_returns_empty_dict_for_empty_line():
    assert KeyLineParser.parse('') == {}


# ----- Counters -----------------------------------------------------------

def test_counters_initial_values():
    c = Counters()
    assert c.get('match_selected') == 0
    assert c.get('tot_not_found') == 0
    assert c.get('selected', None) is None  # not yet present


def test_counters_increment_creates_missing_key():
    c = Counters()
    c.increment('selected')
    assert c.get('selected') == 1
    c.increment('selected')
    assert c.get('selected') == 2


def test_counters_to_log_line_uses_sorted_keys():
    c = Counters()
    c.set_sysnum('99189114973706381')
    c.increment('tot_not_found')
    line = c.to_log_line()
    # Keys must appear in alphabetical order
    parts = [p.split(':', 1)[0] for p in line.split('\t')]
    assert parts == sorted(parts)
    # And SYSNUM comes first (alphabetically, 'S' < 'm' lowercase... but
    # all the other keys are lowercase, so SYSNUM comes first)
    assert parts[0] == 'SYSNUM'


def test_counters_to_log_line_omits_selected_until_first_match():
    """`selected` is added lazily — log lines for records that miss must
    NOT contain the bare `selected:` key, matching Perl's behavior (see
    the first log line of slvr_20260527testfile51.log: tot_not_found
    increments but no `selected` key is present).
    """
    c = Counters()
    c.set_sysnum('X')
    c.increment('tot_not_found')
    line = c.to_log_line()
    # The other counter names end in `_selected`; we want to confirm there's
    # no standalone `selected:` token (preceded by tab, at the front).
    keys = [pair.split(':', 1)[0] for pair in line.split('\t')]
    assert 'selected' not in keys


def test_counters_to_log_line_includes_selected_after_increment():
    c = Counters()
    c.set_sysnum('X')
    c.increment('match_selected')
    c.increment('selected')
    line = c.to_log_line()
    assert 'selected:1' in line
