import os
from datetime import date

import pytest

from app.services.etf_holdings_adapters import (
    ISSUER_ADAPTER_CONFIGS,
    get_holdings_adapter,
)

LIVE_BACKED_ISSUER_ADAPTERS = {
    "818",
    "arlington",
    "21shares",
    "amun",
    "1251_capital",
    "3fourteen",
    "abacus_global",
    "acp_horizon",
    "advent_capital",
    "archer_investment",
    "alternative_access",
    "rational",
    "dakota_wealth",
    "dana",
    "dawn_global",
    "envestnet",
    "amerilife",
    "marygold",
    "soundwatch",
    "equitable",
    "estate_counselors",
    "sound_capital",
    "sovereign",
    "wealthtrust",
    "wedbush",
    "shelton",
    "tidal",
    "scharf",
    "cohanzick",
    "tremblant",
    "cohen_steers",
    "acquirers",
    "infrastructure_capital",
    "acuitas",
    "aot",
    "alerian",
    "abrdn",
    "acsi_funds",
    "oakmark",
    "oshares",
    "range",
    "academy",
    "impact_shares",
    "leverage_shares",
    "absolute_investment_advisers",
    "adaptive_investments",
    "affiliated_managers_group",
    "agf",
    "ag_financial",
    "albert_mason",
    "alexis",
    "artemis",
    "ars",
    "avory",
    "beehive",
    "blueprint",
    "bridgeway",
    "unlimited",
    "webs",
    "waverly",
    "swp",
    "lagan",
    "congress",
    "beacon_capital",
    "retireful",
    "resolute",
    "american_beacon",
    "srn",
    "myriad",
    "reckoner",
    "redbird",
    "redwood",
    "rex",
    "reflection",
    "nightview",
    "gladius",
    "guardian",
    "shariaportfolio",
    "sp_funds",
    "x_square",
    "advisor_shares",
    "akre",
    "allianz",
    "alliancebernstein",
    "alger",
    "allspring",
    "american_century",
    "avantis",
    "ameriprise",
    "columbia_threadneedle",
    "amplify",
    "angel_oak",
    "applied_finance",
    "aptus",
    "araq",
    "day_hagan",
    "ark",
    "arrow",
    "astoria",
    "axs",
    "tradr",
    "bahl_gaynor",
    "baird",
    "barclays",
    "baron",
    "belpointe",
    "bluemonte",
    "bmo",
    "bcp_cc",
    "build",
    "bitwise",
    "bny_mellon",
    "bondbloxx",
    "brookfield",
    "beyond_investing",
    "brandes",
    "brown_advisory",
    "brown_brothers_harriman",
    "brookmont",
    "brookstone",
    "bufferlabs",
    "bushido",
    "capforce",
    "castellan",
    "conductor_fund",
    "cresalta",
    "burney",
    "cambria",
    "cambiar",
    "calamos",
    "canary",
    "cboe",
    "ccm",
    "capital_group",
    "cary_street",
    "fairlead",
    "colliers",
    "peakshares",
    "kingsbarn",
    "prospera",
    "stone_ridge",
    "quantify_chaos",
    "summit_global",
    "regan",
    "castleark",
    "3edge",
    "capital_impact",
    "cicc",
    "cultivar",
    "coinshares",
    "corgi",
    "concourse",
    "cotwo",
    "corient",
    "distribution_cognizant",
    "donoghue_forlines",
    "counterpoint",
    "convergence",
    "cullen",
    "cyber_hornet",
    "optimize",
    "clearshares",
    "clough",
    "clough_cgi",
    "davis",
    "defiance",
    "delaware",
    "dividend_assets",
    "deepwater",
    "ci_financial",
    "digital_currency_group",
    "deutsche_bank",
    "diamond_hill",
    "dimensional",
    "dhandho",
    "core_alternative",
    "eagle_capital",
    "eighth_wonder",
    "emles",
    "emqq",
    "ershares",
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
    "focus_financial",
    "fmc_group",
    "fidelity",
    "frontier",
    "goose_hollow",
    "thornburg",
    "formidable",
    "idx",
    "indexperts",
    "fortuna",
    "liquid_strategies",
    "lionshares",
    "cygnet",
    "elm",
    "esoterica",
    "oneascent",
    "first_eagle",
    "fm_investments",
    "founder",
    "first_trust",
    "grace_partners",
    "franklin",
    "future_fund",
    "global_x",
    "graff",
    "mirae_asset",
    "groupe_bpce",
    "gqg",
    "gamco",
    "goldman_sachs",
    "gmo",
    "golden_eagle",
    "graniteshares",
    "grayscale",
    "guggenheim",
    "hashdex",
    "hartford",
    "harbor",
    "hedgeye",
    "scm_edge",
    "hennessy",
    "ironhorse",
    "horizon_kinetics",
    "howard_capital",
    "hwcap",
    "hull",
    "hypatia",
    "inspire",
    "impax",
    "im_global_partner",
    "innovator",
    "invesco",
    "ishares",
    "jensen",
    "janus_henderson",
    "jpmorgan",
    "kingsview",
    "killir",
    "kovitz",
    "kraneshares",
    "kensington",
    "kurv",
    "langar",
    "lazard",
    "leuthold",
    "little_harbor",
    "logan",
    "main_management",
    "man_group",
    "mairs_power",
    "madison",
    "matthews",
    "mfs",
    "morgan_stanley",
    "miller_value",
    "mitsubishi_ufj",
    "mcivy",
    "mm_vam",
    "vident",
    "motley_fool",
    "neos",
    "neuberger_berman",
    "neil_azous",
    "nomura",
    "new_york_life",
    "noa",
    "northern_trust",
    "nsi",
    "ocean_park",
    "osprey",
    "paralel",
    "pacer",
    "pictet",
    "ptam",
    "precidian",
    "praxis",
    "palmer_square",
    "pmv",
    "point_bridge",
    "pettee",
    "polen",
    "principal",
    "prudential",
    "procuream",
    "proshares",
    "rafferty",
    "rdj",
    "rayliant",
    "raymond_james",
    "russell_investments",
    "renaissance_capital",
    "reverence",
    "roundhill",
    "river_north",
    "running_oak",
    "saracen",
    "schwab",
    "sei",
    "simplify",
    "spdr",
    "spear",
    "spend_life_wisely",
    "sprott",
    "split_rock",
    "ssc",
    "sterling_capital",
    "sterling_fund",
    "strategas",
    "stf",
    "natixis",
    "western_southern",
    "touchstone",
    "intech",
    "inverdale",
    "ballast",
    "bancreek",
    "strive",
    "swan_global",
    "sun_life",
    "symmetry",
    "tapp",
    "tiaa",
    "tcw",
    "thor",
    "tortoise",
    "texas_capital",
    "toews",
    "tuttle",
    "true_shares",
    "truemark",
    "twin_oak",
    "t_rowe_price",
    "timothy_plan",
    "tema",
    "teucrium",
    "themes",
    "ubs",
    "us_global_investors",
    "vanguard",
    "vaneck",
    "vert",
    "victory",
    "virtus",
    "volatility_shares",
    "vontobel",
    "voya",
    "wahed",
    "warren",
    "water_island",
    "altshares",
    "keating",
    "wellington",
    "weitz",
    "wbi",
    "world_gold_council",
    "yorkville",
    "truth_social",
    "sofi",
    "thrivent",
    "calvert",
    "yieldmax",
    "zacks",
}
SEC_BACKED_SAMPLE_ADAPTERS = {
    "direxion",
    "wisdomtree",
}


