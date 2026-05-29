"""Output-file management for the report stage.

`ReportSet` owns the eight output files for one run, knows the 32-column
TSV header, and knows how to write every row format. It is a context
manager — use `with ReportSet(outbase) as reports: ...` and the file
handles are flushed and closed on exit.

The class replaces the standalone print_* functions in slvr_report.py
(lines 402-525). The Excel-protection leading single quote is applied
to exactly the columns Perl protects, no more and no less.
"""
from datetime import datetime


def _v(value):
    """Coerce None/missing to '' for clean tab-delimited output."""
    return '' if value is None else str(value)


class ReportSet:
    """Owns and writes to the eight output files for one run."""

    # The 32-column TSV header (slvr_report.pl 846-882).
    HEADER_COLUMNS = [
        "Notes", "Number", "Arrival date", "EYM", "Alma MMSID", "record source",
        "OCLC number", "Title", "Author", "Alma pub date", "OCLC pub date",
        "008 Language", "Recfmt", "has_245h", "DLC", "PCC", "OCLC Elvl",
        "OCLC 1st 050", "040 b", "# of Institutions", "Institutions",
        "match type", "searched on", "title match", "author match", "date match",
        "Big10 OCLC inst code", "OCLC numbered series", "Alma fund",
        "Alma vendor", "OCLC country code", "OCLC geo code",
    ]

    # Filename suffix per logical handle.
    SUFFIXES = {
        'log':        '.log',
        'marc':       '.marc',
        'summary':    '_summary_rpt.tsv',
        'match':      '_match_rpt.tsv',
        'near_match': '_near_match_rpt.tsv',
        'no_match':   '_no_match_rpt.tsv',
        'not_found':  '_not_found_rpt.tsv',
        'toomany':    '_toomany_rpt.tsv',
        'review':     '_review.txt',
    }

    # TSV reports that need the 32-column header row.
    TSV_REPORTS = ('match', 'near_match', 'no_match', 'not_found', 'toomany')

    def __init__(self, outbase):
        self.outbase = outbase
        self.files = {}

    # ------------------------------------------------------------------
    # Context-manager protocol.

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def open(self):
        """Open all 8 output files and write TSV headers."""
        for name, suffix in self.SUFFIXES.items():
            path = self.outbase + suffix
            if name == 'marc':
                self.files[name] = open(path, 'wb')
            else:
                self.files[name] = open(path, 'w', encoding='utf-8')
        for name in self.TSV_REPORTS:
            self._write_header(self.files[name])

    def close(self):
        """Close all open handles. Idempotent."""
        for fh in self.files.values():
            try:
                fh.close()
            except Exception:
                pass
        self.files = {}

    # ------------------------------------------------------------------
    # Header / row primitives.

    def _write_header(self, fh):
        fh.write('\t'.join(self.HEADER_COLUMNS) + '\n')

    def _write_alma_row(self, fh, alma_info, rec_info, match_type):
        """Write the ALMA-source row.

        Used for: not_found, toomany, no_match, and as the opener for
        each near_match block. Populates only the Alma-side columns;
        OCLC-side columns are left empty.
        """
        row = [
            "",                                            # Notes
            "",                                            # Number
            "'" + _v(alma_info.get('ARRIVAL_DATE')),       # Arrival date
            _v(rec_info.get('eym_count_list')),            # EYM
            "'" + _v(alma_info.get('SYSNUM')),             # Alma MMSID
            "ALMA",                                        # record source
            "",                                            # OCLC number
            _v(alma_info.get('TITLE')),                    # Title
            _v(alma_info.get('AUTHOR')),                   # Author
            "'" + _v(alma_info.get('DATE')),               # Alma pub date
            "",                                            # OCLC pub date
            _v(alma_info.get('LANG')),                     # 008 Language
            _v(alma_info.get('FMT')),                      # Recfmt
            _v(alma_info.get('HAS_245H')),                 # has_245h
            "",                                            # DLC
            "",                                            # PCC
            "",                                            # OCLC Elvl
            "",                                            # OCLC 1st 050
            "",                                            # 040 b
            _v(rec_info.get('inst_count_list')),           # # of Institutions
            "",                                            # Institutions
            match_type,                                    # match type
            "",                                            # searched on
            "",                                            # title match
            "",                                            # author match
            "",                                            # date match
            "",                                            # Big10 OCLC inst code
            "",                                            # OCLC numbered series
            _v(alma_info.get('FUND')),                     # Alma fund
            _v(alma_info.get('VENDOR')),                   # Alma vendor
            "",                                            # OCLC country code
            "",                                            # OCLC geo code
        ]
        fh.write('\t'.join(row) + '\n')

    def _write_oclc_row(self, fh, entry, alma_info):
        """Write the OCLC-source row for one matched / near-matched record."""
        institutions = entry.get('institutions') or []
        big_ten = entry.get('big_ten_institutions') or []
        row = [
            "",                                            # Notes
            "",                                            # Number
            "'" + _v(alma_info.get('ARRIVAL_DATE')),       # Arrival date
            _v(entry.get('eym_cnt')),                      # EYM
            "'" + _v(alma_info.get('SYSNUM')),             # Alma MMSID
            "OCLC",                                        # record source
            "'" + _v(entry.get('rec_oclc_num')),           # OCLC number
            _v(entry.get('rec_title')),                    # Title
            _v(entry.get('rec_author')),                   # Author
            "'" + _v(alma_info.get('DATE')),               # Alma pub date
            "'" + _v(entry.get('rec_pub_date')),           # OCLC pub date
            _v(entry.get('rec_lang')),                     # 008 Language
            _v(entry.get('rec_fmt')),                      # Recfmt
            _v(entry.get('has_245h')),                     # has_245h
            _v(entry.get('dlc')),                          # DLC
            _v(entry.get('pcc')),                          # PCC
            _v(entry.get('elvl')),                         # OCLC Elvl
            _v(entry.get('f050')),                         # OCLC 1st 050
            _v(entry.get('rec_040_b')),                    # 040 b
            str(len(institutions)),                        # # of Institutions
            '; '.join(institutions) if institutions else '',  # Institutions
            _v(entry.get('match_type')),                   # match type
            _v(entry.get('search')),                       # searched on
            _v(entry.get('title_match')),                  # title match
            _v(entry.get('author_match')),                 # author match
            _v(entry.get('date_match')),                   # date match
            ', '.join(big_ten),                            # Big10 OCLC inst code
            _v(entry.get('oclc_numbered_series')),         # OCLC numbered series
            _v(alma_info.get('FUND')),                     # Alma fund
            _v(alma_info.get('VENDOR')),                   # Alma vendor
            _v(entry.get('oclc_country_code')),            # OCLC country code
            _v(entry.get('oclc_geo_code')),                # OCLC geo code
        ]
        fh.write('\t'.join(row) + '\n')

    # ------------------------------------------------------------------
    # Public per-bucket writers.

    def record_not_found(self, alma_info):
        self._write_alma_row(self.files['not_found'], alma_info, {}, "not found")

    def record_toomany(self, alma_info):
        self._write_alma_row(self.files['toomany'], alma_info, {}, "too many matches")

    def record_no_match(self, alma_info, rec_info):
        self._write_alma_row(self.files['no_match'], alma_info, rec_info, "no matches")

    def record_match(self, alma_info, rec_info):
        """Write one OCLC row per matched info_entry. Returns the count."""
        fh = self.files['match']
        count = 0
        for entry in rec_info.get('info_entries', []):
            mt = entry.get('match_type', '')
            if mt.startswith('match'):
                self._write_oclc_row(fh, entry, alma_info)
                count += 1
        return count

    def record_near_match(self, alma_info, rec_info):
        """Write the ALMA opener, OCLC near rows, then the separator line."""
        fh = self.files['near_match']
        self._write_alma_row(fh, alma_info, rec_info, "near match")
        for entry in rec_info.get('info_entries', []):
            if entry.get('match_type', '').startswith('near'):
                self._write_oclc_row(fh, entry, alma_info)
        fh.write("'-------------------------------\n")

    # ------------------------------------------------------------------
    # Other output streams.

    def write_marc(self, mrec):
        """Append a pymarc record to the .marc binary file."""
        try:
            self.files['marc'].write(mrec.as_marc())
        except Exception:
            pass  # never crash the run over a single bad serialization

    def write_review(self, sysnum, ocn, fmt, alma_date, oclc_date):
        """Append one date-mismatch line to _review.txt."""
        self.files['review'].write(
            '\t'.join([sysnum, ocn, fmt, alma_date, oclc_date]) + '\n'
        )

    def write_log_line(self, counters):
        """Append one counter-state line to <outbase>.log."""
        self.files['log'].write(counters.to_log_line() + '\n')

    def write_summary(self, today, counters, incnt):
        """Write the 7-line _summary_rpt.tsv contents.

        Lines 1 and 2 have a literal "\\t***" suffix exactly as Perl emits.
        """
        fh = self.files['summary']
        fh.write('\t'.join(
            [f"Slavic search summary results, run date is {today}", "***"]
        ) + '\n')
        fh.write('\t'.join(["****************************", "***"]) + '\n')
        fh.write('\t'.join(["Alma records searched:", str(incnt)]) + '\n')
        fh.write('\t'.join([
            "OCLC record found, selected for Alma record:",
            str(counters.get('match_selected', 0))
        ]) + '\n')
        fh.write('\t'.join([
            "OCLC record(s) found, near match selected for Alma record:",
            str(counters.get('near_match_selected', 0))
        ]) + '\n')
        fh.write('\t'.join([
            "OCLC record(s) found, none selected for Alma record:",
            str(counters.get('not_selected', 0))
        ]) + '\n')
        fh.write('\t'.join([
            "Too many matches found for Alma record:",
            str(counters.get('toomany_cnt', 0))
        ]) + '\n')
        fh.write('\t'.join([
            "No OCLC record found for Alma record:",
            str(counters.get('tot_not_found', 0))
        ]) + '\n')


def get_today():
    """Today's date as YYYYMMDD — broken out for testability."""
    return datetime.now().strftime("%Y%m%d")
