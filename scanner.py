from __future__ import annotations

import time
import math
from datetime import datetime
from typing import Callable

from condition_parser import validate_rule
from kiwoom_client import KiwoomClient, clean_code, normalize_condition_result
from formula_engine import compile_formula, evaluate_latest
from signal_formula import TIMEFRAMES


MARKET_CODES = {"KOSPI": "0", "KOSDAQ": "10"}


def _number(row: dict, *keys: str, absolute: bool = False) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                parsed = float(str(value).replace(",", "").replace(" ", ""))
                if math.isfinite(parsed):
                    return abs(parsed) if absolute else parsed
            except ValueError:
                continue
    return 0.0


def normalize_quote(row: dict, universe: dict[str, dict]) -> dict:
    code = clean_code(row.get("stk_cd") or row.get("9001") or row.get("code") or "")
    base = universe.get(code, {})
    price = _number(row, "cur_prc", "10", absolute=True)
    volume = _number(row, "trde_qty", "acc_trde_qty", "13", absolute=True)
    listed = _number(base, "listCount", "listcount", absolute=True)
    market_cap = _number(row, "mac", absolute=True)
    if market_cap:
        market_cap *= 100_000_000  # 키움 mac은 억원 단위
    elif listed and price:
        market_cap = listed * price
    trading_value = _number(row, "trde_prica", "acc_trde_prica", absolute=True)
    if trading_value:
        trading_value *= 1_000_000  # 키움 거래대금은 백만원 단위
    if not trading_value and price and volume:
        trading_value = price * volume
    return {
        "code": code,
        "name": row.get("stk_nm") or row.get("302") or base.get("name") or code,
        "market": base.get("_market", ""),
        "price": price,
        "change_rate": _number(row, "flu_rt", "12"),
        "volume": volume,
        "trading_value": trading_value,
        "market_cap": market_cap,
    }


def matches_rule(stock: dict, rule: dict) -> bool:
    checked = validate_rule(rule)
    actual = float(stock.get(checked["field"], 0) or 0)
    expected = checked["value"]
    operator = checked["operator"]
    if operator == "gte":
        return actual >= expected
    if operator == "gt":
        return actual > expected
    if operator == "lte":
        return actual <= expected
    if operator == "lt":
        return actual < expected
    if operator == "between":
        return min(expected, checked["value2"]) <= actual <= max(expected, checked["value2"])
    return False


def matches_all(stock: dict, rules: list[dict]) -> bool:
    return all(matches_rule(stock, rule) for rule in rules)


def _is_excluded(name: str, market_name: str, exclusions: list[str]) -> bool:
    upper_name = name.upper().replace(" ", "")
    upper_market = market_name.upper().replace(" ", "")
    return any(
        keyword.upper().replace(" ", "") in upper_name
        or keyword.upper().replace(" ", "") in upper_market
        for keyword in exclusions
    )


def scan_custom(
    condition: dict,
    progress: Callable[[int, str], None] | None = None,
    client: KiwoomClient | None = None,
) -> list[dict]:
    client = client or KiwoomClient()
    progress = progress or (lambda percent, message: None)
    rules = [validate_rule(rule) for rule in condition.get("rules", [])]
    if not rules:
        raise ValueError("검색 조건을 한 개 이상 입력해 주세요.")

    markets = condition.get("markets") or ["KOSPI", "KOSDAQ"]
    exclusions = list(dict.fromkeys(condition.get("exclusions") or []))
    universe: dict[str, dict] = {}
    progress(5, "검색할 종목을 준비하고 있습니다.")
    for index, market in enumerate(markets):
        market_code = MARKET_CODES.get(market)
        if not market_code:
            continue
        for row in client.stock_list(market_code):
            code = clean_code(row.get("code", ""))
            name = str(row.get("name", ""))
            market_name = str(row.get("marketName") or row.get("marketname") or "")
            if code and name and not _is_excluded(name, market_name, exclusions):
                row["_market"] = market
                universe[code] = row
        progress(10 + int((index + 1) / max(len(markets), 1) * 10), f"{market} 종목을 준비했습니다.")

    codes = list(universe)
    if not codes:
        return []
    batch_size = 30
    matched: list[dict] = []
    total_batches = (len(codes) + batch_size - 1) // batch_size
    for batch_index, start in enumerate(range(0, len(codes), batch_size)):
        batch = codes[start : start + batch_size]
        rows = client.stock_quotes(batch)
        for row in rows:
            stock = normalize_quote(row, universe)
            if stock["code"] and matches_all(stock, rules):
                matched.append(stock)
        percent = 20 + int((batch_index + 1) / max(total_batches, 1) * 75)
        progress(percent, f"현재 {start + len(batch):,}개 종목을 확인했습니다.")
        if batch_index + 1 < total_batches:
            time.sleep(0.2)

    seen = set()
    unique = []
    for stock in sorted(matched, key=lambda item: item.get("trading_value", 0), reverse=True):
        if stock["code"] in seen:
            continue
        seen.add(stock["code"])
        stock["found_at"] = datetime.now().strftime("%H:%M:%S")
        unique.append(stock)
    progress(99, f"{len(unique):,}개 종목의 조회를 마쳤습니다. 결과를 준비하고 있습니다.")
    return unique


