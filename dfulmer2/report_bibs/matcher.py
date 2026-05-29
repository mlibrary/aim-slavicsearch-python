"""Match-type decision table and field-comparison helpers.

The 22-row decision table classifies a (search_type, title_match,
author_match, date_match) tuple into a final match-type string such as
"matched", "near match (Different edition)", or "exclude". The table comes
straight from slvr_report.pl lines 29-54 and slvr_report.py:42-65.
"""


class MatchTypeTable:
    """22-row decision table from slvr_report.pl.

    Rows are evaluated in order; the first row whose four conditions all
    match wins. The first column may be '' meaning "any search type".
    """

    # (search, title_match, author_match, date_match, match_type)
    ROWS = [
        ('',     'yes',  'yes',    'yes', 'matched'),
        ('',     'yes',  'no 100', 'yes', 'matched'),
        ('',     'near', 'yes',    'yes', 'near match (near/author/date)'),
        ('',     'near', 'no 100', 'yes', 'near match (near/date)'),
        ('',     'near', 'no 100', 'no',  'near match (Different edition)'),
        ('',     'near', 'no',     'yes', 'near match (near/date)'),
        ('',     'near', 'yes',    'no',  'near match (Different edition)'),
        ('',     'near', 'no',     'no',  'near match (Different edition)'),
        ('',     'yes',  'yes',    'no',  'near match (Different edition)'),
        ('',     'yes',  'no',     'yes', 'near match (Title/Date)'),
        ('ISBN', 'yes',  'no',     'no',  'near match (Different edition)'),
        ('ISBN', 'yes',  'no 100', 'no',  'near match (Different edition)'),
        ('ISBN', 'no',   'yes',    'yes', 'near match (ISBN/author/date)'),
        ('ISBN', 'no',   'no',     'yes', 'near match (ISBN/date)'),
        ('ISBN', 'no',   'no 100', 'yes', 'near match (ISBN/date)'),
        ('',     'no',   'no',     'no',  'exclude'),
        ('',     'no',   'yes',    'no',  'exclude'),
        ('TITLE', 'yes', 'no',     'no',  'exclude'),
        ('TITLE', 'no',  'yes',    'yes', 'exclude'),
        ('TITLE', 'no',  'no',     'yes', 'exclude'),
        ('',     'no',   'no 100', 'no',  'exclude'),
        ('TITLE', 'yes', 'no 100', 'no',  'exclude'),
    ]

    @classmethod
    def lookup(cls, search, title_match, author_match, date_match):
        """Return the match-type label, or 'exclude' if no row matches."""
        for sch, tm, am, dm, mtype in cls.ROWS:
            if (sch == '' or sch == search) \
                    and tm == title_match \
                    and am == author_match \
                    and dm == date_match:
                return mtype
        return 'exclude'


class Matcher:
    """Helpers for comparing already-normalized fields."""

    @staticmethod
    def field_match(a, b):
        """Exact equality."""
        return a == b

    @staticmethod
    def field_match_word(term_1, term_2, limit=5):
        """Position-aligned word equality.

        Returns 'yes' if `match_count >= limit`, 'near' if more than half
        the words in term_1 matched, else 'no'. Mirrors slvr_report.pl
        field_match_word (lines 693-715).
        """
        list_1 = term_1.split()
        list_2 = term_2.split()
        length = len(list_1)
        if length < limit:
            limit = length
        match_count = 0
        for i in range(length):
            w1 = list_1[i]
            w2 = list_2[i] if i < len(list_2) else ''
            if w1 == w2:
                match_count += 1
        if match_count >= limit:
            return 'yes'
        if match_count > length / 2:
            return 'near'
        return 'no'
