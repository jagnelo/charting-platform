import os

import pytest

from app.services.etf_holdings_adapters import (
    ISSUER_ADAPTER_CONFIGS,
    get_holdings_adapter,
)

LIVE_BACKED_ISSUER_ADAPTERS = {
    "21shares",
    "1251_capital",
    "3fourteen",
    "abacus_global",
    "alternative_access",
    "rational",
    "dakota_wealth",
    "toews",
    "wedbush",
    "shelton",
    "scharf",
    "cohen_steers",
    "acquirers",
    "acuitas",
    "aot",
    "abrdn",
    "adaptive_investments",
    "agf",
    "advisor_shares",
    "akre",
    "allianz",
    "alliancebernstein",
    "alger",
    "allspring",
    "american_century",
    "ameriprise",
    "amplify",
    "angel_oak",
    "anfield",
    "applied_finance",
    "aptus",
    "ark",
    "arrow",
    "astoria",
    "axs",
    "bahl_gaynor",
    "baron",
    "bitwise",
    "bny_mellon",
    "bondbloxx",
    "beyond_investing",
    "brandes",
    "brown_advisory",
    "brown_brothers_harriman",
    "brookmont",
    "burney",
    "cambria",
    "cambiar",
    "calamos",
    "capital_group",
    "castleark",
    "capital_impact",
    "coinshares",
    "corgi",
    "counterpoint",
    "cullen",
    "clearshares",
    "clough",
    "davis",
    "defiance",
    "deepwater",
    "deutsche_bank",
    "diamond_hill",
    "dimensional",
    "direxion",
    "distillate",
    "doubleline",
    "eldridge",
    "eventide",
    "exchange_traded_concepts",
    "etf_architect",
    "faith_investor_services",
    "first_pacific",
    "federated_hermes",
    "fidelity",
    "oneascent",
    "first_eagle",
    "fm_investments",
    "founder",
    "first_trust",
    "franklin",
    "future_fund",
    "global_x",
    "mirae_asset",
    "groupe_bpce",
    "gqg",
    "gamco",
    "gmo",
    "goldman_sachs",
    "graniteshares",
    "grayscale",
    "hashdex",
    "hartford",
    "harbor",
    "hedgeye",
    "hennessy",
    "horizon_kinetics",
    "howard_capital",
    "inspire",
    "impax",
    "innovator",
    "invesco",
    "ishares",
    "janus_henderson",
    "jpmorgan",
    "kraneshares",
    "kurv",
    "lazard",
    "rex",
    "leuthold",
    "main_management",
    "mairs_power",
    "madison",
    "matthews",
    "miller_value",
    "motley_fool",
    "neos",
    "new_york_life",
    "northern_trust",
    "ocean_park",
    "pacer",
    "palmer_square",
    "point_bridge",
    "polen",
    "principal",
    "prudential",
    "procuream",
    "proshares",
    "rafferty",
    "rayliant",
    "renaissance_capital",
    "roundhill",
    "running_oak",
    "schwab",
    "sei",
    "simplify",
    "spdr",
    "spear",
    "sprott",
    "ssc",
    "strive",
    "swan_global",
    "tapp",
    "tiaa",
    "tcw",
    "tortoise",
    "texas_capital",
    "tuttle",
    "true_shares",
    "t_rowe_price",
    "timothy_plan",
    "tema",
    "teucrium",
    "themes",
    "us_global_investors",
    "vanguard",
    "vaneck",
    "victory",
    "virtus",
    "volatility_shares",
    "voya",
    "wahed",
    "wbi",
    "world_gold_council",
    "yorkville",
    "yieldmax",
    "zacks",
}
SEC_BACKED_SAMPLE_ADAPTERS = {
    "direxion",
    "wisdomtree",
}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_ETF_HOLDINGS_TESTS") != "1",
        reason="Set RUN_LIVE_ETF_HOLDINGS_TESTS=1 to run live issuer holdings checks.",
    ),
]


