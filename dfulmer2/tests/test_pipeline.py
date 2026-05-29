"""Tests for report_bibs.pipeline.Pipeline.

These tests exercise the full pipeline against a FakeWorldCatClient. They
write input lines to a temp directory, run the pipeline, and inspect the
output files. No network calls.
"""
import io
import re
from pathlib import Path

from report_bibs.line_io import Counters
from report_bibs.pipeline import Pipeline
from report_bibs.reports import ReportSet


# ----- Fakes scoped to this file -----------------------------------------

class FakeClient:
    """In-memory stand-in for WorldCatClient.

    Tests pre-populate `responses` with the (numrec, [oclc_numbers]) tuples
    that should come back from brief_search, and `marc_records` with the
    pymarc.Records that fetch_marc should return for given OCLC numbers.
    """

    max_hits = 50

    def __init__(self):
        self.responses = {}        # (search_type, normalized_term) → (numrec, [ocns])
        self.marc_records = {}     # oclcNumber → pymarc.Record
        self.holdings = {}         # oclcNumber → count (legacy fetch_holdings_count)
        self.holdings_list = {}    # oclcNumber → [oclc_symbols]
        self.closed = False

    def brief_search(self, search_type, normalized_term):
        key = (search_type, str(normalized_term))
        return self.responses.get(key, (0, []))

    def fetch_marc(self, oclc_number):
        return self.marc_records.get(str(oclc_number))

    def fetch_holdings_count(self, oclc_number):
        return self.holdings.get(str(oclc_number), 0)

    def fetch_holdings_list(self, oclc_number):
        return list(self.holdings_list.get(str(oclc_number), []))

    def connect(self):
        pass

    def reconnect(self):
        pass

    def close(self):
        self.closed = True


def _build_marc_record(ocn='12345', title='Sample Title /',
                       author='Smith, John,', date='2024.',
                       lang='rus', country='ru ', leader_lev='m'):
    """Construct a pymarc.Record that will pass the field checks."""
    from pymarc import Field, Record, Subfield

    rec = Record()
    rec.leader = f'00000nam a2200000{leader_lev}a 4500'

    rec.add_ordered_field(Field(tag='001', data=ocn))
    # 008 must have a blank at position 23 and language at 35-37
    f008 = '240101s' + '2024    ' + country + ' ' + ' ' * (35 - 19) + lang + '   '
    # Pad / fix length to be safe
    if len(f008) < 40:
        f008 = (f008 + ' ' * 40)[:40]
    # Ensure position 23 is blank
    f008 = f008[:23] + ' ' + f008[24:]
    # Ensure positions 15-17 are country, 35-37 are lang
    f008 = f008[:15] + country + f008[18:35] + lang + f008[38:]
    rec.add_ordered_field(Field(tag='008', data=f008))

    rec.add_ordered_field(Field(
        tag='245', indicators=['1', '0'],
        subfields=[Subfield(code='a', value=title)],
    ))
    rec.add_ordered_field(Field(
        tag='100', indicators=['1', ' '],
        subfields=[Subfield(code='a', value=author)],
    ))
    rec.add_ordered_field(Field(
        tag='260', indicators=[' ', ' '],
        subfields=[Subfield(code='c', value=date)],
    ))
    return rec


def _write_input_file(tmp_path, lines):
    p = tmp_path / 'input.txt'
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return p


# ----- Helpers for capturing output --------------------------------------

def _run(tmp_path, *, input_lines, client_setup):
    """Run the pipeline against the given lines and configured client.

    Returns (outbase, stdout_text, stderr_text) so tests can inspect both
    the files and the terminal output.
    """
    client = FakeClient()
    client_setup(client)
    infile = _write_input_file(tmp_path, input_lines)
    outbase = str(tmp_path / 'out')
    stdout = io.StringIO()
    stderr = io.StringIO()
    with ReportSet(outbase) as reports:
        counters = Counters()
        pipeline = Pipeline(client, reports, counters, stdout=stdout, stderr=stderr)
        pipeline.run(str(infile))
    return outbase, stdout.getvalue(), stderr.getvalue()


# ----- Tests --------------------------------------------------------------

