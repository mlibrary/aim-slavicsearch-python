"""Line parsing and per-run counter tracking.

`KeyLineParser` turns one input line (tab-delimited KEY:VALUE pairs as
produced by slvr_extract.pl / dfulmer/processor.py) into a plain dict.

`Counters` accumulates the per-run match/no-match/etc. counts and emits
the log line that goes into <outbase>.log.
"""


class KeyLineParser:
    """Parses the tab-delimited KEY:VALUE lines that feed slvr_report."""

    @staticmethod
    def parse(line):
        """Return a dict for one input line.

        Each tab-separated field is split on the FIRST colon only, so
        values containing colons (e.g. titles) are preserved intact.
        Fields with an empty key are dropped.
        """
        out = {}
        for field in line.split('\t'):
            if not field:
                continue
            parm, sep, value = field.partition(':')
            if not parm or not sep:
                continue
            out[parm] = value
        return out


class Counters:
    """Tracks per-run counters and emits log-line strings.

    Mirrors Perl's `$counters` hashref in slvr_report.pl. Five counters
    are initialized to 0 at construction; a sixth (`selected`) is added
    lazily on the first successful match. `SYSNUM` is set per input line.
    Keys are written to the log line in alphabetical order.
    """

    INITIAL_KEYS = (
        'match_selected',
        'near_match_selected',
        'tot_not_found',
        'not_selected',
        'toomany_cnt',
    )

    def __init__(self):
        self.values = {k: 0 for k in self.INITIAL_KEYS}

    def set_sysnum(self, sysnum):
        """Record the SYSNUM of the line currently being processed."""
        self.values['SYSNUM'] = sysnum

    def increment(self, key):
        """Add 1 to the named counter (creating it if it's not yet present)."""
        self.values[key] = self.values.get(key, 0) + 1

    def get(self, key, default=0):
        return self.values.get(key, default)

    def to_log_line(self):
        """Tab-delimited KEY:value pairs, keys alphabetical."""
        return '\t'.join(f"{k}:{self.values[k]}" for k in sorted(self.values))
