"""WorldCat Metadata API + Search API V2 wrapper.

`WorldCatClient` is the only class in dfulmer2 that touches the network.
The pipeline depends on it through dependency injection, so tests can
swap in a `FakeMetadataSession` and exercise the full pipeline offline.

Operations exposed:
  - brief_search:   query the WorldCat brief-bibs index by ISBN / ISSN /
                    OCLC# / title, return (numberOfRecords, [oclc_numbers])
  - fetch_marc:     pull a full bib record as MARCXML, parse to pymarc
  - fetch_holdings_list:  full list of OCLC institution symbols holding
                          an OCN, via the Search API V2 /bibs-holdings
                          endpoint (bookops_worldcat doesn't wrap it)
  - fetch_holdings_count:  legacy count-only fallback via Metadata API
                           summary_holdings_search (no longer called by
                           the pipeline; kept for backward compatibility)
  - connect / reconnect / close:  session lifecycle (used by the 50-record
                                  refresh cadence Perl inherited from Z39.50)
"""
import io
import os

import requests


class WorldCatError(Exception):
    """Raised when the WorldCat API returns an HTTP error.

    The pipeline catches this, prints the same "search error trapped"
    diagnostic Perl emits, and exits — matching slvr_report.pl's "die on
    Z39.50 error" behavior.
    """