def test_one_record_matched(tmp_path):
    """Title + author + date all match → matched bucket."""
    rec = _build_marc_record(
        ocn='12345',
        title='Sample Title for Testing the Pipeline /',
        author='Smith, John,',
        date='2024.',
    )

    def setup(c):
        # Norm of '9785449816429' is itself; norm of TITLE is the lowercased
        # stopword-stripped form; we don't need to match exactly — just put
        # the response under the ISBN key which is the one we'll exercise.
        c.responses[('ISBN', '9785449816429')] = (1, ['12345'])
        # And the title-search response for completeness (in case it fires).
        c.marc_records['12345'] = rec
        # Three holdings: EYM (counts for the EYM column), UIU (Big Ten),
        # YUS (neither). Tests the Big Ten filter + EYM count + symbol join.
        c.holdings_list['12345'] = ['EYM', 'UIU', 'YUS']

    line = (
        'SYSNUM:111\tFMT:BK\tLANG:rus\tTITLE:Sample Title for Testing the Pipeline /\t'
        'AUTHOR:Smith, John\tAUTHOR_TAG:100\tDATE:2024.\tTITLE_H:\tIMPRINT:Pub\t'
        'ARRIVAL_DATE:2026-02-13\tISBN:9785449816429'
    )
    outbase, stdout, stderr = _run(
        tmp_path, input_lines=[line], client_setup=setup,
    )
    # Verify it landed in match_rpt
    match_text = Path(outbase + '_match_rpt.tsv').read_text()
    lines = match_text.splitlines()
    assert len(lines) >= 2  # header + 1 OCLC row (record_match has no alma opener)
    cells = lines[1].split('\t')
    assert cells[5] == 'OCLC'
    assert cells[6] == "'12345"
    assert 'matched' in cells[21]
    # Holdings-derived columns now populated (was empty before the fix).
    assert cells[3] == '1'                # EYM column = count of EYM
    assert cells[19] == '3'               # # of Institutions
    assert cells[20] == 'EYM; UIU; YUS'   # Institutions
    assert cells[26] == 'UIU'             # Big10 OCLC inst code (only UIU)
    # Log line written
    log = Path(outbase + '.log').read_text()
    assert log.startswith('SYSNUM:111')
    assert 'match_selected:1' in log


def test_one_record_not_found_zero_hits(tmp_path):
    def setup(c):
        # No responses configured -> brief_search returns (0, [])
        pass

    line = (
        'SYSNUM:222\tFMT:BK\tLANG:rus\tTITLE:Unmatched\tAUTHOR:\tAUTHOR_TAG:\t'
        'DATE:2024.\tTITLE_H:\tIMPRINT:\tARRIVAL_DATE:2026-02-13\tISBN:0000'
    )
    outbase, stdout, stderr = _run(
        tmp_path, input_lines=[line], client_setup=setup,
    )
    nf = Path(outbase + '_not_found_rpt.tsv').read_text()
    lines = nf.splitlines()
    assert len(lines) == 2  # header + 1 alma row
    assert lines[1].split('\t')[21] == 'not found'
    # And the terminal output mentions "no records for any search terms"
    assert '222(1): no records for any search terms' in stdout


def test_one_record_too_many(tmp_path):
    def setup(c):
        # numberOfRecords > max_hits -> too-many
        c.responses[('ISBN', '5555555555')] = (99, [])

    line = (
        'SYSNUM:333\tFMT:BK\tLANG:rus\tTITLE:Common Word\tAUTHOR:\tAUTHOR_TAG:\t'
        'DATE:2024.\tTITLE_H:\tIMPRINT:\tARRIVAL_DATE:2026-02-13\tISBN:5555555555'
    )
    outbase, stdout, stderr = _run(
        tmp_path, input_lines=[line], client_setup=setup,
    )
    tm = Path(outbase + '_toomany_rpt.tsv').read_text()
    lines = tm.splitlines()
    assert len(lines) == 2
    assert lines[1].split('\t')[21] == 'too many matches'
    assert 'too many records found for ISBN (99)' in stdout


def test_terminal_summary_includes_separator_and_counts(tmp_path):
    def setup(c):
        pass  # all records will be not_found

    lines = []
    for i in range(3):
        lines.append(
            f'SYSNUM:{1000+i}\tFMT:BK\tLANG:rus\tTITLE:No Match {i}\tAUTHOR:\t'
            f'AUTHOR_TAG:\tDATE:2024.\tTITLE_H:\tIMPRINT:\t'
            f'ARRIVAL_DATE:2026-02-13\tISBN:000{i}'
        )
    outbase, stdout, stderr = _run(
        tmp_path, input_lines=lines, client_setup=setup,
    )
    # The summary block
    assert "'==============================" in stdout
    assert '3 records read' in stdout
    # Per-search-type counts (TITLE always fires; ISBN fires when present)
    assert re.search(r'\tISBN: \d+', stdout)


def test_summary_report_file_contains_counts(tmp_path):
    def setup(c):
        pass

    line = (
        'SYSNUM:999\tFMT:BK\tLANG:rus\tTITLE:X\tAUTHOR:\tAUTHOR_TAG:\t'
        'DATE:2024.\tTITLE_H:\tIMPRINT:\tARRIVAL_DATE:2026-02-13\tISBN:0'
    )
    outbase, stdout, stderr = _run(
        tmp_path, input_lines=[line], client_setup=setup,
    )
    text = Path(outbase + '_summary_rpt.tsv').read_text()
    summary_lines = text.splitlines()
    assert len(summary_lines) == 8
    assert summary_lines[0].endswith('\t***')
    assert 'Alma records searched:\t1' in summary_lines[2]
    assert 'No OCLC record found for Alma record:\t1' in summary_lines[7]
