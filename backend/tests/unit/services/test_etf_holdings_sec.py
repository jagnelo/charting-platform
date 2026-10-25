from datetime import date
from decimal import Decimal

import pytest

from app.services.etf_holdings_sec import (
    _first_date_like_text,
    _parse_date,
    extract_sec_nport_filing_identity,
    parse_sec_legacy_holdings_xml,
    parse_sec_nport_xml,
)


def test_extract_sec_nport_filing_identity_reads_rendered_identity_tables():
    raw_xhtml = """
    <html><body>
      <table>
        <tr><td>Series ID</td><td><div>S000058757</div></td></tr>
        <tr><td>Class (Contract) ID</td><td><div>C000192803</div></td></tr>
      </table>
      <table>
        <tr><td>a. Name of Series.</td><td><div>Point Bridge America First ETF</div></td></tr>
      </table>
    </body></html>
    """

    assert extract_sec_nport_filing_identity(raw_xhtml) == {
        "series_id": "S000058757",
        "class_id": "C000192803",
        "series_name": "Point Bridge America First ETF",
    }


def test_extract_sec_nport_filing_identity_reads_registrant_name_from_xml():
    raw_xml = """
    <edgarSubmission><formData><genInfo>
      <regName>State Street(R) SPDR(R) S&amp;P 500(R) ETF Trust</regName>
      <seriesName>N/A</seriesName>
    </genInfo></formData></edgarSubmission>
    """

    assert extract_sec_nport_filing_identity(raw_xml) == {
        "registrant_name": "State Street(R) SPDR(R) S&P 500(R) ETF Trust",
        "series_name": "N/A",
    }


def test_parse_sec_nport_xml_parses_security_rows_and_report_date():
    raw_xml = """
    <edgarSubmission>
      <formData>
        <genInfo>
          <repPdDate>2026-05-31</repPdDate>
        </genInfo>
        <invstOrSecs>
          <invstOrSec>
            <name>Apple Inc.</name>
            <cusip>037833100</cusip>
            <ticker>AAPL</ticker>
            <assetCat>Equity</assetCat>
            <pctVal>6.5</pctVal>
            <balance>10</balance>
            <valUSD>2000</valUSD>
            <curCd>USD</curCd>
          </invstOrSec>
          <invstOrSec>
            <name>Cash</name>
            <assetCat>Cash</assetCat>
            <pctVal>1.0</pctVal>
            <balance>100</balance>
            <valUSD>100</valUSD>
            <curCd>USD</curCd>
          </invstOrSec>
        </invstOrSecs>
      </formData>
    </edgarSubmission>
    """

    report_date, rows = parse_sec_nport_xml(raw_xml)

    assert report_date == date(2026, 5, 31)
    assert len(rows) == 2
    assert rows[0].symbol == "AAPL"
    assert rows[0].weight == Decimal("0.065")
    assert rows[1].row_type == "cash"


def test_parse_sec_nport_xml_falls_back_to_xhtml_schedule_blocks():
    raw_xhtml = """
    <!DOCTYPE html>
    <html>
      <body>
        <p>Report for March 31, 2026</p>
        <h4>Item C.1. Identification of investment.</h4>
        <table>
          <tr><td class="label">a. Name of issuer (if any).</td><td><div class="fakeBox">NVIDIA Corp.<span>&nbsp;</span></div></td></tr>
          <tr><td class="label">d. CUSIP (if any).</td><td><div class="fakeBox">67066G104<span>&nbsp;</span></div></td></tr>
        </table>
        <table>
          <tr><td class="label">Identifier.</td><td><div class="fakeBox3"><span>ISIN</span></div></td></tr>
          <tr><td class="label">ISIN</td><td><div class="fakeBox3">US67066G1040<span>&nbsp;</span></div></td></tr>
        </table>
        <table>
          <tr><td class="label">Balance</td><td><div class="fakeBox4">185426246.00000000<span>&nbsp;</span></div></td></tr>
          <tr><td class="label">Currency. Indicate the currency in which the investment is denominated.</td><td><div class="fakeBox4">United States Dollar<span>&nbsp;</span></div></td></tr>
          <tr><td class="label">Value. Report values in U.S. dollars.</td><td><div class="fakeBox4">32338337302.40000000<span>&nbsp;</span></div></td></tr>
          <tr><td class="label">Percentage value compared to net assets of the Fund.</td><td><div class="fakeBox4">8.12<span>&nbsp;</span></div></td></tr>
        </table>
      </body>
    </html>
    """

    report_date, rows = parse_sec_nport_xml(raw_xhtml)

    assert report_date is None
    assert len(rows) == 1
    assert rows[0].name == "NVIDIA Corp."
    assert rows[0].cusip == "67066G104"
    assert rows[0].isin == "US67066G1040"
    assert rows[0].shares == Decimal("185426246.00000000")
    assert rows[0].market_value == Decimal("32338337302.40000000")
    assert rows[0].weight == Decimal("0.0812")
    assert rows[0].currency == "USD"


