from datetime import date
from decimal import Decimal

from app.services.etf_holdings_sec import (
    _first_date_like_text,
    _parse_date,
    parse_sec_legacy_holdings_xml,
    parse_sec_nport_xml,
)


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