class WorldCatClient:
    """Thin wrapper around bookops_worldcat.MetadataSession.

    The Z39.50 PQF attribute codes are tracked for the cosmetic terminal
    message ('searching X, zq=@attr 1=N "..."') that Perl emits. The
    actual API uses the prefix codes in SEARCH_INDEX.
    """

    # WorldCat brief_bibs_search query-index prefixes.
    SEARCH_INDEX = {
        'OCLC':  'no',
        'ISSN':  'in',
        'ISBN':  'bn',
        'TITLE': 'ti',
    }

    DEFAULT_AGENT = 'slavicsearch-port/0.1'
    DEFAULT_SCOPE = (
        'WorldCatMetadataAPI '
        'wcapi:view_holdings '
        'wcapi:view_institution_holdings'
    )

    HOLDINGS_URL = (
        'https://americas.discovery.api.oclc.org'
        '/worldcat/search/v2/bibs-holdings'
    )

    def __init__(self, token, agent=DEFAULT_AGENT, max_hits=50, session_factory=None):
        """Create the client.

        token : WorldcatAccessToken (real or fake) — anything with an
                interface compatible with bookops_worldcat.MetadataSession's
                `authorization=` parameter.
        agent : User-Agent string sent to OCLC.
        max_hits : MAX_HITS — caps brief-search limit, drives too-many detection.
        session_factory : Callable used to construct the underlying session.
                When None (the default), bookops_worldcat.MetadataSession is
                used. Tests pass a factory that returns a FakeMetadataSession.
        """
        self.token = token
        self.agent = agent
        self.max_hits = max_hits
        if session_factory is None:
            from bookops_worldcat import MetadataSession
            self._session_factory = lambda: MetadataSession(authorization=self.token)
        else:
            self._session_factory = session_factory
        self.session = None
        self.connect()

    @classmethod
    def from_env(cls, environ=None, **kwargs):
        """Read WSKEY_* from os.environ and build a real WorldCat token.

        Raises KeyError if WSKEY_CLIENT_ID or WSKEY_SECRET is missing.
        """
        env = environ if environ is not None else os.environ
        key = env['WSKEY_CLIENT_ID']
        secret = env['WSKEY_SECRET']
        scopes = env.get('WSKEY_SCOPES', cls.DEFAULT_SCOPE)
        # Auto-augment legacy .env files (which only had WorldCatMetadataAPI)
        # so fetch_holdings_list can hit Search API V2 without manual edits.
        if 'wcapi:view_holdings' not in scopes:
            scopes = (scopes + ' wcapi:view_holdings').strip()
        if 'wcapi:view_institution_holdings' not in scopes:
            scopes = (scopes + ' wcapi:view_institution_holdings').strip()
        from bookops_worldcat import WorldcatAccessToken
        token = WorldcatAccessToken(
            key=key,
            secret=secret,
            scopes=scopes,
            agent=kwargs.pop('agent', cls.DEFAULT_AGENT),
        )
        return cls(token, **kwargs)

    # ------------------------------------------------------------------
    # Session lifecycle.

    def connect(self):
        """Open a fresh session. Safe to call after close()."""
        self.session = self._session_factory()

    def reconnect(self):
        """Close and re-open the session.

        Called every 50 records by the pipeline (mirroring Perl's Z39.50
        reconnect cadence). The OAuth token is reused; only the HTTP
        session is recreated.
        """
        self.close()
        self.connect()

    def close(self):
        """Release the HTTP session if one is open."""
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None

    # ------------------------------------------------------------------
    # Operations.

    def brief_search(self, search_type, normalized_term):
        """Run a brief-bib search.

        Returns (numberOfRecords, [oclc_number, ...]).
        - numberOfRecords is the TOTAL hits the server reports (may exceed
          the number of OCLC numbers returned when there are too many).
        - The list of OCLC numbers is what the caller will iterate over to
          fetch full MARC records.

        Raises WorldCatError on any HTTP error.
        """
        if search_type not in self.SEARCH_INDEX:
            raise ValueError(f"unsupported search type: {search_type}")
        query = f"{self.SEARCH_INDEX[search_type]}: {normalized_term}"
        try:
            r = self.session.brief_bibs_search(q=query, limit=self.max_hits)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise WorldCatError(str(e)) from e
        numrec = data.get('numberOfRecords', 0)
        briefs = data.get('briefRecords') or data.get('bibRecords') or []
        oclc_numbers = [str(b['oclcNumber']) for b in briefs if b.get('oclcNumber') is not None]
        return numrec, oclc_numbers

    def fetch_marc(self, oclc_number):
        """Fetch one bib as MARCXML and parse to pymarc.Record.

        Returns the pymarc.Record on success, or None when:
          - the HTTP call fails
          - parse_xml_to_array returns an empty list
          - parsing raises an exception

        The pipeline treats None as "skip this record" — same effect as
        Perl's "zreclen <= 5: bad record, ignoring" path.
        """
        try:
            r = self.session.bib_get(oclcNumber=oclc_number)
            r.raise_for_status()
        except Exception:
            return None
        from pymarc import parse_xml_to_array
        try:
            records = parse_xml_to_array(io.BytesIO(r.content))
        except Exception:
            return None
        if not records:
            return None
        return records[0]

    def fetch_holdings_count(self, oclc_number):
        """Return the total institution-holding count for an OCLC#.

        Legacy fallback that only returns the count, not the symbol list.
        Pipeline switched to fetch_holdings_list (which gives both); this
        method is kept so older callers / tests don't break.
        """
        try:
            r = self.session.summary_holdings_search(oclcNumber=oclc_number)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return 0
        briefs = data.get('briefRecords') or []
        if not briefs:
            return 0
        ih = briefs[0].get('institutionHolding') or {}
        total = ih.get('totalHoldingCount')
        try:
            return int(total) if total is not None else 0
        except (TypeError, ValueError):
            return 0

    def fetch_holdings_list(self, oclc_number):
        """Return the full list of OCLC institution symbols holding the OCN.

        Calls the WorldCat Search API V2 /bibs-holdings endpoint, which
        bookops_worldcat does not wrap natively, so this uses requests.get
        directly with the bearer token from self.token. The endpoint
        requires the wcapi:view_holdings and wcapi:view_institution_holdings
        scopes (DEFAULT_SCOPE includes both).

        Order of symbols in the returned list matches the order the API
        returns them in — no sorting.

        Returns [] on any error (network, non-200, missing keys) so the
        pipeline can keep going with empty Institutions columns rather
        than aborting on one bad record.
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.token.token_str}',
                'Accept': 'application/json',
                'User-Agent': self.agent,
            }
            r = requests.get(
                self.HOLDINGS_URL,
                headers=headers,
                params={'oclcNumber': str(oclc_number)},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
        briefs = data.get('briefRecords') or []
        if not briefs:
            return []
        ih = briefs[0].get('institutionHolding') or {}
        holdings = ih.get('briefHoldings') or []
        return [h['oclcSymbol'] for h in holdings if h.get('oclcSymbol')]