def test_live_provider_matrix_covers_every_registered_issuer_adapter():
    registered = set(ISSUER_ADAPTER_CONFIGS)

    assert LIVE_BACKED_ISSUER_ADAPTERS <= registered
    assert SEC_BACKED_SAMPLE_ADAPTERS <= registered
    for adapter_key, config in ISSUER_ADAPTER_CONFIGS.items():
        assert config.live_tested_default_route is (adapter_key in LIVE_BACKED_ISSUER_ADAPTERS)
        assert config.supports_sec_filing_fallback is True


def _assert_live_holdings_result(result, *, adapter_key: str, min_rows: int = 10):
    assert result.source_url
    assert result.rows, f"{adapter_key} returned no parseable holdings rows"
    assert len(result.rows) >= min_rows
    assert result.raw_text
    assert result.legal_metadata
    assert result.legal_metadata["adapter_key"] == adapter_key
    assert any(row.symbol or row.name or row.cusip or row.isin for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol", "issuer_product_id", "identifiers", "min_rows"),
    [
        (
            "corgi",
            "FDRS",
            None,
            {},
            20,
        ),
        (
            "capital_impact",
            "XOVR",
            None,
            {},
            20,
        ),
        (
            "alger",
            "CNEQ",
            None,
            {},
            20,
        ),
        (
            "acuitas",
            "AIMS",
            None,
            {},
            100,
        ),
        (
            "agf",
            "BTAL",
            None,
            {},
            100,
        ),
        (
            "impax",
            "BLDX",
            None,
            {},
            20,
        ),
        (
            "brown_brothers_harriman",
            "BBHL",
            None,
            {},
            20,
        ),
        (
            "wbi",
            "WBIL",
            None,
            {},
            20,
        ),
        (
            "mairs_power",
            "MINN",
            None,
            {},
            20,
        ),
        (
            "hedgeye",
            "HECA",
            None,
            {},
            20,
        ),
        (
            "polen",
            "PCLG",
            None,
            {},
            20,
        ),
        (
            "founder",
            "FFF",
            None,
            {},
            90,
        ),
        (
            "21shares",
            "ARKB",
            None,
            {},
            1,
        ),
        (
            "acquirers",
            "ZIG",
            None,
            {},
            20,
        ),
        (
            "akre",
            "AKRE",
            None,
            {},
            15,
        ),
        (
            "astoria",
            "ROE",
            None,
            {},
            100,
        ),
        (
            "groupe_bpce",
            "GQI",
            None,
            {},
            50,
        ),
        (
            "tcw",
            "ACLO",
            None,
            {},
            100,
        ),
        (
            "rayliant",
            "CNQQ",
            None,
            {},
            50,
        ),
        (
            "adaptive_investments",
            "ADPV",
            None,
            {},
            20,
        ),
        (
            "zacks",
            "ZECP",
            None,
            {},
            20,
        ),
        (
            "texas_capital",
            "TXS",
            None,
            {},
            20,
        ),
        (
            "abrdn",
            "SGOL",
            None,
            {},
            1,
        ),
        (
            "advisor_shares",
            "MSOS",
            None,
            {},
            5,
        ),
        (
            "allianz",
            "FEBT",
            None,
            {},
            5,
        ),
        (
            "alliancebernstein",
            "FWD",
            None,
            {},
            100,
        ),
        (
            "amplify",
            "BLOK",
            None,
            {},
            20,
        ),
        (
            "angel_oak",
            "AOHY",
            None,
            {},
            100,
        ),
        (
            "anfield",
            "AEMS",
            None,
            {},
            3,
        ),
        (
            "applied_finance",
            "VSLU",
            None,
            {},
            100,
        ),
        (
            "aptus",
            "DRSK",
            None,
            {},
            20,
        ),
        (
            "arrow",
            "ARCM",
            None,
            {},
            100,
        ),
        (
            "spdr",
            "SPY",
            None,
            {},
            100,
        ),
        (
            "ishares",
            "IVV",
            "239726",
            {},
            5,
        ),
        (
            "ishares",
            "EEM",
            None,
            {},
            100,
        ),
        (
            "ishares",
            "IWM",
            None,
            {},
            100,
        ),
        (
            "kraneshares",
            "KWEB",
            None,
            {},
            20,
        ),
        (
            "vaneck",
            "SMH",
            None,
            {"product_slug": "semiconductor-etf-smh"},
            20,
        ),
        (
            "american_century",
            "AVUV",
            None,
            {},
            100,
        ),
        (
            "ark",
            "ARKK",
            None,
            {},
            20,
        ),
        (
            "axs",
            "TARK",
            None,
            {},
            5,
        ),
        (
            "bahl_gaynor",
            "BGIG",
            None,
            {},
            20,
        ),
        (
            "bitwise",
            "BITB",
            None,
            {},
            1,
        ),
        (
            "bny_mellon",
            "BKAG",
            None,
            {},
            100,
        ),
        (
            "bondbloxx",
            "PCMM",
            None,
            {},
            20,
        ),
        (
            "brookmont",
            "BAMA",
            None,
            {},
            5,
        ),
        (
            "baron",
            "RONB",
            None,
            {},
            20,
        ),
        (
            "brandes",
            "BUSA",
            None,
            {},
            20,
        ),
        (
            "ocean_park",
            "DUKQ",
            None,
            {},
            5,
        ),
        (
            "beyond_investing",
            "VEGN",
            None,
            {},
            100,
        ),
        (
            "cambria",
            "SYLD",
            None,
            {},
            50,
        ),
        (
            "cambiar",
            "CAMX",
            None,
            {},
            20,
        ),
        (
            "calamos",
            "CPSM",
            None,
            {},
            3,
        ),
        (
            "castleark",
            "CARK",
            None,
            {},
            20,
        ),
        (
            "coinshares",
            "WGMI",
            None,
            {},
            10,
        ),
        (
            "counterpoint",
            "CPAI",
            None,
            {},
            50,
        ),
        (
            "capital_group",
            "CGGR",
            None,
            {},
            20,
        ),
        (
            "defiance",
            "QQQY",
            None,
            {},
            4,
        ),
        (
            "davis",
            "DUSA",
            None,
            {},
            20,
        ),
        (
            "deutsche_bank",
            "USSG",
            None,
            {},
            100,
        ),
        (
            "deepwater",
            "DBSC",
            None,
            {},
            20,
        ),
        (
            "dimensional",
            "DFAC",
            None,
            {},
            1000,
        ),
        (
            "direxion",
            "SPXL",
            None,
            {},
            100,
        ),
        (
            "doubleline",
            "DBND",
            None,
            {},
            100,
        ),
        (
            "fidelity",
            "FBCG",
            None,
            {},
            100,
        ),
        (
            "allspring",
            "ASLV",
            None,
            {},
            20,
        ),
        (
            "distillate",
            "DSTL",
            None,
            {},
            50,
        ),
        (
            "eventide",
            "ESUM",
            None,
            {},
            100,
        ),
        (
            "etf_architect",
            "QVAL",
            None,
            {},
            20,
        ),
        (
            "faith_investor_services",
            "BRIF",
            None,
            {},
            20,
        ),
        (
            "federated_hermes",
            "FTRB",
            None,
            {},
            10,
        ),
        (
            "ssc",
            "SDOG",
            None,
            {},
            10,
        ),
        (
            "oneascent",
            "OALC",
            None,
            {},
            100,
        ),
        (
            "timothy_plan",
            "TPHD",
            None,
            {},
            50,
        ),
        (
            "first_eagle",
            "FEGE",
            None,
            {},
            50,
        ),
        (
            "spear",
            "SPRX",
            None,
            {},
            20,
        ),
        (
            "fm_investments",
            "TBIL",
            None,
            {},
            2,
        ),
        (
            "invesco",
            "QQQ",
            None,
            {},
            100,
        ),
        (
            "janus_henderson",
            "JAAA",
            None,
            {},
            100,
        ),
        (
            "jpmorgan",
            "JEPI",
            "46641Q332",
            {},
            100,
        ),
        (
            "graniteshares",
            "NVD",
            None,
            {},
            1,
        ),
        (
            "gmo",
            "INVG",
            None,
            {},
            100,
        ),
        (
            "gqg",
            "GQGU",
            None,
            {},
            20,
        ),
        (
            "tiaa",
            "NULG",
            None,
            {},
            50,
        ),
        (
            "prudential",
            "PJBF",
            None,
            {},
            30,
        ),
        (
            "brown_advisory",
            "BAFE",
            None,
            {},
            20,
        ),
        (
            "first_pacific",
            "FPAG",
            None,
            {},
            20,
        ),
        (
            "gamco",
            "GCAD",
            None,
            {},
            20,
        ),
        (
            "goldman_sachs",
            "GVIP",
            None,
            {},
            20,
        ),
        (
            "grayscale",
            "GBTC",
            None,
            {},
            1,
        ),
        (
            "hashdex",
            "DEFI",
            None,
            {},
            3,
        ),
        (
            "matthews",
            "MCH",
            None,
            {},
            50,
        ),
        (
            "new_york_life",
            "IQSI",
            None,
            {},
            100,
        ),
        (
            "hartford",
            "HDUS",
            None,
            {},
            100,
        ),
        (
            "hennessy",
            "STNC",
            None,
            {},
            20,
        ),
        (
            "harbor",
            "WINN",
            None,
            {},
            50,
        ),
        (
            "horizon_kinetics",
            "INFL",
            None,
            {},
            20,
        ),
        (
            "howard_capital",
            "QQH",
            None,
            {},
            50,
        ),
        (
            "diamond_hill",
            "DHLX",
            None,
            {},
            20,
        ),
        (
            "inspire",
            "BIBL",
            None,
            {},
            50,
        ),
        (
            "neos",
            "SPYI",
            None,
            {},
            100,
        ),
        (
            "northern_trust",
            "QDF",
            None,
            {},
            100,
        ),
        (
            "pacer",
            "COWZ",
            None,
            {},
            50,
        ),
        (
            "palmer_square",
            "PSQO",
            None,
            {},
            100,
        ),
        (
            "point_bridge",
            "MAGA",
            None,
            {},
            100,
        ),
        (
            "principal",
            "PSC",
            None,
            {},
            100,
        ),
        (
            "miller_value",
            "MVPA",
            None,
            {},
            20,
        ),
        (
            "procuream",
            "UFO",
            None,
            {},
            20,
        ),
        (
            "sprott",
            "NIKL",
            None,
            {},
            10,
        ),
        (
            "kurv",
            "AAPY",
            None,
            {},
            10,
        ),
        (
            "lazard",
            "JPY",
            None,
            {},
            50,
        ),
        (
            "rex",
            "FEPI",
            None,
            {},
            50,
        ),
        (
            "leuthold",
            "LCR",
            None,
            {},
            20,
        ),
        (
            "renaissance_capital",
            "IPO",
            None,
            {},
            20,
        ),
        (
            "world_gold_council",
            "GLD",
            None,
            {},
            1,
        ),
        (
            "yorkville",
            "TSIC",
            None,
            {},
            20,
        ),
        (
            "running_oak",
            "ROEQ",
            None,
            {},
            50,
        ),
        (
            "vanguard",
            "VOO",
            None,
            {},
            100,
        ),
        (
            "innovator",
            "BALT",
            None,
            {},
            5,
        ),
        (
            "schwab",
            "SCHD",
            None,
            {},
            100,
        ),
        (
            "simplify",
            "CTA",
            None,
            {},
            5,
        ),
        (
            "strive",
            "STXF",
            None,
            {},
            20,
        ),
        (
            "swan_global",
            "HEGD",
            None,
            {},
            10,
        ),
        (
            "tapp",
            "TDAX",
            None,
            {},
            3,
        ),
        (
            "tuttle",
            "MAGO",
            None,
            {},
            20,
        ),
        (
            "true_shares",
            "ONEH",
            None,
            {},
            5,
        ),
        (
            "t_rowe_price",
            "TCHP",
            None,
            {},
            50,
        ),
        (
            "proshares",
            "TQQQ",
            None,
            {},
            100,
        ),
        (
            "first_trust",
            "QQEW",
            None,
            {},
            20,
        ),
        (
            "franklin",
            "FLQL",
            None,
            {},
            100,
        ),
        (
            "future_fund",
            "FFOX",
            None,
            {},
            20,
        ),
        (
            "madison",
            "CVRD",
            None,
            {},
            20,
        ),
        (
            "motley_fool",
            "TMFC",
            None,
            {},
            50,
        ),
        (
            "roundhill",
            "MAGS",
            None,
            {},
            20,
        ),
        (
            "teucrium",
            "CORN",
            None,
            {},
            3,
        ),
        (
            "tema",
            "TOLL",
            None,
            {},
            20,
        ),
        (
            "themes",
            "SPAM",
            None,
            {},
            20,
        ),
        (
            "us_global_investors",
            "JETS",
            None,
            {},
            20,
        ),
        (
            "victory",
            "VFLO",
            None,
            {},
            20,
        ),
        (
            "voya",
            "VMSB",
            None,
            {},
            100,
        ),
        (
            "virtus",
            "SSMG",
            None,
            {},
            50,
        ),
        (
            "burney",
            "BRNY",
            None,
            {},
            50,
        ),
        (
            "cullen",
            "DIVP",
            None,
            {},
            20,
        ),
        (
            "volatility_shares",
            "SVIX",
            None,
            {},
            3,
        ),
        (
            "clearshares",
            "OPER",
            None,
            {},
            5,
        ),
        (
            "clough",
            "CBSE",
            None,
            {},
            20,
        ),
        (
            "main_management",
            "BUYW",
            None,
            {},
            10,
        ),
        (
            "wahed",
            "HLAL",
            None,
            {},
            50,
        ),
        (
            "yieldmax",
            "TSLY",
            None,
            {},
            10,
        ),
        (
            "tortoise",
            "TPZ",
            None,
            {},
            20,
        ),
    ],
)
async def test_live_issuer_direct_holdings_routes_return_parseable_rows(
    adapter_key,
    symbol,
    issuer_product_id,
    identifiers,
    min_rows,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    result = await adapter.fetch_latest(
        symbol=symbol,
        issuer_product_id=issuer_product_id,
        identifiers=identifiers,
    )

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=min_rows)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol", "identifiers"),
    [
        (
            "global_x",
            "QYLD",
            {},
        ),
        (
            "mirae_asset",
            "QYLD",
            {},
        ),
    ],
)
async def test_live_issuer_product_pages_discover_parseable_holdings_files(
    adapter_key,
    symbol,
    identifiers,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    result = await adapter.fetch_latest(symbol=symbol, identifiers=identifiers)

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=5)
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_sei_dated_daily_holdings_export():
    adapter = get_holdings_adapter("sei")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="SEIS")

    _assert_live_holdings_result(result, adapter_key="sei", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "issuer_dated_daily_holdings_export"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_ameriprise_columbia_threadneedle_cusip_holdings_export():
    adapter = get_holdings_adapter("ameriprise")
    assert adapter is not None

    result = await adapter.fetch_latest(
        symbol="XCEM",
        identifiers={"cusip": "19762B202"},
    )

    _assert_live_holdings_result(result, adapter_key="ameriprise", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "ameriprise_columbia_cusip_holdings_csv"
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_1251_capital_owned_fm_investments_holdings_api():
    adapter = get_holdings_adapter("1251_capital")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="UTWO")

    _assert_live_holdings_result(result, adapter_key="1251_capital", min_rows=2)
    assert result.legal_metadata["route_resolution"] == (
        "1251_capital_fm_investments_holdings_api"
    )
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_rafferty_direxion_daily_holdings_export():
    adapter = get_holdings_adapter("rafferty")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="COM")

    _assert_live_holdings_result(result, adapter_key="rafferty", min_rows=5)
    assert result.legal_metadata["route_resolution"] == "rafferty_direxion_symbol_holdings_csv"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_exchange_traded_concepts_bluemonte_fund_page_payload():
    adapter = get_holdings_adapter("exchange_traded_concepts")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="BLUC")

    _assert_live_holdings_result(result, adapter_key="exchange_traded_concepts", min_rows=3)
    assert result.legal_metadata["route_resolution"] == (
        "exchange_traded_concepts_bluemonte_fund_page_payload"
    )
    assert any(row.extra_data.get("figi") for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_aot_invest_public_product_page_holdings_table():
    adapter = get_holdings_adapter("aot")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="AOTG")

    _assert_live_holdings_result(result, adapter_key="aot", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "aot_invest_public_product_page_holdings_table"
    )
    assert all(row.extra_data.get("market_value_unit") == "millions_usd" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_3fourteen_public_product_page_holdings_table():
    adapter = get_holdings_adapter("3fourteen")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="FCTE")

    _assert_live_holdings_result(result, adapter_key="3fourteen", min_rows=15)
    assert result.legal_metadata["route_resolution"] == (
        "smi_3fourteen_public_product_page_holdings_table"
    )
    assert result.legal_metadata["composition_date"]
    security_rows = [row for row in result.rows if row.row_type == "security"]
    assert security_rows
    assert all(row.extra_data.get("figi") for row in security_rows)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_abacus_global_product_page_linked_daily_holdings_csv():
    adapter = get_holdings_adapter("abacus_global")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="ABLG")

    _assert_live_holdings_result(result, adapter_key="abacus_global", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "abacus_fcf_product_page_linked_daily_holdings_csv"
    )
    assert result.legal_metadata["composition_date"]
    assert result.source_url.endswith("/ABLG_allHoldings.csv")


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_alternative_access_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("alternative_access")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="AAA")

    _assert_live_holdings_result(result, adapter_key="alternative_access", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "alternative_access_product_page_linked_holdings_xlsx"
    )
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "xlsx"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_rational_risk_parity_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("rational")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="RPAR")

    _assert_live_holdings_result(result, adapter_key="rational", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "rational_rpar_product_page_linked_holdings_xlsx"
    )
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "xlsx"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_toews_product_page_linked_holdings_csv():
    adapter = get_holdings_adapter("toews")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="HRSK")

    _assert_live_holdings_result(result, adapter_key="toews", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "toews_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "csv"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_wedbush_symbol_holdings_csv():
    adapter = get_holdings_adapter("wedbush")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="TGLR")

    _assert_live_holdings_result(result, adapter_key="wedbush", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "wedbush_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_shelton_product_page_linked_holdings_csv():
    adapter = get_holdings_adapter("shelton")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="SEPI")
    _assert_live_holdings_result(result, adapter_key="shelton", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "shelton_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_scharf_product_page_linked_holdings_csv():
    adapter = get_holdings_adapter("scharf")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="KAT")
    _assert_live_holdings_result(result, adapter_key="scharf", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "scharf_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "csv"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_cohen_steers_public_fund_api():
    adapter = get_holdings_adapter("cohen_steers")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="CSRE")
    _assert_live_holdings_result(result, adapter_key="cohen_steers", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "cohen_steers_public_fund_api"
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "json"




@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_eldridge_combined_daily_holdings_file_filters_requested_etf():
    adapter = get_holdings_adapter("eldridge")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="CLOX")

    _assert_live_holdings_result(result, adapter_key="eldridge", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "issuer_combined_daily_holdings_csv"
    assert result.legal_metadata["composition_date"]
    assert all(row.extra_data.get("Account") == "CLOX" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol"),
    [
        ("wisdomtree", "DXJ"),
    ],
)
async def test_live_sec_backed_adapters_probe_ready_with_sec_identifiers(
    adapter_key,
    symbol,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    probe = adapter.probe(
        symbol=symbol,
        name="",
        identifiers={"sec_cik": "0000036405"},
    )

    assert not ISSUER_ADAPTER_CONFIGS[adapter_key].live_tested_default_route
    assert probe.status == "ready"
    assert probe.source_url == "https://data.sec.gov/submissions/CIK0000036405.json"