def scan_kiwoom(condition: dict, client: KiwoomClient | None = None) -> list[dict]:
    client = client or KiwoomClient()
    rows = client.search_saved_condition(str(condition.get("kiwoom_seq", "")))
    results = []
    for row in rows:
        stock = normalize_condition_result(row)
        stock["found_at"] = datetime.now().strftime("%H:%M:%S")
        results.append(stock)
    return results


def scan_signal(
    condition: dict,
    progress: Callable[[int, str], None] | None = None,
    client: KiwoomClient | None = None,
) -> list[dict]:
    compiled = compile_formula(str(condition.get("raw_text", "")))
    timeframe = str(condition.get("timeframe", ""))
    if timeframe not in TIMEFRAMES:
        raise ValueError("검색할 차트 봉을 선택해 주세요.")
    rules = [validate_rule(rule) for rule in condition.get("rules", [])]
    client = client or KiwoomClient()
    progress = progress or (lambda percent, message: None)
    markets = condition.get("markets") or ["KOSPI", "KOSDAQ"]
    exclusions = condition.get("exclusions") or []
    universe: dict[str, dict] = {}
    progress(3, "검색할 종목 목록을 준비하고 있습니다.")
    for market in markets:
        market_code = MARKET_CODES.get(market)
        if not market_code:
            continue
        for row in client.stock_list(market_code):
            code = clean_code(row.get("code", ""))
            name = str(row.get("name", ""))
            market_name = str(row.get("marketName") or row.get("marketname") or "")
            if code and name and not _is_excluded(name, market_name, exclusions):
                row["_market"] = market
                universe[code] = row
    codes = list(universe)
    matching_quotes: dict[str, dict] = {}
    if rules and codes:
        candidates = []
        batch_size = 30
        total_batches = (len(codes) + batch_size - 1) // batch_size
        for batch_index, start in enumerate(range(0, len(codes), batch_size)):
            batch = codes[start:start + batch_size]
            for row in client.stock_quotes(batch):
                stock = normalize_quote(row, universe)
                if stock["code"] in universe and matches_all(stock, rules):
                    if stock["code"] not in matching_quotes:
                        candidates.append(stock["code"])
                    matching_quotes[stock["code"]] = stock
            progress(5 + int((batch_index + 1) / total_batches * 25),
                     f"추가 필터 확인 중 · {min(start + batch_size, len(codes)):,}/{len(codes):,}개")
            if batch_index + 1 < total_batches:
                time.sleep(0.2)
        codes = candidates
        progress(30, f"추가 필터를 통과한 {len(codes):,}개 종목의 수식을 확인합니다.")
    results = []
    for index, code in enumerate(codes):
        if index:
            time.sleep(0.2)
        bars = client.daily_chart(code) if timeframe == "D" else client.minute_chart(code, timeframe)
        matched, last = evaluate_latest(compiled, bars)
        if matched and last:
            quote = matching_quotes.get(code, {})
            results.append({
                "code": code,
                "name": universe[code]["name"],
                "market": universe[code]["_market"],
                "price": _number(last, "cur_prc", absolute=True),
                "change_rate": quote.get("change_rate", 0),
                "volume": _number(last, "trde_qty", absolute=True),
                "trading_value": quote.get("trading_value", 0),
                "market_cap": quote.get("market_cap", 0),
                "found_at": datetime.now().strftime("%H:%M:%S"),
                "bar_time": str(last.get("cntr_tm") or last.get("dt") or ""),
            })
        start_percent = 30 if rules else 5
        progress(start_percent + int((index + 1) / max(len(codes), 1) * (99 - start_percent)),
                 f"{index + 1:,}/{len(codes):,}개 종목 확인 중 · 신호 {len(results):,}개")
    progress(99, f"{len(results):,}개 종목의 조회를 마쳤습니다. 결과를 준비하고 있습니다.")
    return results
