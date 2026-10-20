from __future__ import annotations

from datetime import date

import httpx

from app.providers.cta_plan import CTAPlanProvider, _latest_file, _parse_symbol_file


def _source_row(
    symbol: str,
    *,
    prior: str = "",
    participant: str = "N",
    test: str = "0",
    instrument_type: str = "0",
) -> str:
    fields = [
        symbol,
        prior,
        participant,
        "100.00",
        "100.00",
        "100",
        "1",
        "1",
        "1",
        test,
        "0",
        "0",
        " ",
        " ",
        instrument_type,
        "",
        "",
        "",
    ]
    return ",".join(fields)


def test_latest_file_uses_newest_published_date_not_a_guessed_calendar_day():
    index = """
      <a href='CTA.Symbol.File.20261009.csv'>Friday</a>
      <a href='CTA.Symbol.File.20261012.csv'>Monday</a>
      <a href='CTA.Symbol.File.20261014.csv'>future</a>
      <a href='CTA.Symbol.File.20261399.csv'>invalid</a>
    """

    assert _latest_file(index, today=date(2026, 10, 13)) == (
        date(2026, 10, 12),
        "CTA.Symbol.File.20261012.csv",
    )


def test_parser_maps_primary_listing_codes_and_preserves_prior_symbol():
    text = "\n".join(
        [
            _source_row("NEWCO", prior="OLDCO", participant="C"),
            _source_row("BOND1", participant="N", instrument_type="2"),
        ]
    )

    quotes, errors, total_rows = _parse_symbol_file(text)

    assert errors == []
    assert total_rows == 2
    assert len(quotes) == 1
    assert quotes[0]["symbol"] == "NEWCO"
    assert quotes[0]["exchange_mic"] == "XCIS"
    assert quotes[0]["prior_security_symbol"] == "OLDCO"
    assert quotes[0]["source_record"]["participant_id"] == "C"


def test_parser_maps_new_exchange_participants_to_current_mics():
    text = "\n".join(
        [
            _source_row("TXSE1", participant="F"),
            _source_row("24X1", participant="G"),
            _source_row("ISE1", participant="I"),
        ]
    )

    quotes, errors, _ = _parse_symbol_file(text)

    assert errors == []
    assert {row["symbol"]: row["exchange_mic"] for row in quotes} == {
        "TXSE1": "TXSE",
        "24X1": "24EQ",
        "ISE1": "XISE",
    }


def test_parser_preserves_case_distinct_source_symbols_without_collapsing_rows():
    text = "\n".join(
        [
            _source_row("TpC", participant="N"),
            _source_row("TPC", participant="N"),
        ]
    )

    quotes, errors, total_rows = _parse_symbol_file(text)

    assert errors == []
    assert total_rows == 2
    assert [row["symbol"] for row in quotes] == ["TpC", "TPC"]


def test_parser_holds_unknown_participant_without_silently_normalizing_it():
    quotes, errors, total_rows = _parse_symbol_file(_source_row("UNKNOWN", participant="?"))

    assert total_rows == 1
    assert quotes == []
    assert errors == ["row 2: unknown CTA primary-listing participant code '?'"]


def test_provider_persists_full_index_and_csv_in_its_discovery_page(monkeypatch):
    file_body = _source_row("NASDAQ1", participant="T")
    responses = [
        httpx.Response(
            200,
            text='<a href="CTA.Symbol.File.20261012.csv">daily</a>',
            request=httpx.Request("GET", "https://ftp.nyse.com/cta_symbol_files/"),
        ),
        httpx.Response(
            200,
            text=file_body,
            request=httpx.Request(
                "GET", "https://ftp.nyse.com/cta_symbol_files/CTA.Symbol.File.20261012.csv"
            ),
        ),
    ]
    calls: list[str] = []

    def get(url: str, **_kwargs):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr("app.providers.cta_plan.httpx.get", get)
    page = CTAPlanProvider().discover_universe_page("EQUITY", 0)

    assert len(calls) == 2
    assert page["total"] == 1
    assert page["complete"] is True
    assert page["source_snapshot_date"] == "2026-10-12"
    assert page["source_files"] == [
        "cta_symbol_file_index",
        "CTA.Symbol.File.20261012.csv",
    ]
    assert page["raw_source_payload"]["index_html"].startswith("<a")
    assert page["raw_source_payload"]["symbol_file_csv"] == file_body
