"""Shared fixtures for the dfulmer2 test suite.

Fixtures defined here are auto-injected into any test that requests them
by name. The fakes live here because tests in three different modules
need them.
"""
import io
from pathlib import Path

import pytest
from pymarc import MARCReader

FIXTURES = Path(__file__).parent / 'fixtures'


# ----- MARC fixture -------------------------------------------------------

@pytest.fixture
def onebib_record():
    """A pymarc.Record parsed from the committed onebib.mrc fixture."""
    with open(FIXTURES / 'onebib.mrc', 'rb') as fh:
        return next(MARCReader(fh, force_utf8=True))


# ----- WorldCat session fakes --------------------------------------------

class FakeResponse:
    """Minimal stand-in for the requests.Response objects bookops returns."""

    def __init__(self, *, json_data=None, content=b'', status_code=200):
        self._json = json_data
        self.content = content
        self.headers = {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("no JSON body set")
        return self._json


class FakeSession:
    """Stand-in for bookops_worldcat.MetadataSession.

    Tests configure the responses they want by setting public attributes
    BEFORE the WorldCatClient calls any methods. Lists of canned responses
    can be queued for sequence-of-calls tests.
    """

    def __init__(self):
        self.brief_search_responses = []   # list of FakeResponse
        self.bib_get_responses = {}        # oclcNumber → FakeResponse
        self.holdings_responses = {}       # oclcNumber → FakeResponse
        self.brief_search_calls = []
        self.bib_get_calls = []
        self.holdings_calls = []
        self.closed = False

    def brief_bibs_search(self, q, limit=50, **kwargs):
        self.brief_search_calls.append({'q': q, 'limit': limit})
        if not self.brief_search_responses:
            return FakeResponse(json_data={'numberOfRecords': 0, 'briefRecords': []})
        return self.brief_search_responses.pop(0)

    def bib_get(self, oclcNumber, **kwargs):
        self.bib_get_calls.append(oclcNumber)
        return self.bib_get_responses.get(
            str(oclcNumber),
            FakeResponse(content=b''),
        )

    def summary_holdings_search(self, oclcNumber=None, **kwargs):
        self.holdings_calls.append(oclcNumber)
        return self.holdings_responses.get(
            str(oclcNumber),
            FakeResponse(json_data={'briefRecords': []}),
        )

    def close(self):
        self.closed = True


@pytest.fixture
def fake_session():
    """A fresh FakeSession for tests that drive WorldCatClient directly."""
    return FakeSession()


@pytest.fixture
def fake_client(fake_session):
    """A WorldCatClient backed by the FakeSession."""
    from report_bibs.worldcat import WorldCatClient
    return WorldCatClient(token=object(), session_factory=lambda: fake_session)


@pytest.fixture
def make_response():
    """Return the FakeResponse class so tests can build canned responses.

    Exposed as a fixture (rather than importing directly) so the dfulmer2
    test tree doesn't depend on a `tests.conftest` module path — which
    would collide with dfulmer/tests/conftest.py when both packages share
    the `tests` package name during a repo-root pytest run.
    """
    return FakeResponse


# ----- Helpers for building MARCXML in tests -----------------------------

def make_marcxml(*, leader='00000nam a2200000 a 4500',
                 fields=()):
    """Build a minimal MARCXML document for tests.

    `fields` is a sequence of either:
      ('001', 'value')             — control field
      ('245', '10', [('a', 'X')])  — data field with indicators + subfields
    """
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<collection xmlns="http://www.loc.gov/MARC21/slim">',
        '<record>',
        f'<leader>{leader}</leader>',
    ]
    for f in fields:
        if len(f) == 2:
            tag, value = f
            out.append(f'<controlfield tag="{tag}">{value}</controlfield>')
        else:
            tag, indicators, subs = f
            ind1, ind2 = indicators[0], indicators[1]
            out.append(f'<datafield tag="{tag}" ind1="{ind1}" ind2="{ind2}">')
            for code, val in subs:
                out.append(f'<subfield code="{code}">{val}</subfield>')
            out.append('</datafield>')
    out.append('</record></collection>')
    return '\n'.join(out).encode('utf-8')


@pytest.fixture
def make_marcxml_fixture():
    """Expose the make_marcxml helper to test modules."""
    return make_marcxml
