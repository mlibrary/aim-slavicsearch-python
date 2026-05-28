"""Normalization of search terms before matching.

Every search type (ISBN, ISSN, OCLC, LCCN, TITLE, AUTHOR, DATE) has a
slightly different normalization rule. All the rules live here as
classmethods of `Normalizer` so they share a clear namespace and the
stopword / punctuation tables are class attributes (not module globals).

This module is a direct port of the `norm()` and `char_norm_unicode()`
functions in slvr_report.pl (lines 587-684).
"""
import re
import unicodedata


class Normalizer:
    """Normalize a search term to a comparable form.

    Use Normalizer.for_type(term, ntype) when the search type is known only
    as a string at runtime (the search loop). Use the per-type classmethods
    (Normalizer.isbn, Normalizer.title, ...) when the call site knows the
    type at write time.
    """

    # 80 English stopwords that OCLC's title index ignores. Verbatim from
    # slvr_report.pl lines 74-81.
    STOPWORDS = frozenset("""
        a for in she was an from into so
        were and had is than when are has
        it that which as have its the with
        at he not their would be her of there
        you but his on this by if or to
    """.split())

    # Punctuation stripped from titles (Perl line 620). Includes \xC5 and
    # \xC6 (Latin-1 Å and Æ) which Perl's tr/// treats as a range.
    TITLE_PUNCT = frozenset("!@#$%^*()_+={}[];:'\"<>,.?\xC5\xC6")

    # Author punctuation set (Perl line 641) — same as title but without
    # the two Latin-1 letters.
    AUTHOR_PUNCT = frozenset("!@#$%^*()_+={}[];:'\"<>,.?")

    @classmethod
    def char_norm_unicode(cls, term):
        """NFKD decompose; strip marks/modifiers; map ł→l and đ→d.

        Mirrors slvr_report.pl `char_norm_unicode` (lines 675-684).
        """
        term = unicodedata.normalize('NFKD', term)
        kept = []
        for ch in term:
            cat = unicodedata.category(ch)
            if cat in ('Mn', 'Mc', 'Me'):
                continue  # combining marks (\p{M})
            if cat == 'Lm':
                continue  # modifier letters (\p{Lm})
            kept.append(ch)
        s = ''.join(kept)
        s = s.replace('ł', 'l')  # ł
        s = s.replace('đ', 'd')  # đ
        return s

    @classmethod
    def title(cls, term):
        """Title normalization for matching."""
        term = term.lower()
        term = cls.char_norm_unicode(term)
        term = re.sub(r' [-&:] ', ' ', term)
        term = term.replace('-', ' ')
        term = ''.join(ch for ch in term if ch not in cls.TITLE_PUNCT)
        term = term.replace('/', ' ')
        words = [w for w in term.split() if w not in cls.STOPWORDS]
        return ' '.join(words)

    @classmethod
    def author(cls, term, tag=''):
        """Author normalization.

        When the source field is a 100 (personal name) and the term contains
        a comma, truncate to "Last, F" (last name plus first initial) before
        further cleanup. Other tag values (110, 111, 130) are normalized
        whole. This matches slvr_report.pl lines 629-651.
        """
        term = term.lower()
        if tag == '100' and ',' in term:
            m = re.match(r'(.*?,\s*\w).*', term)
            if m:
                term = m.group(1)
        term = cls.char_norm_unicode(term)
        term = re.sub(r' [-&:] ', ' ', term)
        term = term.replace('-', ' ')
        term = ''.join(ch for ch in term if ch not in cls.AUTHOR_PUNCT)
        term = term.replace('/', ' ')
        return term

    @classmethod
    def date(cls, term):
        """Date normalization: first 4-digit year wins, else keep digits/u/-."""
        m = re.search(r'(\d{4})', term)
        if m:
            return m.group(1)
        return ''.join(c for c in term if c.isdigit() or c in 'u-')

    @classmethod
    def isbn(cls, term):
        """Strip dashes, spaces, and apostrophes; lowercase."""
        return ''.join(c for c in term if c not in "- '").lower()

    @classmethod
    def issn(cls, term):
        """ISSN normalization is the same as ISBN."""
        return cls.isbn(term)

    @classmethod
    def oclc(cls, term):
        """First digit run, coerced to int (strips leading zeros)."""
        m = re.search(r'(\d+)', term)
        if not m:
            return 0
        return int(m.group(1))

    @classmethod
    def lccn(cls, term):
        """First digit run, kept as a string."""
        m = re.search(r'(\d+)', term)
        return m.group(1) if m else ''

    @classmethod
    def mpn(cls, term):
        """No normalization — pass through."""
        return term

    # ------------------------------------------------------------------
    # Dispatch by string type — used by the search loop.

    _DISPATCH = {
        'TITLE': 'title',
        'AUTHOR': 'author',
        'DATE': 'date',
        'ISBN': 'isbn',
        'ISSN': 'issn',
        'OCLC': 'oclc',
        'LCCN': 'lccn',
        'MPN': 'mpn',
    }

    @classmethod
    def for_type(cls, term, ntype, tag=''):
        """Normalize `term` according to the named search type."""
        ntype = ntype.upper()
        if ntype not in cls._DISPATCH:
            raise ValueError(f"invalid normalization type: {ntype}")
        method = getattr(cls, cls._DISPATCH[ntype])
        if ntype == 'AUTHOR':
            return method(term, tag)
        return method(term)