def test_parse_sec_nport_xml_normalizes_canadian_dollar_currency_names():
    raw_xml = """
    <edgarSubmission>
      <formData>
        <genInfo>
          <repPdDate>2026-05-31</repPdDate>
        </genInfo>
        <invstOrSecs>
          <invstOrSec>
            <name>Shopify Inc.</name>
            <cusip>82509L107</cusip>
            <assetCat>Equity</assetCat>
            <pctVal>1.5</pctVal>
            <balance>10</balance>
            <valUSD>2000</valUSD>
            <curCd>Canada Dollar</curCd>
          </invstOrSec>
        </invstOrSecs>
      </formData>
    </edgarSubmission>
    """

    report_date, rows = parse_sec_nport_xml(raw_xml)

    assert report_date == date(2026, 5, 31)
    assert len(rows) == 1
    assert rows[0].currency == "CAD"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.648126277059", "0.00648126277059"),
        ("1", "0.01"),
        ("6.5", "0.065"),
        ("0", "0"),
        ("-0.25", "-0.0025"),
        ("0.65%", "0.0065"),
    ],
)
@pytest.mark.parametrize("rendered", [False, True], ids=["xml", "xhtml"])
def test_nport_percentage_fields_always_convert_percent_units_to_fraction(
    value, expected, rendered
):
    if rendered:
        raw = f"""
        <!DOCTYPE html>
        <html><body><h4>Item C.1. Identification of investment.</h4>
          <table>
            <tr><td>a. Name of issuer (if any).</td><td>Example Corp<span>&nbsp;</span></td></tr>
            <tr><td>Percentage value compared to net assets of the Fund.</td><td>{value}</td></tr>
            <tr><td>Asset category.</td><td>Equity-common</td></tr>
          </table>
        </body></html>
        """
    else:
        raw = f"""
        <edgarSubmission><formData><invstOrSecs><invstOrSec>
          <name>Example Corp</name><assetCat>EC</assetCat><pctVal>{value}</pctVal>
        </invstOrSec></invstOrSecs></formData></edgarSubmission>
        """

    _, rows = parse_sec_nport_xml(raw)

    assert len(rows) == 1
    assert rows[0].weight == Decimal(expected)
    assert rows[0].holding_type == "common_stock"
    if rendered:
        assert rows[0].extra_data["sec_asset_category"] == "Equity-common"


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("EC", "common_stock"),
        ("Equity-common", "common_stock"),
        ("EP", "preferred_stock"),
        ("Equity-preferred", "preferred_stock"),
        ("DE", "de"),
        ("DBT", "dbt"),
        ("STIV", "stiv"),
    ],
)
def test_nport_normalizes_only_common_and_preferred_equity_categories(category, expected):
    raw = f"""
    <edgarSubmission><formData><invstOrSecs><invstOrSec>
      <name>Example Corp</name><assetCat>{category}</assetCat><pctVal>0.5</pctVal>
    </invstOrSec></invstOrSecs></formData></edgarSubmission>
    """

    _, rows = parse_sec_nport_xml(raw)

    assert rows[0].holding_type == expected
    assert rows[0].extra_data["assetCat"] == category


def test_nport_generic_weight_alias_remains_fraction_valued():
    raw = """
    <edgarSubmission><formData><invstOrSecs><invstOrSec>
      <name>Example Corp</name><assetCat>EC</assetCat><weight>0.6481</weight>
    </invstOrSec></invstOrSecs></formData></edgarSubmission>
    """

    _, rows = parse_sec_nport_xml(raw)

    assert rows[0].weight == Decimal("0.6481")


