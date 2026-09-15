from scanner import matches_all, normalize_quote


def test_normalize_quote_converts_kiwoom_units():
    row = {
        "stk_cd": "005930",
        "stk_nm": "삼성전자",
        "cur_prc": "-70000",
        "flu_rt": "+3.50",
        "trde_qty": "1000000",
        "trde_prica": "70000",
        "mac": "4000000",
    }
    universe = {"005930": {"name": "삼성전자", "_market": "KOSPI", "listCount": "1000000"}}
    stock = normalize_quote(row, universe)

    assert stock["price"] == 70_000
    assert stock["change_rate"] == 3.5
    assert stock["trading_value"] == 70_000_000_000
    assert stock["market_cap"] == 400_000_000_000_000


def test_matches_all_supported_rules():
    stock = {
        "price": 25_000,
        "change_rate": 4.2,
        "volume": 1_500_000,
        "trading_value": 20_000_000_000,
        "market_cap": 1_000_000_000_000,
    }
    rules = [
        {"field": "price", "operator": "between", "value": 10_000, "value2": 50_000},
        {"field": "change_rate", "operator": "gte", "value": 3},
        {"field": "trading_value", "operator": "gte", "value": 10_000_000_000},
    ]
    assert matches_all(stock, rules)