def _covers_live_provider(adapter_key: str):
    """Mark a bespoke live test as the concrete route for one native provider."""

    def decorate(test):
        test._live_provider_adapter_key = adapter_key
        return test

    return decorate


pytestmark = [pytest.mark.live]

# Keep the registry/coverage contracts executable in every backend test run.  Only the
# network-bearing issuer probes are opt-in; placing the skip on the whole module used to
# silently skip the very tests that prove a promoted adapter has a concrete live route.
_NON_NETWORK_CONTRACT_TESTS = {
    "test_live_provider_matrix_covers_every_registered_issuer_adapter",
    "test_live_backed_providers_each_have_a_concrete_live_route_test",
}


@pytest.fixture(autouse=True)
def _skip_network_probe_unless_enabled(request):
    if (
        request.node.originalname not in _NON_NETWORK_CONTRACT_TESTS
        and os.getenv("RUN_LIVE_ETF_HOLDINGS_TESTS") != "1"
    ):
        pytest.skip("Set RUN_LIVE_ETF_HOLDINGS_TESTS=1 to run live issuer holdings checks.")


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
            "convergence",
            "CLSE",
            None,
            {},
            100,
        ),
        ("dhandho", "WAGN", None, {}, 10),
        ("water_island", "ARB", None, {}, 30),
        ("altshares", "ARB", None, {}, 30),
        ("keating", "KEAT", None, {}, 20),
        ("canary", "HBR", None, {}, 1),
        ("optimize", "OPTZ", None, {}, 100),
        ("emles", "EOPS", None, {}, 1),
        ("acp_horizon", "HBTA", None, {}, 100),
        ("advent_capital", "ACVT", None, {}, 20),
        ("archer_investment", "ARWG", None, {}, 20),
        ("818", "SPCT", None, {}, 20),
        ("arlington", "AQEC", None, {}, 20),
        ("kingsview", "MVFD", None, {}, 30),
        ("killir", "GARY", None, {}, 20),
        ("rdj", "HEDG", None, {}, 8),
        ("reverence", "OOSP", None, {}, 200),
        ("saracen", "SJCP", None, {}, 10),
        ("mm_vam", "VUSE", None, {}, 100),
        ("vident", "VUSE", None, {}, 100),
        ("albert_mason", "KNOW", None, {}, 50),
        ("focus_financial", "EBI", None, {}, 1000),
        ("graff", "PFDE", None, {}, 50),
        ("resolute", "AHLT", None, {}, 200),
        ("american_beacon", "AHLT", None, {}, 200),
        (
            "corgi",
            "FDRS",
            None,
            {},
            20,
        ),
        ("indexperts", "QIDX", None, {}, 100),
        ("fortuna", "HBTC", None, {}, 5),
        ("liquid_strategies", "OVL", None, {}, 5),
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
            "scm_edge",
            "HEFT",
            None,
            {},
            50,
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
            "amun",
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
            "neuberger_berman",
            "NBCR",
            None,
            {},
            20,
        ),
        (
            "neil_azous",
            "RDFI",
            None,
            {},
            20,
        ),
        (
            "nomura",
            "FRWD",
            None,
            {},
            20,
        ),
        (
            "delaware",
            "LRGG",
            None,
            {},
            20,
        ),
        (
            "ironhorse",
            "CGV",
            None,
            {},
            90,
        ),
        (
            "adaptive_investments",
            "ADPV",
            None,
            {},
            20,
        ),
        (
            "belpointe",
            "PLGI",
            None,
            {},
            100,
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
            "precidian",
            "ASMH",
            None,
            {},
            2,
        ),
        (
            "advisor_shares",
            "MSOS",
            None,
            {},
            4,
        ),
        (
            "allianz",
            "FEBT",
            None,
            {},
            5,
        ),
        (
            "araq",
            "SSUS",
            None,
            {},
            10,
        ),
        (
            "day_hagan",
            "SSUS",
            None,
            {},
            10,
        ),
        (
            "alliancebernstein",
            "FWD",
            None,
            {},
            100,
        ),
        (
            "equitable",
            "FWD",
            None,
            {},
            100,
        ),
        (
            "estate_counselors",
            "TBFC",
            None,
            {},
            20,
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
            "brookfield",
            "TRBF",
            None,
            {},
            100,
        ),
        (
            "guardian",
            "SCNM",
            None,
            {},
            20,
        ),
        (
            "sterling_capital",
            "SCEP",
            None,
            {},
            20,
        ),
        (
            "hwcap",
            "HWSM",
            None,
            {},
            100,
        ),
        (
            "spend_life_wisely",
            "SLWS",
            None,
            {},
            100,
        ),
        (
            "stf",
            "TUG",
            None,
            {},
            20,
        ),
        (
            "absolute_investment_advisers",
            "ABEQ",
            None,
            {},
            10,
        ),
        (
            "paralel",
            "SRHQ",
            None,
            {},
            50,
        ),
        (
            "logan",
            "LCLG",
            None,
            {},
            50,
        ),
        (
            "pmv",
            "ARP",
            None,
            {},
            5,
        ),
        (
            "warren",
            "WCAP",
            None,
            {},
            20,
        ),
        (
            "barclays",
            "ATMP",
            None,
            {},
            10,
        ),
        (
            "bmo",
            "BNKU",
            None,
            {},
            10,
        ),
        (
            "ubs",
            "PFFL",
            None,
            {},
            2,
        ),
        (
            "concourse",
            "CCFE",
            None,
            {},
            10,
        ),
        (
            "distribution_cognizant",
            "VOXP",
            None,
            {},
            100,
        ),
        ("natixis", "GQI", None, {}, 100),
        ("nsi", "NSI", None, {}, 40),
        ("western_southern", "LCF", None, {}, 20),
        ("touchstone", "LCF", None, {}, 20),
        ("intech", "LGDX", None, {}, 100),
        ("inverdale", "MGMT", None, {}, 20),
        ("ballast", "MGMT", None, {}, 20),
        ("bancreek", "BCUS", None, {}, 20),
        ("split_rock", "KOOL", None, {}, 20),
        ("ptam", "STBF", None, {}, 100),
        ("ci_financial", "SBH", None, {}, 20),
        ("reflection", "DEMZ", None, {}, 40),
        ("cotwo", "CTWO", None, {}, 2),
        ("frontier", "FARX", None, {}, 10),
        ("goose_hollow", "GHTA", None, {}, 10),
        ("thornburg", "TXUE", None, {}, 10),
        ("formidable", "FORH", None, {}, 20),
        ("idx", "GLDB", None, {}, 5),
        ("lionshares", "TOT", None, {}, 2),
        ("cygnet", "ELM", None, {}, 10),
        ("elm", "ELM", None, {}, 10),
        ("esoterica", "WUGI", None, {}, 10),
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
        ("spdr", "SPYG", None, {}, 100),
        ("spdr", "SPYV", None, {}, 100),
        ("spdr", "MDY", None, {}, 100),
        ("spdr", "MDYG", None, {}, 100),
        ("spdr", "MDYV", None, {}, 100),
        ("spdr", "SLYG", None, {}, 100),
        ("spdr", "SLYV", None, {}, 100),
        ("spdr", "SPTM", None, {}, 100),
        ("spdr", "XBI", None, {}, 100),
        ("spdr", "KRE", None, {}, 100),
        ("spdr", "XRT", None, {}, 50),
        ("spdr", "XME", None, {}, 30),
        ("spdr", "XAR", None, {}, 20),
        ("spdr", "XHB", None, {}, 30),
        ("spdr", "XOP", None, {}, 50),
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
        ("ishares", "IJR", None, {}, 100),
        ("ishares", "IWB", None, {}, 100),
        ("ishares", "IWD", None, {}, 100),
        ("ishares", "IWF", None, {}, 100),
        ("ishares", "IWN", None, {}, 100),
        ("ishares", "IWO", None, {}, 100),
        ("ishares", "IWV", None, {}, 100),
        (
            "ishares",
            "SOXX",
            None,
            {},
            30,
        ),
        ("ishares", "IBB", None, {}, 100),
        ("ishares", "ITA", None, {}, 20),
        ("ishares", "ITB", None, {}, 30),
        ("vaneck", "OIH", None, {"product_slug": "oil-services-etf-oih"}, 20),
        ("vaneck", "SLX", None, {"product_slug": "steel-etf-slx"}, 20),
        (
            "kraneshares",
            "KWEB",
            None,
            {},
            20,
        ),
        (
            "cicc",
            "KWEB",
            None,
            {},
            20,
        ),
        (
            "man_group",
            "BUYO",
            None,
            {},
            300,
        ),
        (
            "kensington",
            "KAMO",
            None,
            {},
            8,
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
            "avantis",
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
            "tradr",
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
            "build",
            "BFIX",
            None,
            {},
            50,
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
        ("brookstone", "BAMD", None, {}, 5),
        ("brookstone", "BAMG", None, {}, 5),
        ("brookstone", "BAMV", None, {}, 5),
        ("brookstone", "BAMB", None, {}, 5),
        ("brookstone", "BAMU", None, {}, 5),
        ("brookstone", "BAMA", None, {}, 5),
        ("brookstone", "BAMO", None, {}, 5),
        ("brookstone", "BAMY", None, {}, 5),
        ("bufferlabs", "BFLB", None, {}, 3),
        ("bushido", "SMRI", None, {}, 20),
        ("bushido", "RNIN", None, {}, 20),
        ("capforce", "FFTY", None, {}, 20),
        ("capforce", "BOUT", None, {}, 20),
        ("castellan", "CTEF", None, {}, 20),
        ("castellan", "CTIF", None, {}, 20),
        ("conductor_fund", "CGV", None, {}, 20),
        ("cresalta", "CVGD", None, {}, 20),
        ("cresalta", "CVSM", None, {}, 20),
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
            "cary_street",
            "TACK",
            None,
            {},
            5,
        ),
        (
            "fairlead",
            "TACK",
            None,
            {},
            5,
        ),
        (
            "summit_global",
            "SGLC",
            None,
            {},
            50,
        ),
        (
            "regan",
            "MBSF",
            None,
            {},
            50,
        ),
        (
            "castleark",
            "CARK",
            None,
            {},
            20,
        ),
        (
            "prospera",
            "THRV",
            None,
            {},
            10,
        ),
        (
            "stone_ridge",
            "LFDR",
            None,
            {},
            10,
        ),
        (
            "3edge",
            "EDGU",
            None,
            {},
            10,
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
            "RSP",
            None,
            {},
            100,
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
            "PJUS",
            None,
            {},
            # PJBF was liquidated in July 2026. PJUS remains an active PGIM
            # ETF and verifies the issuer's current daily-holdings route.
            50,
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
            "grayscale",
            "GBTC",
            None,
            {},
            1,
        ),
        (
            "digital_currency_group",
            "BCOR",
            None,
            {},
            40,
        ),
        (
            "hashdex",
            "DEFI",
            None,
            {},
            # Current DEFI disclosure is a two-row crypto/cash portfolio;
            # validate the complete disclosed snapshot rather than imposing
            # an equity-count minimum that the issuer does not satisfy.
            2,
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
            "noa",
            "USAF",
            None,
            {},
            50,
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
            "truth_social",
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
            "wellington",
            "VUSV",
            None,
            {},
            70,
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
            "mfs",
            "MFSB",
            None,
            {},
            50,
        ),
        (
            "sun_life",
            "MFSV",
            None,
            {},
            50,
        ),
        (
            "symmetry",
            "SMOM",
            None,
            {},
            5,
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
            # MAGO was liquidated on 2026-07-10; use the current DRMP fund for
            # the provider-health probe while historical MAGO identity remains
            # supported by the canonical security master.
            "DRMP",
            None,
            {},
            2,
        ),
        (
            "true_shares",
            "ONEH",
            None,
            {},
            5,
        ),
        (
            "truemark",
            "LRNZ",
            None,
            {},
            20,
        ),
        (
            "twin_oak",
            "TOAK",
            None,
            {},
            3,
        ),
        (
            "river_north",
            "FLDZ",
            None,
            {},
            50,
        ),
        (
            "cohanzick",
            "CUSD",
            None,
            {},
            10,
        ),
        (
            "tremblant",
            "TOGA",
            None,
            {},
            20,
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
            "grace_partners",
            "IDVY",
            None,
            {},
            20,
        ),
        (
            "cboe",
            "BUFG",
            None,
            {},
            8,
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
            "vontobel",
            "VNIE",
            None,
            {},
            40,
        ),
        (
            "vert",
            "VGSR",
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
            4,
        ),
        (
            "clough",
            "CBSE",
            None,
            {},
            20,
        ),
        (
            "clough_cgi",
            "CBSE",
            None,
            {},
            20,
        ),
        (
            "weitz",
            "WCPB",
            None,
            {},
            100,
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
        (
            "jensen",
            "JGRW",
            None,
            {},
            20,
        ),
        (
            "peakshares",
            "PSTR",
            None,
            {},
            20,
        ),
        (
            "colliers",
            "NFRX",
            None,
            {},
            20,
        ),
        (
            "kingsbarn",
            "DVDN",
            None,
            {},
            10,
        ),
        (
            "quantify_chaos",
            "BTGD",
            None,
            {},
            5,
        ),
        (
            "russell_investments",
            "RUSC",
            None,
            {},
            100,
        ),
        (
            "morgan_stanley",
            "MSLC",
            None,
            {},
            100,
        ),
        (
            "golden_eagle",
            "HYP",
            None,
            {},
            50,
        ),
        (
            "dividend_assets",
            "DVGR",
            None,
            {},
            30,
        ),
        (
            "cyber_hornet",
            "XXX",
            None,
            {},
            400,
        ),
        ("praxis", "PRXG", None, {}, 100),
        ("baird", "SAGP", None, {}, 100),
        ("affiliated_managers_group", "MUNX", None, {}, 50),
        ("raymond_james", "RJDI", None, {}, 30),
        ("osprey", "OSOL", None, {}, 1),
        ("goldman_sachs", "GSLC", None, {}, 400),
        ("guggenheim", "GCSH", None, {}, 10),
        ("alexis", "LEXI", None, {}, 20),
        ("ag_financial", "CLCG", None, {}, 20),
        ("artemis", "ACEP", None, {}, 20),
        ("ars", "ACEP", None, {}, 20),
        ("avory", "AVRY", None, {}, 20),
        ("beehive", "BEEX", None, {}, 20),
        ("blueprint", "TFPN", None, {}, 20),
        ("bridgeway", "BBLU", None, {}, 20),
        ("bridgeway", "BAGX", None, {}, 20),
        ("bridgeway", "BRSV", None, {}, 20),
        ("bridgeway", "BSVO", None, {}, 20),
        ("bridgeway", "BUSM", None, {}, 20),
        ("unlimited", "HFND", None, {}, 40),
        ("x_square", "ZTAX", None, {}, 10),
        ("webs", "DVSP", None, {}, 4),
        ("waverly", "GGM", None, {}, 5),
        ("swp", "SWP", None, {}, 40),
        ("lagan", "CAML", None, {}, 30),
        ("congress", "CAML", None, {}, 30),
        ("ccm", "OWNS", None, {}, 100),
        ("beacon_capital", "BSR", None, {}, 25),
        ("beacon_capital", "BTR", None, {}, 10),
        ("retireful", "RULE", None, {}, 30),
        # Siren's currently published BLCN portfolio is in liquidation and contains
        # its disclosed cash/currency positions, so validate complete current rows
        # rather than falsely expecting a historical equity count.
        ("srn", "BLCN", None, {}, 5),
        ("myriad", "MDAA", None, {}, 50),
        ("reckoner", "RAAA", None, {}, 50),
        ("redbird", "RCLR", None, {}, 3),
        ("nightview", "NITE", None, {}, 10),
        ("gladius", "CMBO", None, {}, 6),
        ("shariaportfolio", "SPTE", None, {}, 50),
        ("sp_funds", "SPTE", None, {}, 50),
        ("academy", "VETZ", None, {}, 10),
        ("impact_shares", "NACP", None, {}, 10),
        ("acsi_funds", "ACSI", None, {}, 20),
        ("oakmark", "OAKM", None, {}, 10),
        ("oakmark", "OAKI", None, {}, 10),
        ("oshares", "OUSA", None, {}, 50),
        ("range", "NUKZ", None, {}, 10),
        ("range", "COAL", None, {}, 10),
        ("sofi", "SFY", None, {}, 300),
        ("thrivent", "TSCV", None, {}, 40),
        # Calvert's current public JSON is identity/date-valid but discloses 121
        # rows for CVLC; keep a conservative floor rather than asserting the
        # stale 500-row expectation from an older universe snapshot.
        ("calvert", "CVLC", None, {}, 100),
        ("alerian", "ENFR", None, {}, 20),
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

    try:
        result = await adapter.fetch_latest(
            symbol=symbol,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
    except ValueError as exc:
        if (
            adapter_key == "zacks"
            and "closed the backend connection without a response after retries" in str(exc)
        ):
            pytest.skip(str(exc))
        raise

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=min_rows)
    if adapter_key == "ishares" and symbol in {"SOXX", "IBB", "ITA", "ITB"}:
        assert result.legal_metadata["route_resolution"] == "issuer_public_json_api"
        assert result.legal_metadata["composition_date"]
    if adapter_key == "ishares" and symbol == "SOXX":
        assert any(row.symbol == "NVDA" for row in result.rows)
    if adapter_key == "bufferlabs":
        assert result.legal_metadata["route_resolution"] == (
            "bufferlabs_public_complete_current_holdings_table"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "derivative" for row in result.rows)
        assert any(row.row_type == "cash" for row in result.rows)
    if adapter_key == "bushido":
        assert result.legal_metadata["route_resolution"] == (
            "bushido_public_complete_current_holdings_table"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "cash" for row in result.rows)
    if adapter_key == "capforce":
        assert result.legal_metadata["route_resolution"] == (
            "capforce_public_complete_current_holdings_table"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "cash" for row in result.rows)
    if adapter_key == "castellan":
        assert result.legal_metadata["route_resolution"] == (
            "castellan_public_complete_current_holdings_table"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "cash" for row in result.rows)
    if adapter_key == "conductor_fund":
        assert result.legal_metadata["route_resolution"] == (
            "conductor_product_page_declared_complete_holdings_csv"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "cash" for row in result.rows)
    if adapter_key == "cresalta":
        assert result.legal_metadata["route_resolution"] == (
            "cresalta_public_complete_current_holdings_table"
        )
        assert result.legal_metadata["composition_date"]
        assert any(row.holding_type == "cash" for row in result.rows)
@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("ishares")
async def test_live_ishares_explicit_historical_as_of_snapshot():
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None

    result = await adapter.fetch_for_date(symbol="IWV", requested_date=date(2026, 6, 30))

    _assert_live_holdings_result(result, adapter_key="ishares", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "issuer_public_json_api_as_of_date"
    assert result.legal_metadata["requested_holdings_date"] == "2026-06-30"
    assert result.legal_metadata["composition_date"] == "2026-06-30"
    assert any(row.symbol == "NVDA" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("invesco")
async def test_live_invesco_qqq_historical_fallback_is_sec_labelled():
    """Prove dated QQQ uses periodic SEC evidence rather than current holdings."""

    adapter = get_holdings_adapter("invesco")
    assert adapter is not None

    requested_date = date(2025, 12, 31)
    result = await adapter.fetch_for_date(
        symbol="QQQ",
        requested_date=requested_date,
        identifiers={"sec_cik": "0001067839"},
    )

    _assert_live_holdings_result(result, adapter_key="invesco", min_rows=100)
    metadata = result.legal_metadata or {}
    assert metadata["source_access"] == "sec_filing"
    assert metadata["source_provider"] == "sec"
    assert metadata["requested_holdings_date"] == requested_date.isoformat()
    assert metadata["historical_as_of_policy"] == (
        "latest_sec_filing_report_on_or_before_requested_date"
    )
    assert metadata["issuer_route"] == "invesco_current_monthly_only"
    assert date.fromisoformat(str(metadata["composition_date"])) <= requested_date


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("ishares")
@pytest.mark.parametrize("symbol", ["IJR", "IWB", "IWD", "IWF", "IWN", "IWO", "IWV"])
async def test_live_ishares_family_legs_support_historical_as_of_snapshots(symbol):
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None

    result = await adapter.fetch_for_date(symbol=symbol, requested_date=date(2026, 6, 30))

    _assert_live_holdings_result(result, adapter_key="ishares", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "issuer_public_json_api_as_of_date"
    assert result.legal_metadata["requested_holdings_date"] == "2026-06-30"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol", "identifiers", "expected_route_resolution"),
    [
        (
            "global_x",
            "QYLD",
            {},
            "global_x_fund_page_declared_holdings_csv",
        ),
        (
            "mirae_asset",
            "QYLD",
            {},
            "global_x_fund_page_declared_holdings_csv",
        ),
    ],
)
async def test_live_issuer_product_pages_discover_parseable_holdings_files(
    adapter_key,
    symbol,
    identifiers,
    expected_route_resolution,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    result = await adapter.fetch_latest(symbol=symbol, identifiers=identifiers)

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=5)
    assert result.legal_metadata["route_resolution"] == expected_route_resolution


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("leverage_shares")
async def test_live_leverage_shares_symbol_scoped_holdings_csv():
    adapter = get_holdings_adapter("leverage_shares")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="MPG")

    _assert_live_holdings_result(result, adapter_key="leverage_shares", min_rows=5)
    assert result.source_url.endswith("/MPG_Holdings.csv")
    assert result.legal_metadata["route_resolution"] == "issuer_profile_metadata"
    assert result.legal_metadata["source_access"] == (
        "issuer_public_product_page_declared_complete_holdings_csv"
    )
    assert any(row.row_type == "cash" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("hull")
async def test_live_hull_product_verified_complete_holdings_csv():
    adapter = get_holdings_adapter("hull")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="HTUS")

    _assert_live_holdings_result(result, adapter_key="hull", min_rows=10)
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_verified_complete_holdings_csv"
    )
    assert result.legal_metadata["composition_date"]
    assert any(row.holding_type == "cash" for row in result.rows)
    assert any(row.holding_type in {"future", "option"} for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("im_global_partner")
async def test_live_imgp_dbmf_product_page_exposes_complete_holdings_table():
    adapter = get_holdings_adapter("im_global_partner")
    assert adapter is not None

    try:
        result = await adapter.fetch_latest(symbol="DBMF")
    except ValueError as exc:
        if "scheduled maintenance" in str(exc).lower():
            pytest.skip(str(exc))
        raise

    _assert_live_holdings_result(result, adapter_key="im_global_partner", min_rows=10)
    assert result.legal_metadata["route_resolution"] == "imgp_verified_fund_scoped_holdings_table"
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["fund_id"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("sei")
async def test_live_sei_dated_daily_holdings_export():
    adapter = get_holdings_adapter("sei")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="SEIS")

    _assert_live_holdings_result(result, adapter_key="sei", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "issuer_dated_daily_holdings_export"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("ameriprise")
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
@_covers_live_provider("columbia_threadneedle")
async def test_live_columbia_threadneedle_cusip_holdings_export():
    adapter = get_holdings_adapter("columbia_threadneedle")
    assert adapter is not None

    result = await adapter.fetch_latest(
        symbol="RECS",
        identifiers={"cusip": "19761L706"},
    )

    _assert_live_holdings_result(
        result,
        adapter_key="columbia_threadneedle",
        min_rows=100,
    )
    assert result.legal_metadata["route_resolution"] == ("columbia_threadneedle_cusip_holdings_csv")
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("1251_capital")
async def test_live_1251_capital_owned_fm_investments_holdings_api():
    adapter = get_holdings_adapter("1251_capital")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="UTWO")

    _assert_live_holdings_result(result, adapter_key="1251_capital", min_rows=2)
    assert result.legal_metadata["route_resolution"] == ("1251_capital_fm_investments_holdings_api")
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("rafferty")
async def test_live_rafferty_direxion_daily_holdings_export():
    adapter = get_holdings_adapter("rafferty")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="COM")

    _assert_live_holdings_result(result, adapter_key="rafferty", min_rows=5)
    assert result.legal_metadata["route_resolution"] == "rafferty_direxion_symbol_holdings_csv"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("direxion")
async def test_live_direxion_qqqe_equal_weight_holdings_export():
    """Exercise the exact Nasdaq-100 equal-weight leg used by the workstation."""
    adapter = get_holdings_adapter("direxion")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="QQQE")

    _assert_live_holdings_result(result, adapter_key="direxion", min_rows=80)
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("direxion")
async def test_live_direxion_qqqe_historical_fallback_is_sec_labelled():
    """Prove dated QQQE uses periodic SEC evidence rather than current CSV rows."""

    adapter = get_holdings_adapter("direxion")
    assert adapter is not None

    requested_date = date(2025, 12, 31)
    result = await adapter.fetch_for_date(
        symbol="QQQE",
        requested_date=requested_date,
        identifiers={"sec_cik": "0001424958"},
    )

    _assert_live_holdings_result(result, adapter_key="direxion", min_rows=80)
    metadata = result.legal_metadata or {}
    assert metadata["source_access"] == "sec_filing"
    assert metadata["source_provider"] == "sec"
    assert metadata["requested_holdings_date"] == requested_date.isoformat()
    assert metadata["historical_as_of_policy"] == (
        "latest_sec_filing_report_on_or_before_requested_date"
    )
    assert metadata["issuer_route"] == "direxion_current_daily_csv"
    assert date.fromisoformat(str(metadata["composition_date"])) <= requested_date


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("hypatia")
async def test_live_hypatia_public_fund_scoped_holdings_api():
    adapter = get_holdings_adapter("hypatia")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="WCEO")

    _assert_live_holdings_result(result, adapter_key="hypatia", min_rows=20)
    assert result.legal_metadata["route_resolution"] == ("hypatia_public_fund_scoped_holdings_api")
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("exchange_traded_concepts")
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
@_covers_live_provider("bluemonte")
async def test_live_bluemonte_fund_page_payload():
    adapter = get_holdings_adapter("bluemonte")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="BLUC")

    _assert_live_holdings_result(result, adapter_key="bluemonte", min_rows=3)
    assert result.legal_metadata["route_resolution"] == "bluemonte_fund_page_payload"
    assert any(row.extra_data.get("figi") for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("emqq")
async def test_live_emqq_global_cms_holdings_api():
    adapter = get_holdings_adapter("emqq")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="EMQQ")

    _assert_live_holdings_result(result, adapter_key="emqq", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "emqq_global_cms_holdings_api"
    assert result.legal_metadata["composition_date"]
    assert any(row.extra_data.get("figi") for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("ershares")
async def test_live_ershares_ssnc_full_holdings_api():
    adapter = get_holdings_adapter("ershares")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="XOVR")

    _assert_live_holdings_result(result, adapter_key="ershares", min_rows=20)
    assert result.legal_metadata["route_resolution"] == ("ershares_public_ssnc_full_holdings_api")
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("kovitz")
async def test_live_kovitz_filepoint_complete_holdings_json():
    adapter = get_holdings_adapter("kovitz")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="EQTY")

    _assert_live_holdings_result(result, adapter_key="kovitz", min_rows=20)
    assert result.legal_metadata["route_resolution"] == ("kovitz_filepoint_complete_holdings_json")
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("strategas")
async def test_live_strategas_current_holdings_csv():
    adapter = get_holdings_adapter("strategas")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="SAGP")

    _assert_live_holdings_result(result, adapter_key="strategas", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "strategas_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("aot")
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
@_covers_live_provider("3fourteen")
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
@_covers_live_provider("abacus_global")
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
@_covers_live_provider("alternative_access")
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
@_covers_live_provider("rational")
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
@_covers_live_provider("toews")
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
@_covers_live_provider("redwood")
async def test_live_redwood_leadershares_fund_scoped_holdings_csv():
    adapter = get_holdings_adapter("redwood")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="LSAT")

    _assert_live_holdings_result(result, adapter_key="redwood", min_rows=10)
    assert result.legal_metadata["route_resolution"] == (
        "redwood_leadershares_fund_scoped_holdings_download"
    )
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "csv"
    assert any(row.symbol == "FERG" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("rex")
async def test_live_rex_shares_tslt_product_page_holdings_csv():
    adapter = get_holdings_adapter("rex")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="TSLT")

    _assert_live_holdings_result(result, adapter_key="rex", min_rows=5)
    assert result.legal_metadata["route_resolution"] == (
        "rex_product_page_complete_holdings_csv_form"
    )
    assert result.legal_metadata["source_format"] == "csv"
    # The issuer's current CSV has no as-of/composition-date field; the absence
    # is preserved rather than inferred from request time or page metadata.
    assert result.legal_metadata.get("composition_date") is None


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("sterling_fund")
async def test_live_sterling_fund_management_scmc_publisher_holdings_pdf():
    adapter = get_holdings_adapter("sterling_fund")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="SCMC")

    _assert_live_holdings_result(result, adapter_key="sterling_fund", min_rows=100)
    assert result.legal_metadata["route_resolution"] == (
        "sterling_capital_publisher_current_holdings_pdf_for_sterling_fund_scmc"
    )
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "pdf"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("donoghue_forlines")
async def test_live_donoghue_forlines_product_page_declared_holdings_csv():
    adapter = get_holdings_adapter("donoghue_forlines")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="DFTT")

    _assert_live_holdings_result(result, adapter_key="donoghue_forlines", min_rows=20)
    assert result.legal_metadata["route_resolution"] in {
        "donoghue_forlines_product_page_ajax_holdings_csv",
        "sec_edgar_filing_fallback",
    }
    if result.legal_metadata["route_resolution"] == "sec_edgar_filing_fallback":
        assert result.legal_metadata["issuer_route_fallback"] == "sec_edgar_filing"
        assert result.legal_metadata["issuer_route_failure"]
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] in {"csv", "nport_xml", "legacy_xml_table"}


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("dakota_wealth")
async def test_live_dakota_wealth_public_product_page_holdings_table():
    adapter = get_holdings_adapter("dakota_wealth")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="DAK")

    _assert_live_holdings_result(result, adapter_key="dakota_wealth", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "dakota_wealth_public_product_page_holdings_table"
    )
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "html"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("eagle_capital")
async def test_live_eagle_capital_daily_creation_basket_json():
    adapter = get_holdings_adapter("eagle_capital")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="EAGL")

    _assert_live_holdings_result(result, adapter_key="eagle_capital", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "eagle_capital_daily_holdings_json"
    assert result.legal_metadata["composition_date"]
    assert result.rows[0].cusip


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("eighth_wonder")
async def test_live_eighth_wonder_fundsmith_etft_complete_holdings_component():
    adapter = get_holdings_adapter("eighth_wonder")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="ETFT")

    _assert_live_holdings_result(result, adapter_key="eighth_wonder", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "fundsmith_public_etft_complete_holdings_component"
    )
    assert result.legal_metadata["composition_date"]
    assert any(row.isin for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("core_alternative")
async def test_live_core_alternative_dated_daily_holdings_csv():
    adapter = get_holdings_adapter("core_alternative")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="CCOR")

    _assert_live_holdings_result(result, adapter_key="core_alternative", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "core_alternative_dated_daily_holdings_csv"
    )
    assert result.legal_metadata["composition_date"]
    assert result.rows[0].cusip


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("infrastructure_capital")
async def test_live_infrastructure_capital_symbol_holdings_workbook():
    adapter = get_holdings_adapter("infrastructure_capital")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="ICAP")

    _assert_live_holdings_result(result, adapter_key="infrastructure_capital", min_rows=20)
    assert result.legal_metadata["route_resolution"] == (
        "infrastructure_capital_symbol_holdings_xls"
    )
    assert result.rows[0].cusip


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("thor")
async def test_live_thor_product_page_scoped_holdings_api():
    adapter = get_holdings_adapter("thor")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="THIR")

    _assert_live_holdings_result(result, adapter_key="thor", min_rows=2)
    assert result.legal_metadata["route_resolution"] in {
        "thor_product_page_scoped_holdings_api",
        "thor_product_page_embedded_holdings_json",
    }
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip and row.holding_type == "equity" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("wedbush")
async def test_live_wedbush_symbol_holdings_csv():
    adapter = get_holdings_adapter("wedbush")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="TGLR")

    _assert_live_holdings_result(result, adapter_key="wedbush", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "wedbush_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("shelton")
async def test_live_shelton_product_page_linked_holdings_csv():
    adapter = get_holdings_adapter("shelton")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="SEPI")
    _assert_live_holdings_result(result, adapter_key="shelton", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "shelton_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("tidal")
async def test_live_tidal_sponsor_fund_scoped_daily_holdings_csv():
    adapter = get_holdings_adapter("tidal")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="IINC")
    _assert_live_holdings_result(result, adapter_key="tidal", min_rows=100)
    assert (
        result.legal_metadata["route_resolution"] == "tidal_sponsor_fund_scoped_daily_holdings_csv"
    )
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("pictet")
async def test_live_pictet_public_fund_allocation_api():
    adapter = get_holdings_adapter("pictet")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="PQUS")
    _assert_live_holdings_result(result, adapter_key="pictet", min_rows=100)
    assert result.legal_metadata["route_resolution"] == "pictet_public_kurtosys_fund_allocations"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("dana")
