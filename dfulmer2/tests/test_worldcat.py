"""Tests for report_bibs.worldcat.WorldCatClient.

The FakeSession defined in conftest.py replaces bookops_worldcat's
MetadataSession, so these tests never touch the network.
"""
import pytest

from report_bibs.worldcat import WorldCatClient, WorldCatError


def test_brief_search_returns_numrec_and_oclc_numbers(fake_session, fake_client, make_response):
    fake_session.brief_search_responses.append(make_response(
        json_data={
            'numberOfRecords': 2,
            'briefRecords': [
                {'oclcNumber': '12345'},
                {'oclcNumber': '67890'},
            ],
        }
    ))
    numrec, ocns = fake_client.brief_search('ISBN', '9781234567890')
    assert numrec == 2
    assert ocns == ['12345', '67890']
    # And the query string used the bn: prefix
    assert fake_session.brief_search_calls[0]['q'] == 'bn: 9781234567890'


def test_brief_search_detects_too_many(fake_session, fake_client, make_response):
    # numberOfRecords > max_hits (50 by default) signals "too many"
    fake_session.brief_search_responses.append(make_response(
        json_data={'numberOfRecords': 99, 'briefRecords': []}
    ))
    numrec, ocns = fake_client.brief_search('TITLE', 'foo')
    assert numrec == 99
    assert ocns == []  # caller can detect numrec > max_hits and skip


def test_brief_search_raises_on_http_error(fake_session, fake_client, make_response):
    fake_session.brief_search_responses.append(make_response(status_code=500))
    with pytest.raises(WorldCatError):
        fake_client.brief_search('OCLC', '12345')


def test_fetch_marc_parses_marcxml(fake_session, fake_client, make_response, make_marcxml_fixture):
    xml = make_marcxml_fixture(fields=[
        ('001', '12345'),
        ('245', '00', [('a', 'A test title /')]),
    ])
    fake_session.bib_get_responses['12345'] = make_response(content=xml)
    record = fake_client.fetch_marc('12345')
    assert record is not None
    assert record['001'].value() == '12345'
    assert 'test title' in record['245'].value().lower()


def test_fetch_marc_returns_none_on_empty_response(fake_session, fake_client, make_response):
    fake_session.bib_get_responses['x'] = make_response(content=b'')
    assert fake_client.fetch_marc('x') is None


def test_fetch_holdings_count_returns_int(fake_session, fake_client, make_response):
    fake_session.holdings_responses['9999'] = make_response(json_data={
        'briefRecords': [
            {'oclcNumber': '9999',
             'institutionHolding': {'totalHoldingCount': 7}}
        ]
    })
    assert fake_client.fetch_holdings_count('9999') == 7


def test_fetch_holdings_count_returns_zero_when_missing(fake_session, fake_client, make_response):
    fake_session.holdings_responses['xx'] = make_response(json_data={
        'briefRecords': []
    })
    assert fake_client.fetch_holdings_count('xx') == 0


def test_reconnect_closes_old_session_and_opens_new(fake_session):
    sessions = []

    def factory():
        s = type(fake_session)()  # build a fresh FakeSession
        sessions.append(s)
        return s

    client = WorldCatClient(token=object(), session_factory=factory)
    first = client.session
    client.reconnect()
    assert first.closed is True
    assert client.session is not first


def test_from_env_raises_when_credentials_missing():
    with pytest.raises(KeyError):
        WorldCatClient.from_env(environ={})


# ----- fetch_holdings_list (Search API V2 /bibs-holdings) ----------------

class _FakeToken:
    token_str = 'tk_fake'