def test_nport_asset_conditional_other_right_is_retained_as_non_equity():
    raw = """
    <edgarSubmission xmlns="urn:sec:nport"><formData><invstOrSecs><invstOrSec>
      <name>OmniAb, Inc.</name><cusip>00165C104</cusip>
      <valUSD>1000</valUSD><pctVal>0.25</pctVal>
      <assetConditional assetCat="OTHER" desc="Right" />
    </invstOrSec></invstOrSecs></formData></edgarSubmission>
    """

    _, rows = parse_sec_nport_xml(raw)

    assert len(rows) == 1
    assert rows[0].holding_type == "other"
    assert rows[0].row_type == "security"
    assert rows[0].extra_data["sec_asset_category"] == "OTHER"
    assert rows[0].extra_data["sec_asset_conditionals"] == [{"assetCat": "OTHER", "desc": "Right"}]


def test_real_iwm_nport_percent_excerpt_preserves_public_source_provenance():
    # These selected values are from the retained official filing artifact
    # https://www.sec.gov/Archives/edgar/data/1100663/000207169126012507/primary_doc.xml,
    # accession 0002071691-26-012507 (raw SHA256 48befdf670e0a0258dfbb8b67489e964827fdf041cdabec657cd14a71a8a632c).
    # SEC Form N-PORT Item C.2.d reports percentage value; Item C.4 identifies EC as Equity-common.
    raw = """
    <edgarSubmission><formData><genInfo><repPdDate>2026-03-31</repPdDate></genInfo>
      <invstOrSecs>
        <invstOrSec><name>Radian Group, Inc.</name><cusip>750236101</cusip>
          <valUSD>109830892.80000000</valUSD><pctVal>0.152721985047</pctVal><assetCat>EC</assetCat>
        </invstOrSec>
        <invstOrSec><name>Coeur Mining, Inc.</name><cusip>192108504</cusip>
          <valUSD>466103735.06000000</valUSD><pctVal>0.648126277059</pctVal><assetCat>EC</assetCat>
        </invstOrSec>
      </invstOrSecs>
    </formData></edgarSubmission>
    """

    report_date, rows = parse_sec_nport_xml(raw)

    assert report_date == date(2026, 3, 31)
    assert [(row.name, row.cusip, row.weight, row.holding_type) for row in rows] == [
        ("Radian Group, Inc.", "750236101", Decimal("0.00152721985047"), "common_stock"),
        ("Coeur Mining, Inc.", "192108504", Decimal("0.00648126277059"), "common_stock"),
    ]


def test_parse_sec_legacy_holdings_xml_parses_xml_rows():
    raw_xml = """
    <portfolio>
      <reportDate>2026-04-30</reportDate>
      <holding>
        <issuerName>Microsoft Corp</issuerName>
        <cusip>594918104</cusip>
        <ticker>MSFT</ticker>
        <shares>8</shares>
        <valueUSD>3200</valueUSD>
        <percentageOfNetAssets>5.4</percentageOfNetAssets>
      </holding>
    </portfolio>
    """

    report_date, rows = parse_sec_legacy_holdings_xml(raw_xml)

    assert report_date == date(2026, 4, 30)
    assert len(rows) == 1
    assert rows[0].symbol == "MSFT"
    assert rows[0].weight == Decimal("0.054")
    assert rows[0].market_value == Decimal("3200")


def test_parse_sec_legacy_holdings_xml_falls_back_to_html_split_rows_and_thousands():
    raw_html = """
    <html>
      <body>
        <p>Schedule of Investments May 31, 2026</p>
        <table>
          <tr>
            <th>Issuer</th>
            <th>CUSIP</th>
            <th>Shares</th>
            <th>Value (000)</th>
            <th>% Net Assets</th>
          </tr>
          <tr>
            <td>Apple Inc.</td>
            <td>037833100</td>
            <td></td>
            <td></td>
            <td></td>
          </tr>
          <tr>
            <td></td>
            <td></td>
            <td>10</td>
            <td>2</td>
            <td>6.1%</td>
          </tr>
          <tr>
            <td>Microsoft Corp</td>
            <td>594918104</td>
            <td>8</td>
            <td>3</td>
            <td>5.4%</td>
          </tr>
        </table>
      </body>
    </html>
    """

    report_date, rows = parse_sec_legacy_holdings_xml(raw_html)

    assert report_date == date(2026, 5, 31)
    assert len(rows) == 2
    assert rows[0].name == "Apple Inc."
    assert rows[0].market_value == Decimal("2000")
    assert rows[0].weight == Decimal("0.061")
    assert rows[1].cusip == "594918104"


def test_date_helpers_support_month_name_dates():
    text = "As of September 30, 2025 the fund held the following investments."
    assert _first_date_like_text(text) == "2025-09-30"
    assert _parse_date(_first_date_like_text(text)) == date(2025, 9, 30)
    assert _parse_date("2025-09-30") == date(2025, 9, 30)