async def test_live_dana_fund_scoped_daily_holdings_csv():
    adapter = get_holdings_adapter("dana")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="DANA")
    _assert_live_holdings_result(result, adapter_key="dana", min_rows=10)
    assert result.legal_metadata["route_resolution"] == "dana_fund_scoped_daily_holdings_csv"
    assert result.legal_metadata["composition_date"]
    assert result.legal_metadata["source_format"] == "csv"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("dawn_global")
async def test_live_dawn_global_tema_publisher_holdings_csv():
    adapter = get_holdings_adapter("dawn_global")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="DSPY")
    _assert_live_holdings_result(result, adapter_key="dawn_global", min_rows=100)
    assert result.legal_metadata["publisher"] == "tema"
    assert result.legal_metadata["route_resolution"] == "dawn_global_tema_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("fmc_group")
async def test_live_fmc_group_quarterly_holdings_workbook():
    adapter = get_holdings_adapter("fmc_group")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="FMCX")
    _assert_live_holdings_result(result, adapter_key="fmc_group", min_rows=20)
    assert result.legal_metadata["route_resolution"] == "fmc_group_fmcx_quarterly_holdings_workbook"
    assert result.legal_metadata["source_frequency"] == "quarterly"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("envestnet")
async def test_live_envestnet_product_page_linked_full_holdings_xls():
    adapter = get_holdings_adapter("envestnet")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="APMU")
    _assert_live_holdings_result(result, adapter_key="envestnet", min_rows=100)
    assert (
        result.legal_metadata["route_resolution"]
        == "envestnet_product_page_linked_full_holdings_xls"
    )
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("amerilife")
async def test_live_amerilife_brookstone_bama_full_holdings_csv():
    adapter = get_holdings_adapter("amerilife")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="BAMA")
    _assert_live_holdings_result(result, adapter_key="amerilife", min_rows=5)
    assert result.legal_metadata["publisher"] == "brookstone_asset_management"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("marygold")