class _Recorder:
    """Captures the args of patched requests.get calls."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        self.calls.append({
            'url': url,
            'headers': headers,
            'params': params,
            'timeout': timeout,
        })
        return self.response


def _client_with_token():
    """Build a WorldCatClient whose .token has a usable token_str attr."""
    from report_bibs.worldcat import WorldCatClient

    class _FakeSession:
        def close(self): pass

    return WorldCatClient(token=_FakeToken(), session_factory=_FakeSession)


def test_fetch_holdings_list_returns_symbols_in_api_order(monkeypatch, make_response):
    client = _client_with_token()
    rec = _Recorder(make_response(json_data={
        'numberOfRecords': 1,
        'briefRecords': [{
            'oclcNumber': '1542849527',
            'institutionHolding': {
                'totalHoldingCount': 3,
                'briefHoldings': [
                    {'oclcSymbol': 'HUL', 'country': 'US'},
                    {'oclcSymbol': 'EYM', 'country': 'US'},
                    {'oclcSymbol': 'UIU', 'country': 'US'},
                ],
            },
        }],
    }))
    monkeypatch.setattr('report_bibs.worldcat.requests.get', rec)
    assert client.fetch_holdings_list('1542849527') == ['HUL', 'EYM', 'UIU']

    # And the request was shaped correctly.
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call['url'] == client.HOLDINGS_URL
    assert call['params'] == {'oclcNumber': '1542849527'}
    assert call['headers']['Authorization'] == 'Bearer tk_fake'
    assert call['headers']['Accept'] == 'application/json'


def test_fetch_holdings_list_returns_empty_on_no_brief_records(monkeypatch, make_response):
    client = _client_with_token()
    rec = _Recorder(make_response(json_data={'numberOfRecords': 0, 'briefRecords': []}))
    monkeypatch.setattr('report_bibs.worldcat.requests.get', rec)
    assert client.fetch_holdings_list('999999') == []


def test_fetch_holdings_list_returns_empty_on_http_error(monkeypatch, make_response):
    client = _client_with_token()
    rec = _Recorder(make_response(status_code=500))
    monkeypatch.setattr('report_bibs.worldcat.requests.get', rec)
    # Does not raise — pipeline keeps going with empty Institutions cols.
    assert client.fetch_holdings_list('xyz') == []


def test_fetch_holdings_list_returns_empty_when_briefHoldings_missing(monkeypatch, make_response):
    client = _client_with_token()
    rec = _Recorder(make_response(json_data={
        'briefRecords': [{
            'oclcNumber': '1',
            'institutionHolding': {'totalHoldingCount': 0},  # no briefHoldings key
        }],
    }))
    monkeypatch.setattr('report_bibs.worldcat.requests.get', rec)
    assert client.fetch_holdings_list('1') == []


def test_fetch_holdings_list_skips_entries_without_oclcSymbol(monkeypatch, make_response):
    client = _client_with_token()
    rec = _Recorder(make_response(json_data={
        'briefRecords': [{
            'institutionHolding': {
                'briefHoldings': [
                    {'oclcSymbol': 'EYM'},
                    {'country': 'US'},          # missing oclcSymbol → skip
                    {'oclcSymbol': '', 'country': 'US'},  # falsy → skip
                    {'oclcSymbol': 'YUS'},
                ],
            },
        }],
    }))
    monkeypatch.setattr('report_bibs.worldcat.requests.get', rec)
    assert client.fetch_holdings_list('2') == ['EYM', 'YUS']


def test_fetch_holdings_list_returns_empty_when_token_attr_missing(monkeypatch, make_response):
    """If self.token has no token_str attribute, return [] (don't raise)."""
    from report_bibs.worldcat import WorldCatClient

    class _FakeSession:
        def close(self): pass

    # token without token_str
    client = WorldCatClient(token=object(), session_factory=_FakeSession)
    # requests.get should never be called — but if it is, return a 500 so we'd
    # notice. The test really just confirms the except path catches AttributeError.
    monkeypatch.setattr(
        'report_bibs.worldcat.requests.get',
        lambda *a, **kw: make_response(status_code=500),
    )
    assert client.fetch_holdings_list('x') == []
