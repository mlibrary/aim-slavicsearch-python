"""Tests for report_bibs.reports.ReportSet."""
from pathlib import Path

from report_bibs.line_io import Counters
from report_bibs.reports import ReportSet


# ----- File creation ------------------------------------------------------

def test_open_creates_all_eight_files(tmp_path):
    outbase = str(tmp_path / 'run1')
    with ReportSet(outbase) as reports:
        pass
    expected = [
        '.log', '.marc',
        '_summary_rpt.tsv', '_match_rpt.tsv', '_near_match_rpt.tsv',
        '_no_match_rpt.tsv', '_not_found_rpt.tsv', '_toomany_rpt.tsv',
        '_review.txt',
    ]
    for suffix in expected:
        assert (tmp_path / f'run1{suffix}').exists(), f"missing {suffix}"


def test_tsv_headers_written_to_five_report_files(tmp_path):
    outbase = str(tmp_path / 'run2')
    with ReportSet(outbase) as reports:
        pass
    for name in ('_match_rpt', '_near_match_rpt', '_no_match_rpt',
                 '_not_found_rpt', '_toomany_rpt'):
        text = (tmp_path / f'run2{name}.tsv').read_text()
        first_line = text.splitlines()[0]
        # 32 columns
        assert len(first_line.split('\t')) == 32
        # Recognizable header
        assert first_line.startswith('Notes\tNumber\tArrival date')


def test_summary_and_log_have_no_tsv_header(tmp_path):
    outbase = str(tmp_path / 'run3')
    with ReportSet(outbase) as reports:
        pass
    assert (tmp_path / 'run3_summary_rpt.tsv').read_text() == ''
    assert (tmp_path / 'run3.log').read_text() == ''


# ----- Row writing --------------------------------------------------------

def _alma_info():
    return {
        'SYSNUM': '99189114973706381',
        'TITLE': 'Sample Title',
        'AUTHOR': 'Smith, John',
        'DATE': '2024.',
        'LANG': 'rus',
        'FMT': 'BK',
        'HAS_245H': 0,
        'ARRIVAL_DATE': '2026-02-13',
        'FUND': 'F1',
        'VENDOR': 'V1',
    }


def test_record_not_found_writes_alma_row(tmp_path):
    outbase = str(tmp_path / 'run4')
    with ReportSet(outbase) as reports:
        reports.record_not_found(_alma_info())
    lines = (tmp_path / 'run4_not_found_rpt.tsv').read_text().splitlines()
    assert len(lines) == 2  # header + one data row
    cells = lines[1].split('\t')
    assert len(cells) == 32
    # Excel-protection leading quote on Arrival date, MMSID, Alma pub date
    assert cells[2] == "'2026-02-13"
    assert cells[4] == "'99189114973706381"
    assert cells[5] == "ALMA"
    assert cells[9] == "'2024."
    # match type cell:
    assert cells[21] == "not found"


def test_record_toomany_writes_alma_row(tmp_path):
    outbase = str(tmp_path / 'run5')
    with ReportSet(outbase) as reports:
        reports.record_toomany(_alma_info())
    cells = (tmp_path / 'run5_toomany_rpt.tsv').read_text().splitlines()[1].split('\t')
    assert cells[21] == "too many matches"


def test_record_near_match_appends_separator(tmp_path):
    outbase = str(tmp_path / 'run6')
    rec_info = {
        'info_entries': [
            {
                'match_type': 'near match (Different edition)',
                'search': 'ISBN',
                'title_match': 'yes',
                'author_match': 'yes',
                'date_match': 'no',
                'has_245h': 0,
                'institutions': [''] * 3,
                'big_ten_institutions': [],
                'eym_cnt': 0,
                'rec_lang': 'rus',
                'oclc_country_code': 'ru ',
                'oclc_geo_code': 'e-ru---',
                'rec_oclc_num': '12345',
                'rec_fmt': 'BK',
                'rec_title': 'Sample Title /',
                'rec_author': 'Smith, John,',
                'rec_pub_date': '2023',
                'elvl': ' ',
                'rec_040_b': 'eng',
                'f050': '',
                'dlc': '',
                'pcc': '',
                'oclc_numbered_series': '',
            },
        ],
        'result_match_type': 'near match',
        'inst_count_list': '3',
        'eym_count_list': '0',
    }
    with ReportSet(outbase) as reports:
        reports.record_near_match(_alma_info(), rec_info)
    text = (tmp_path / 'run6_near_match_rpt.tsv').read_text()
    assert "'-------------------------------" in text
    # Verify the alma opener and the oclc row both appear
    lines = text.splitlines()
    assert lines[0].startswith('Notes')                  # header
    assert lines[1].split('\t')[5] == 'ALMA'             # alma row
    assert lines[2].split('\t')[5] == 'OCLC'             # oclc row
    assert lines[3] == "'-------------------------------"  # separator


# ----- Log and summary ---------------------------------------------------

def test_write_log_line_uses_counters_to_log_line(tmp_path):
    outbase = str(tmp_path / 'run7')
    counters = Counters()
    counters.set_sysnum('99')
    counters.increment('match_selected')
    with ReportSet(outbase) as reports:
        reports.write_log_line(counters)
    text = (tmp_path / 'run7.log').read_text()
    assert text.startswith('SYSNUM:99')
    assert 'match_selected:1' in text


def test_write_summary_emits_eight_lines_with_star_suffix(tmp_path):
    outbase = str(tmp_path / 'run8')
    counters = Counters()
    counters.increment('match_selected')
    counters.increment('tot_not_found')
    with ReportSet(outbase) as reports:
        reports.write_summary('20260527', counters, 5)
    lines = (tmp_path / 'run8_summary_rpt.tsv').read_text().splitlines()
    # 2 header lines + 6 counter lines == 8 total (matches Perl reference)
    assert len(lines) == 8
    assert lines[0].endswith('\t***')
    assert lines[1] == '****************************\t***'
    assert 'Alma records searched:\t5' in lines[2]
    assert 'OCLC record found, selected for Alma record:\t1' in lines[3]
    assert 'No OCLC record found for Alma record:\t1' in lines[7]


# ----- write_review -------------------------------------------------------

def test_write_review_one_line_per_call(tmp_path):
    outbase = str(tmp_path / 'run9')
    with ReportSet(outbase) as reports:
        reports.write_review('S1', '111', 'BK', '2024.', '2023.')
        reports.write_review('S2', '222', 'BK', '2025', '2024')
    text = (tmp_path / 'run9_review.txt').read_text()
    assert text == 'S1\t111\tBK\t2024.\t2023.\nS2\t222\tBK\t2025\t2024\n'