async def test_live_marygold_uscf_public_browser_holdings_api():
    adapter = get_holdings_adapter("marygold")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="USO")
    _assert_live_holdings_result(result, adapter_key="marygold", min_rows=3)
    assert result.legal_metadata["publisher"] == "uscf_investments"
    assert result.legal_metadata["route_resolution"] == "marygold_uscf_public_browser_holdings_api"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("soundwatch")
async def test_live_soundwatch_product_page_linked_full_holdings_xls():
    adapter = get_holdings_adapter("soundwatch")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="SHDG")
    _assert_live_holdings_result(result, adapter_key="soundwatch", min_rows=5)
    assert result.legal_metadata["route_resolution"] == "soundwatch_product_page_full_holdings_xls"
    assert result.legal_metadata["composition_date"]
    assert any(row.row_type == "derivative" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("wealthtrust")
async def test_live_wealthtrust_public_wltg_complete_holdings_table():
    adapter = get_holdings_adapter("wealthtrust")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="WLTG")
    _assert_live_holdings_result(result, adapter_key="wealthtrust", min_rows=20)
    assert (
        result.legal_metadata["route_resolution"]
        == "wealthtrust_public_wltg_complete_holdings_table"
    )
    assert any(row.symbol == "AAPL" for row in result.rows)
    assert any(row.row_type == "cash" for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("cultivar")
async def test_live_cultivar_current_fund_page_holdings_table():
    adapter = get_holdings_adapter("cultivar")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="CVAR")
    _assert_live_holdings_result(result, adapter_key="cultivar", min_rows=50)
    assert result.legal_metadata["route_resolution"] == "cultivar_current_fund_page_holdings_table"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("scharf")
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
@_covers_live_provider("cohanzick")
async def test_live_cohanzick_cusd_page_verified_holdings_json():
    adapter = get_holdings_adapter("cohanzick")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="CUSD")
    _assert_live_holdings_result(result, adapter_key="cohanzick", min_rows=10)
    assert result.legal_metadata["route_resolution"] == "issuer_public_current_holdings_json"
    assert result.legal_metadata["source_format"] == "json"


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("tremblant")
async def test_live_tremblant_toga_page_verified_filepoint_holdings_csv():
    adapter = get_holdings_adapter("tremblant")
    assert adapter is not None
    result = await adapter.fetch_latest(symbol="TOGA")
    _assert_live_holdings_result(result, adapter_key="tremblant", min_rows=20)
    assert (
        result.legal_metadata["route_resolution"]
        == "issuer_product_page_verified_filepoint_holdings_csv"
    )
    assert result.legal_metadata["source_format"] == "csv"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("cohen_steers")
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
@_covers_live_provider("bcp_cc")
async def test_live_bcp_cc_legacy_identity_uses_bounded_first_eagle_holdings_page():
    adapter = get_holdings_adapter("bcp_cc")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="FEOE")

    _assert_live_holdings_result(result, adapter_key="bcp_cc", min_rows=20)
    assert (
        result.legal_metadata["route_resolution"]
        == "bcp_cc_legacy_identity_first_eagle_product_page_holdings_table"
    )
    assert result.legal_metadata["source_provider"] == "first_eagle"
    assert result.legal_metadata["composition_date"]


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("mitsubishi_ufj")
async def test_live_mitsubishi_ufj_mjsc_nuxt_complete_holdings_component():
    adapter = get_holdings_adapter("mitsubishi_ufj")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="MJSC")

    _assert_live_holdings_result(result, adapter_key="mitsubishi_ufj", min_rows=80)
    assert (
        result.legal_metadata["route_resolution"]
        == "mufg_product_page_nuxt_complete_holdings_component"
    )
    assert result.legal_metadata["source_format"] == "nuxt_hydration_json"
    assert result.legal_metadata["composition_date"]
    assert any(row.extra_data.get("source_ticker") for row in result.rows)
    assert all(row.symbol is None for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("mcivy")
async def test_live_mcivy_genter_nottingham_fund_scoped_holdings_json():
    adapter = get_holdings_adapter("mcivy")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="GEND")

    _assert_live_holdings_result(result, adapter_key="mcivy", min_rows=30)
    assert (
        result.legal_metadata["route_resolution"]
        == "mcivy_genter_nottingham_fund_scoped_complete_holdings_json"
    )
    assert result.legal_metadata["publisher"] == "The Nottingham Company"
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("langar")
async def test_live_langar_lght_nottingham_fund_scoped_holdings_json():
    adapter = get_holdings_adapter("langar")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="LGHT")

    _assert_live_holdings_result(result, adapter_key="langar", min_rows=30)
    assert (
        result.legal_metadata["route_resolution"]
        == "langar_nottingham_fund_scoped_complete_holdings_json"
    )
    assert result.legal_metadata["publisher"] == "The Nottingham Company"
    assert result.legal_metadata["composition_date"]
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("little_harbor")
async def test_live_little_harbor_mstb_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("little_harbor")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="MSTB")

    _assert_live_holdings_result(result, adapter_key="little_harbor", min_rows=5)
    assert (
        result.legal_metadata["route_resolution"]
        == "little_harbor_product_page_linked_complete_holdings_xls"
    )
    assert any(row.cusip for row in result.rows)
    assert any(row.row_type in {"cash", "derivative"} for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("pettee")
async def test_live_pettee_homz_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("pettee")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="HOMZ")

    _assert_live_holdings_result(result, adapter_key="pettee", min_rows=50)
    assert (
        result.legal_metadata["route_resolution"]
        == "pettee_hoya_product_page_linked_complete_holdings_xls"
    )
    assert result.legal_metadata["publisher"] == "Hoya Capital Real Estate"
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("sound_capital")
async def test_live_sound_capital_rver_river1_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("sound_capital")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="RVER")

    _assert_live_holdings_result(result, adapter_key="sound_capital", min_rows=15)
    assert (
        result.legal_metadata["route_resolution"]
        == "sound_capital_river1_product_page_linked_complete_holdings_xls"
    )
    assert result.legal_metadata["publisher"] == "River1 Asset Management"
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("sovereign")
async def test_live_sovereign_sovf_product_page_linked_holdings_workbook():
    adapter = get_holdings_adapter("sovereign")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="SOVF")

    _assert_live_holdings_result(result, adapter_key="sovereign", min_rows=50)
    assert (
        result.legal_metadata["route_resolution"]
        == "sovereign_sovf_product_page_linked_complete_holdings_xls"
    )
    assert any(row.cusip for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@_covers_live_provider("eldridge")
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
@_covers_live_provider("corient")
async def test_live_corient_fundx_product_page_declared_csv_viewer_holdings():
    adapter = get_holdings_adapter("corient")
    assert adapter is not None

    result = await adapter.fetch_latest(symbol="XCOR")

    _assert_live_holdings_result(result, adapter_key="corient", min_rows=10)
    assert (
        result.legal_metadata["route_resolution"]
        == "fundx_product_page_declared_csv_viewer_holdings_json"
    )
    assert result.legal_metadata["publisher"] == "fundx"
    assert result.legal_metadata["parent_issuer"] == "corient"
    assert any(row.symbol == "IOO" for row in result.rows)
    assert any(row.cusip for row in result.rows)


def _parametrized_live_provider_keys(*tests) -> set[str]:
    keys: set[str] = set()
    for test in tests:
        for mark in getattr(test, "pytestmark", []):
            if mark.name != "parametrize" or len(mark.args) < 2:
                continue
            for case in mark.args[1]:
                if isinstance(case, tuple) and case and isinstance(case[0], str):
                    keys.add(case[0])
    return keys


def test_live_backed_providers_each_have_a_concrete_live_route_test():
    """Keep a provider from being marked native/live-backed without a live test route."""

    parametrized = _parametrized_live_provider_keys(
        test_live_issuer_direct_holdings_routes_return_parseable_rows,
        test_live_issuer_product_pages_discover_parseable_holdings_files,
    )
    bespoke = {
        adapter_key
        for value in globals().values()
        if callable(value)
        and isinstance(adapter_key := getattr(value, "_live_provider_adapter_key", None), str)
    }
    assert parametrized | bespoke == LIVE_BACKED_ISSUER_ADAPTERS


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
