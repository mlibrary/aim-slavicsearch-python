"""Tests for report_bibs.bib.Bib.

These tests run against the onebib.mrc fixture (a single MARC record copied
from dfulmer/tests/fixtures/). When a test needs a different MARC shape
(missing field, malformed indicator), it mutates the fixture record using
pymarc.Field and Subfield builders.
"""
from pymarc import Field, Subfield

from report_bibs.bib import Bib


# ----- Identifiers and 008 -----------------------------------------------

def test_oclc_number_strips_prefix(onebib_record):
    # The onebib fixture's 001 doesn't have an ocm prefix, but the regex
    # should leave it intact.
    bib = Bib(onebib_record)
    assert bib.oclc_number == '990186423140106381'


def test_f008_returns_string_or_empty(onebib_record):
    bib = Bib(onebib_record)
    assert isinstance(bib.f008, str)
    assert len(bib.f008) > 0


def test_language_slices_bytes_35_to_38(onebib_record):
    bib = Bib(onebib_record)
    # onebib.mrc has 'arm' (Armenian) at 008/35-37
    assert bib.language == 'arm'


def test_language_empty_when_008_missing(onebib_record):
    onebib_record.remove_fields('008')
    bib = Bib(onebib_record)
    assert bib.language == ''
    assert bib.f008 == ''


def test_country_code_slices_bytes_15_to_18(onebib_record):
    bib = Bib(onebib_record)
    # The fixture's country code is in 008[15:18]; just check it's 3 chars
    assert len(bib.country_code) == 3


# ----- Format / leader-based ---------------------------------------------

def test_record_format_returns_bk_for_book(onebib_record):
    # The fixture is a book (leader[6]='a', leader[7]='m')
    bib = Bib(onebib_record)
    assert bib.record_format == 'BK'


def test_encoding_level_returns_leader_position_17(onebib_record):
    bib = Bib(onebib_record)
    assert bib.encoding_level == str(onebib_record.leader)[17]


# ----- Title 245 ----------------------------------------------------------

def test_title_ab_extracts_a_and_b(onebib_record):
    bib = Bib(onebib_record)
    # The fixture's title starts with "Chʻspiatsʻats verkʻ"
    assert 'Ch' in bib.title_ab
    assert 'verkʻ' in bib.title_ab


def test_has_245h_false_when_no_h(onebib_record):
    bib = Bib(onebib_record)
    assert bib.has_245h == 0


def test_has_245h_true_when_h_present(onebib_record):
    # Inject a $h into the 245 field
    f245 = onebib_record.get_fields('245')[0]
    f245.add_subfield('h', '[electronic resource]')
    bib = Bib(onebib_record)
    assert bib.has_245h == 1
    assert 'electronic' in bib.title_h_value


# ----- Author 1xx ---------------------------------------------------------

def test_first_1xx_field_is_100(onebib_record):
    bib = Bib(onebib_record)
    assert bib.first_1xx_field is not None
    assert bib.first_1xx_field.tag == '100'


def test_author_100_value_returns_subfield_a(onebib_record):
    bib = Bib(onebib_record)
    assert bib.author_100_value.startswith('Alajajyan')


def test_author_value_returns_none_string_when_no_1xx(onebib_record):
    # Strip all 1xx fields
    for tag in ('100', '110', '111', '130'):
        onebib_record.remove_fields(tag)
    bib = Bib(onebib_record)
    assert bib.author_value == 'none'


# ----- Publication date ---------------------------------------------------

def test_pub_date_prefers_260c(onebib_record):
    bib = Bib(onebib_record)
    date, source = bib.pub_date
    assert source == '260'
    assert date.startswith('2019')


def test_pub_date_falls_back_to_008(onebib_record):
    onebib_record.remove_fields('260')
    bib = Bib(onebib_record)
    date, source = bib.pub_date
    assert source == '008'
    assert date == '2019'


# ----- get_bib_data static helper ----------------------------------------

def test_get_bib_data_with_indicator_filter(onebib_record):
    # Add a 264 field with ind1=' ', ind2='1' (publication)
    onebib_record.add_field(Field(
        tag='264',
        indicators=[' ', '1'],
        subfields=[Subfield(code='c', value='2024.')]
    ))
    # '264#1' should match (# = any ind1, 1 = ind2)
    assert Bib.get_bib_data(onebib_record, '264#1', 'c') == '2024.'
    # '264#2' should not match
    assert Bib.get_bib_data(onebib_record, '264#2', 'c') == ''


# ----- passes_field_checks -----------------------------------------------

def test_passes_field_checks_true_for_fixture(onebib_record):
    bib = Bib(onebib_record)
    assert bib.passes_field_checks is True


def test_passes_field_checks_false_when_008_23_not_blank(onebib_record):
    # Mutate the 008 to put a non-blank at position 23
    f008 = onebib_record.get_fields('008')[0]
    val = f008.value()
    f008.data = val[:23] + 'X' + val[24:]
    bib = Bib(onebib_record)
    assert bib.passes_field_checks is False


def test_passes_field_checks_false_when_040b_non_english(onebib_record):
    # Remove any pre-existing 040 from the fixture so our injected field wins
    onebib_record.remove_fields('040')
    onebib_record.add_field(Field(
        tag='040',
        indicators=[' ', ' '],
        subfields=[Subfield(code='b', value='fre')]
    ))
    bib = Bib(onebib_record)
    assert bib.passes_field_checks is False


# ----- Cataloging source fields ------------------------------------------

def test_is_dlc_false_without_050(onebib_record):
    bib = Bib(onebib_record)
    assert bib.is_dlc is False


def test_is_pcc_false_without_042(onebib_record):
    bib = Bib(onebib_record)
    assert bib.is_pcc is False
