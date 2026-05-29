"""Read-only view of a pymarc.Record for the report stage.

`Bib` wraps a single MARC record and exposes one `@cached_property` per
field that slvr_report.pl reads from each retrieved OCLC bib. This mirrors
the structure of dfulmer/extract_bibs/bib.py — the same wrap-the-record-
in-properties pattern, just for a different set of fields.
"""
import re
from functools import cached_property


class Bib:
    """Wraps a pymarc.Record. Properties are cached per-instance."""

    def __init__(self, record):
        self.record = record

    # ------------------------------------------------------------------
    # Identifiers and control fields.

    @cached_property
    def oclc_number(self):
        """001 field with the 'ocm', 'ocn', or 'on' prefix stripped."""
        fields = self.record.get_fields('001')
        if not fields:
            return ''
        return re.sub(r'(ocm|ocn|on)', '', fields[0].value())

    @cached_property
    def f008(self):
        """The full 008 control-field value, or empty string."""
        fields = self.record.get_fields('008')
        if not fields:
            return ''
        return fields[0].value()

    @cached_property
    def language(self):
        """008 positions 35-37 — language code."""
        return self.f008[35:38] if len(self.f008) >= 38 else ''

    @cached_property
    def country_code(self):
        """008 positions 15-17 — OCLC country code."""
        return self.f008[15:18] if len(self.f008) >= 18 else ''

    @cached_property
    def encoding_level(self):
        """Leader byte 17."""
        leader = str(self.record.leader)
        return leader[17] if len(leader) > 17 else ''

    @cached_property
    def record_format(self):
        """Leader[6]+Leader[7] → 2-letter format code (BK, SE, VM, ...).

        Returns '' for invalid combinations and writes a diagnostic to
        stderr, matching Perl's getRecFmt (slvr_report.pl 717-740). Raises
        ValueError only for genuinely unmappable but otherwise-valid codes.
        """
        leader = str(self.record.leader)
        if not leader:
            return ''
        rec_typ = leader[6]
        bib_lev = leader[7]
        if rec_typ == 'z':
            return 'AU'
        if rec_typ not in 'abcdefgijkmoprt':
            return ''
        if bib_lev not in 'abcdms':
            return ''
        if rec_typ in 'at' and bib_lev in 'acdm':
            return 'BK'
        if rec_typ == 'm' and bib_lev in 'abcdms':
            return 'CF'
        if rec_typ in 'gkor' and bib_lev in 'abcdms':
            return 'VM'
        if rec_typ in 'cdij' and bib_lev in 'abcdms':
            return 'MU'
        if rec_typ in 'ef' and bib_lev in 'abcdms':
            return 'MP'
        if rec_typ == 'a' and bib_lev in 'bs':
            return 'SE'
        if rec_typ in 'bp' and bib_lev in 'abcdms':
            return 'MX'
        raise ValueError(f"can't set bib fmt, recTyp={rec_typ}, bibLev={bib_lev}")

    # ------------------------------------------------------------------
    # Title (245) and related.

    @cached_property
    def title_ab(self):
        """245 subfields a+b joined, with non-filing-indicator BYTE trim.

        Perl `bytes::substr` skips a byte count, not a codepoint count, so
        we round-trip through UTF-8 bytes. The same trick is used in the
        extract port (dfulmer/extract_bibs/bib.py:title_ab).
        """
        fields = self.record.get_fields('245')
        if not fields:
            return ''
        f = fields[0]
        s = ' '.join(f.get_subfields('a', 'b'))
        try:
            nf_ind = int(str(f.indicator2))
        except (ValueError, TypeError):
            nf_ind = 0
        return s.encode('utf-8')[nf_ind:].decode('utf-8', errors='replace').strip()

    @cached_property
    def title_h_value(self):
        """245$h (general material designation), or ''."""
        fields = self.record.get_fields('245')
        if not fields:
            return ''
        return ' '.join(fields[0].get_subfields('h'))

    @cached_property
    def has_245h(self):
        """1 if 245$h is non-empty, else 0. (Matches Perl's truthiness.)"""
        return 1 if self.title_h_value else 0

    # ------------------------------------------------------------------
    # Author (1xx).

    @cached_property
    def first_1xx_field(self):
        """First of 100/110/111/130 in order, or None."""
        for f in self.record.get_fields('100', '110', '111', '130'):
            return f
        return None

    @cached_property
    def author_value(self):
        """First subfield $a of the 1xx field. Returns 'none' when absent.

        The literal 'none' default mirrors Perl line 460
        (info_entry->{rec_author} = 'none').
        """
        f = self.first_1xx_field
        if f is None:
            return 'none'
        return ' '.join(f.get_subfields('a'))

    @cached_property
    def author_100_value(self):
        """$a of the 100 field only — empty when the first 1xx isn't a 100."""
        f = self.first_1xx_field
        if f is None or f.tag != '100':
            return ''
        return ' '.join(f.get_subfields('a'))

    # ------------------------------------------------------------------
    # Publication date — tries 260$c, 264#1$c, 008[7:11] in order.

    @cached_property
    def pub_date(self):
        """Return (date, source) where source is '260'/'264'/'008'/'none'."""
        date = self.get_bib_data(self.record, '260', 'c')
        if date:
            return date, '260'
        date = self.get_bib_data(self.record, '264#1', 'c')
        if date:
            return date, '264'
        if self.f008:
            date = self.f008[7:11]
            if date:
                return date, '008'
        return '', 'none'

    @staticmethod
    def get_bib_data(record, tag_spec, subfield):
        """Fetch subfield value(s) from one or more fields, optionally
        filtered by indicator.

        `tag_spec` may be a plain three-digit tag ('260') or a tag plus
        one or two indicator characters ('264#1', '245#0'). A '#' in an
        indicator position means "match any". Returns a comma-joined
        string with leading/trailing whitespace stripped.

        Static so it can be unit-tested without constructing a Bib.
        """
        i1 = ''
        i2 = ''
        if len(tag_spec) > 3:
            if len(tag_spec) >= 4:
                i1 = tag_spec[3]
            if len(tag_spec) >= 5:
                i2 = tag_spec[4]
            tag = tag_spec[:3]
        else:
            tag = tag_spec
        data = []
        for field in record.get_fields(tag):
            if i1 and i1 != '#' and str(field.indicator1) != i1:
                continue
            if i2 and i2 != '#' and str(field.indicator2) != i2:
                continue
            joined = ' '.join(field.get_subfields(*subfield))
            if joined:
                data.append(joined)
        return ','.join(data).strip()

    # ------------------------------------------------------------------
    # Cataloging / cataloging-source fields.

    @cached_property
    def f040_b(self):
        """040$b cataloging language code (often 'eng'), or ''."""
        fields = self.record.get_fields('040')
        if not fields:
            return ''
        return ' '.join(fields[0].get_subfields('b'))

    @cached_property
    def f050_ab(self):
        """050$a + 050$b call number, or ''."""
        fields = self.record.get_fields('050')
        if not fields:
            return ''
        return ' '.join(fields[0].get_subfields('a', 'b'))

    @cached_property
    def is_dlc(self):
        """True when 050 indicator2 is '0' (Library of Congress assigned)."""
        fields = self.record.get_fields('050')
        if not fields:
            return False
        return str(fields[0].indicator2) == '0'

    @cached_property
    def is_pcc(self):
        """True when 042$a == 'pcc' (Program for Cooperative Cataloging)."""
        fields = self.record.get_fields('042')
        if not fields:
            return False
        return ' '.join(fields[0].get_subfields('a')) == 'pcc'

    @cached_property
    def has_oclc_numbered_series(self):
        """True when any 490 has a $v (volume number)."""
        for field in self.record.get_fields('490'):
            if field.get_subfields('v'):
                return True
        return False

    @cached_property
    def geo_code(self):
        """043 field value (geographic area code), or ''."""
        fields = self.record.get_fields('043')
        if not fields:
            return ''
        return fields[0].value()

    # ------------------------------------------------------------------
    # The two reject conditions from slvr_report.pl get_records.

    @cached_property
    def passes_field_checks(self):
        """True if the record survives the per-record rejection rules.

        Specifically: 008 position 23 must be a blank, and 040$b must be
        either 'eng' or absent. (Title-match rejection is handled by the
        Pipeline, not here, because it requires the Alma title for comparison.)
        """
        if len(self.f008) <= 23 or self.f008[23] != ' ':
            return False
        if self.f040_b and self.f040_b != 'eng':
            return False
        return True

    # ------------------------------------------------------------------
    # Serialization passthrough.

    def as_marc(self):
        """Binary USMARC bytes — for writing to the .marc output file."""
        return self.record.as_marc()
