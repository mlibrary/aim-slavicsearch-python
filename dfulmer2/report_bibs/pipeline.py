"""Pipeline orchestration for one run.

`Pipeline` reads the input key file line by line, runs WorldCat searches,
evaluates each set of hits against the match-type decision table, and
dispatches the result to the appropriate output bucket (matched, near
match, no_match, not_found, toomany). The terminal-message format is
preserved byte-for-byte from slvr_report.pl so a user comparing logs
side-by-side sees the same shape of output.

The class takes its WorldCatClient and ReportSet as constructor
arguments (dependency injection), which is what makes the test suite
network-free — `test_pipeline.py` passes in a fake client and an
in-memory report set.
"""
import signal
import sys
import time

from .bib import Bib
from .line_io import KeyLineParser
from .matcher import Matcher, MatchTypeTable
from .normalize import Normalizer
from .reports import get_today
from .worldcat import WorldCatError


class Pipeline:
    """Drive one full report-stage run."""

    SEARCH_ORDER = ('OCLC', 'ISSN', 'ISBN', 'TITLE')
    SESSION_REFRESH_INTERVAL = 50
    TITLE_WORD_MATCH_LIMIT = 5
    SLEEP_SECONDS = 2

    # Matches Perl's %big_ten_institutions hash in slvr_report.pl.
    BIG_TEN_INSTITUTIONS = frozenset([
        "UIU", "IUL", "NUI", "UMC", "EEM", "MNU", "LDL", "INU",
        "OSU", "UPM", "IPL", "NJR", "GZM", "CGU", "WAU",
    ])

    # Z39.50 PQF attribute codes — preserved purely for the cosmetic
    # "searching X, zq=@attr 1=N \"...\"" terminal message. The actual API
    # query syntax is in WorldCatClient.SEARCH_INDEX.
    PQF_ATTR = {'OCLC': '12', 'ISSN': '8', 'ISBN': '7', 'TITLE': '4'}

    def __init__(self, client, reports, counters, *, stdout=None, stderr=None):
        self.client = client
        self.reports = reports
        self.counters = counters
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr
        self.exit_flag = False
        self.incnt = 0
        self.search_cnt = 0
        self.type_cnt = {}

    # ------------------------------------------------------------------
    # Signal handling (optional — tests don't install handlers).

    def install_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        self.exit_flag = True

    # ------------------------------------------------------------------
    # Top-level driver.

    def run(self, infile_path):
        """Process every line in `infile_path` and write the summary."""
        today = get_today()
        with open(infile_path, 'r', encoding='utf-8') as infile:
            for raw in infile:
                if self.exit_flag:
                    self.stdout.write("exitting due to signal\n")
                    break
                line = raw.rstrip('\r\n')
                if not line:
                    continue
                self.incnt += 1
                if self.incnt % self.SESSION_REFRESH_INTERVAL == 0:
                    self._refresh_session()
                self.process_line(line)
        self._write_terminal_summary()
        self.reports.write_summary(today, self.counters, self.incnt)

    def _refresh_session(self):
        """Close the WorldCat session, pause 2 seconds, then reopen.

        Mirrors slvr_report.pl's Z39.50 reconnect cadence. The 'sleeping' /
        'continue' messages go to stderr, exactly as Perl emits them.
        """
        self.client.close()
        self.stderr.write(f"{self.incnt}: sleeping\n")
        time.sleep(self.SLEEP_SECONDS)
        self.stderr.write(f"{self.incnt}: continue\n")
        self.client.connect()

    # ------------------------------------------------------------------
    # Per-record logic.

    def process_line(self, line):
        """Handle one input line end-to-end."""
        alma = KeyLineParser.parse(line)
        sysnum = alma.get('SYSNUM', '')
        self.counters.set_sysnum(sysnum)
        alma['HAS_245H'] = 0 if alma.get('TITLE_H', '') == '' else 1

        records, too_many = self.search_record(alma, sysnum)

        if not records:
            if too_many:
                self._handle_too_many(sysnum, too_many, alma)
            else:
                self._handle_not_found(sysnum, alma)
            self.reports.write_log_line(self.counters)
            return

        rec_info = self.evaluate_records(records, alma, sysnum)
        match_type = rec_info.get('result_match_type', '')

        if not match_type:
            self.counters.increment('not_selected')
            msg = f"{sysnum}({self.incnt}): no valid records found\n"
            self.stdout.write(msg)
            self.stderr.write(msg)
            self.reports.record_no_match(alma, rec_info)
        elif match_type == 'matched':
            self.counters.increment('match_selected')
            self.counters.increment('selected')
            pm = self.reports.record_match(alma, rec_info)
            if pm == 0:
                raise RuntimeError(f"{sysnum}: no matches printed for match type {match_type}")
        elif match_type == 'near match':
            self.counters.increment('near_match_selected')
            self.counters.increment('selected')
            self.reports.record_near_match(alma, rec_info)
        else:
            raise RuntimeError(f"{sysnum}: unknown match type {match_type!r}")

        self.reports.write_log_line(self.counters)

    # ------------------------------------------------------------------
    # WorldCat search step.

    def search_record(self, alma, sysnum):
        """Run the four searches in order; return (records, too_many).

        records is a list of (search_type, pymarc.Record) tuples deduped
        by OCLC#. too_many is a list of "TYPE = 'term'" strings for
        searches whose hit count exceeded MAX_HITS.
        """
        records = []
        seen_ocns = set()
        too_many = []
        for search_type in self.SEARCH_ORDER:
            if search_type not in alma:
                continue
            term = alma[search_type]
            if not term:
                raise RuntimeError(
                    f"{sysnum}({self.incnt}): no term for search {search_type}"
                )
            rc = self._one_search(search_type, term, sysnum, records, seen_ocns)
            if rc == 2:
                too_many.append(f"{search_type} = '{term}'")
            self.search_cnt += 1
            self.type_cnt[search_type] = self.type_cnt.get(search_type, 0) + 1
        return records, too_many

    def _one_search(self, search_type, term, sysnum, records, seen_ocns):
        """One call to WorldCat for one (search_type, term).

        Returns:
          0  — no records
          1  — records found (mutated into the `records` list)
          2  — too many records (numberOfRecords > max_hits)
        """
        norm_term = Normalizer.for_type(term, search_type)
        attr = self.PQF_ATTR.get(search_type, '?')
        zq = f'@attr 1={attr} "{norm_term}"'
        self.stdout.write(
            f"{sysnum}({self.incnt}):{term}: searching {search_type}, zq={zq}\n"
        )

        try:
            numrec, oclc_numbers = self.client.brief_search(search_type, norm_term)
        except WorldCatError as e:
            self.stderr.write(
                f"{sysnum}({self.incnt}):search error trapped, search is {zq}\n{e}\n"
            )
            sys.exit(1)

        if numrec == 0:
            self.stdout.write(
                f"{sysnum}({self.incnt}):{term}: {search_type} not found\n"
            )
            return 0
        if numrec > self.client.max_hits:
            self.stdout.write(
                f"{sysnum}({self.incnt}):{term}: too many records found for {search_type} ({numrec})\n"
            )
            return 2

        for ocn in oclc_numbers:
            stripped = ocn
            # Strip ocm/ocn/on prefix the same way Perl does on 001 dedup.
            for prefix in ('ocm', 'ocn', 'on'):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):]
                    break
            if stripped in seen_ocns:
                continue
            seen_ocns.add(stripped)
            mrec = self.client.fetch_marc(ocn)
            if mrec is None:
                self.stdout.write(
                    f"{sysnum}({self.incnt}): error getting record for {search_type} {term} from worldcat\n"
                )
                continue
            records.append((search_type, mrec))
        return 1

    # ------------------------------------------------------------------
    # Per-record evaluation: which buckets does each retrieved record land in?

    def evaluate_records(self, records, alma, sysnum):
        """Evaluate every retrieved OCLC record against the Alma record.

        Returns rec_info: {info_entries, result_match_type, inst_count_list,
        eym_count_list}. info_entries holds one dict per non-excluded record.
        """
        info_entries = []
        inst_counts = []
        eym_counts = []
        match_type_seen = {}

        alma_title_norm = Normalizer.title(alma.get('TITLE', ''))
        alma_author = alma.get('AUTHOR', '')
        alma_author_tag = alma.get('AUTHOR_TAG', '')
        alma_date = alma.get('DATE', '')
        alma_author_norm = ''
        if alma_author and alma_author_tag == '100':
            alma_author_norm = Normalizer.author(alma_author, alma_author_tag)
        alma_date_norm = Normalizer.date(alma_date) if alma_date else ''

        for search_type, mrec in records:
            bib = Bib(mrec)
            if not bib.passes_field_checks:
                continue
            entry = self._build_info_entry(
                bib, search_type, alma, sysnum,
                alma_title_norm, alma_author_norm, alma_date_norm, alma_date,
            )
            if entry is None:
                continue
            mt = MatchTypeTable.lookup(
                entry['search'], entry['title_match'],
                entry['author_match'], entry['date_match'],
            )
            if not mt or mt == 'exclude':
                continue
            entry['match_type'] = mt
            key = 'near match' if mt.startswith('near match') else mt
            match_type_seen[key] = match_type_seen.get(key, 0) + 1
            inst_counts.append(len(entry['institutions']))
            eym_counts.append(entry['eym_cnt'])
            info_entries.append(entry)
            self.reports.write_marc(mrec)

        if 'matched' in match_type_seen:
            result = 'matched'
        elif 'near match' in match_type_seen:
            result = 'near match'
        else:
            result = ''

        return {
            'info_entries': info_entries,
            'result_match_type': result,
            'inst_count_list': ','.join(str(c) for c in inst_counts),
            'eym_count_list': ','.join(str(c) for c in eym_counts),
        }

    def _build_info_entry(self, bib, search_type, alma, sysnum,
                          alma_title_norm, alma_author_norm,
                          alma_date_norm, alma_date_raw):
        """Build the info_entry dict for one retrieved record, or None
        if the record's title doesn't match the Alma title.
        """
        # Title match — required.
        rec_title = bib.title_ab
        rec_title_norm = Normalizer.title(rec_title)
        title_match = Matcher.field_match_word(
            alma_title_norm, rec_title_norm, self.TITLE_WORD_MATCH_LIMIT
        )
        if title_match == 'no':
            return None
        self.stdout.write(f"title_match, rc={title_match}\n")

        # Author match.
        author_match = 'no 100'
        if alma_author_norm:
            author_match = 'no'
            rec_author_100 = bib.author_100_value
            if rec_author_100:
                rec_author_norm = Normalizer.author(rec_author_100, '100')
                if Matcher.field_match(alma_author_norm, rec_author_norm):
                    author_match = 'yes'

        # Date match — and record any mismatch in the review file.
        rec_date_raw, _ = bib.pub_date
        rec_date_norm = Normalizer.date(rec_date_raw) if rec_date_raw else ''
        date_match = 'no'
        if alma_date_norm:
            if alma_date_norm == rec_date_norm:
                date_match = 'yes'
            else:
                self.reports.write_review(
                    sysnum, bib.oclc_number, bib.record_format,
                    alma_date_raw, rec_date_raw,
                )

        # Holdings — one Search API V2 /bibs-holdings call per surviving
        # record. Returns the full list of OCLC institution symbols, from
        # which we derive the EYM count and the Big Ten subset (mirroring
        # Perl's process_institutions over the 948$c subfields).
        institutions = self.client.fetch_holdings_list(bib.oclc_number)
        eym_cnt = sum(1 for s in institutions if s == 'EYM')
        big_ten = [s for s in institutions if s in self.BIG_TEN_INSTITUTIONS]

        entry = {
            'search': search_type,
            'title_match': title_match,
            'author_match': author_match,
            'date_match': date_match,
            'has_245h': bib.has_245h,
            'institutions': institutions,
            'big_ten_institutions': big_ten,
            'eym_cnt': eym_cnt,
            'rec_lang': bib.language,
            'oclc_country_code': bib.country_code,
            'oclc_geo_code': bib.geo_code,
            'rec_oclc_num': bib.oclc_number,
            'rec_fmt': bib.record_format,
            'rec_title': rec_title,
            'rec_author': bib.author_value,
            'rec_pub_date': rec_date_norm,
            'elvl': bib.encoding_level,
            'rec_040_b': bib.f040_b,
            'f050': bib.f050_ab,
            'dlc': 'DLC' if bib.is_dlc else '',
            'pcc': 'PCC' if bib.is_pcc else '',
            'oclc_numbered_series': '490$v' if bib.has_oclc_numbered_series else '',
        }
        return entry

    # ------------------------------------------------------------------
    # Result handlers for the no-records branches.

    def _handle_too_many(self, sysnum, too_many, alma):
        msg = (
            f"{sysnum}({self.incnt}): no records, too many records found for searches: "
            + ",".join(too_many) + " \n"
        )
        self.stdout.write(msg)
        self.stderr.write(msg)
        self.reports.record_toomany(alma)
        self.counters.increment('toomany_cnt')

    def _handle_not_found(self, sysnum, alma):
        self.counters.increment('tot_not_found')
        self.stdout.write(
            f"{sysnum}({self.incnt}): no records for any search terms\n"
        )
        self.reports.record_not_found(alma)

    # ------------------------------------------------------------------
    # End-of-run summary on the terminal.

    def _write_terminal_summary(self):
        self.stdout.write("'==============================\n")
        self.stdout.write(f"{self.incnt} records read\n")
        if self.search_cnt:
            self.stdout.write(f"{self.search_cnt} searches\n")
        for t in sorted(self.type_cnt):
            self.stdout.write(f"\t{t}: {self.type_cnt[t]}\n")
