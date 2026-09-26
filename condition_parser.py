from __future__ import annotations

import re
import math
from dataclasses import dataclass


FIELD_LABELS = {
    "price": "현재가",
    "change_rate": "등락률",
    "volume": "거래량",
    "trading_value": "거래대금",
    "market_cap": "시가총액",
}

UNIT_LABELS = {
    "price": "원",
    "change_rate": "%",
    "volume": "주",
    "trading_value": "원",
    "market_cap": "원",
}

OPERATOR_LABELS = {
    "gte": "이상",
    "gt": "초과",
    "lte": "이하",
    "lt": "미만",
    "between": "범위",
}

FIELD_ALIASES = {
    "현재가": "price",
    "주가": "price",
    "가격": "price",
    "등락률": "change_rate",
    "등락율": "change_rate",
    "상승률": "change_rate",
    "거래량": "volume",
    "누적거래량": "volume",
    "거래대금": "trading_value",
    "시가총액": "market_cap",
    "시총": "market_cap",
}


@dataclass
class ParseResult:
    name: str
    rules: list[dict]
    markets: list[str]
    exclusions: list[str]
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "rules": self.rules,
            "markets": self.markets,
            "exclusions": self.exclusions,
            "warnings": self.warnings,
        }


def _number(text: str, field: str) -> float:
    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        raise ValueError("숫자를 찾지 못했습니다.")
    value = float(match.group())

    multiplier = 1.0
    suffix = cleaned[match.end() :]
    if field in {"price", "trading_value", "market_cap"}:
        if "조" in suffix:
            multiplier = 1_000_000_000_000
        elif "억" in suffix:
            multiplier = 100_000_000
        elif "만" in suffix:
            multiplier = 10_000
        elif "천" in suffix:
            multiplier = 1_000
    elif field == "volume":
        if "백만" in suffix:
            multiplier = 1_000_000
        elif "만" in suffix:
            multiplier = 10_000
        elif "천" in suffix:
            multiplier = 1_000
    return value * multiplier


def _rule(field: str, operator: str, value: float, value2: float | None = None) -> dict:
    label = f"{FIELD_LABELS[field]} {format_value(field, value)} {OPERATOR_LABELS[operator]}"
    if operator == "between" and value2 is not None:
        label = f"{FIELD_LABELS[field]} {format_value(field, value)} ~ {format_value(field, value2)}"
    result = {"field": field, "operator": operator, "value": value, "label": label}
    if value2 is not None:
        result["value2"] = value2
    return result


def format_value(field: str, value: float) -> str:
    if field == "change_rate":
        return f"{value:g}%"
    if field in {"trading_value", "market_cap"} and abs(value) >= 100_000_000:
        return f"{value / 100_000_000:g}억 원"
    if field == "volume" and abs(value) >= 10_000:
        return f"{value / 10_000:g}만 주"
    if field == "price":
        return f"{value:,.0f}원"
    return f"{value:,.0f}{UNIT_LABELS[field]}"


def _parse_metric(field: str, value_text: str) -> dict:
    normalized = value_text.strip()
    range_match = re.search(r"(.+?)(?:~|부터)(.+?)(?:까지)?$", normalized)
    if range_match:
        low = _number(range_match.group(1), field)
        high = _number(range_match.group(2), field)
        return _rule(field, "between", min(low, high), max(low, high))

    pairs = re.findall(r"([-+]?\d[\d,.]*\s*(?:조|억|백만|만|천)?\s*(?:원|주|%)?)\s*(이상|초과|이하|미만)", normalized)
    if len(pairs) >= 2:
        parsed = [(_number(number, field), op) for number, op in pairs]
        lower = next((value for value, op in parsed if op in {"이상", "초과"}), None)
        upper = next((value for value, op in parsed if op in {"이하", "미만"}), None)
        if lower is not None and upper is not None:
            return _rule(field, "between", lower, upper)

    operator = "gte"
    if "초과" in normalized:
        operator = "gt"
    elif "이하" in normalized:
        operator = "lte"
    elif "미만" in normalized:
        operator = "lt"
    value = _number(normalized, field)
    return _rule(field, operator, value)


def parse_condition_text(text: str) -> ParseResult:
    name = ""
    rules: list[dict] = []
    markets = ["KOSPI", "KOSDAQ"]
    exclusions: list[str] = []
    warnings: list[str] = []

    raw_lines = re.split(r"[\r\n]+", text)
    lines = [re.sub(r"^[\s•·*-]+", "", line).strip() for line in raw_lines if line.strip()]

    for line in lines:
        key, separator, value = line.partition(":")
        if not separator:
            key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if key in {"조건식명", "조건식 이름", "이름"} and value:
            name = value
            continue

        if key in {"시장", "대상시장", "거래소"} and value:
            selected = []
            lowered = value.lower()
            if "코스피" in value or "kospi" in lowered:
                selected.append("KOSPI")
            if "코스닥" in value or "kosdaq" in lowered:
                selected.append("KOSDAQ")
            if selected:
                markets = selected
            else:
                warnings.append(f"시장 조건을 이해하지 못했습니다: {line}")
            continue

        if key in {"제외", "제외종목", "제외 항목"} and value:
            exclusions.extend(
                token.strip().upper()
                for token in re.split(r"[,/·]", value)
                if token.strip()
            )
            continue

        if ("평균" in line or "대비" in line) and any(alias in line for alias in FIELD_ALIASES):
            warnings.append(f"평균 대비 조건은 아직 지원하지 않습니다: {line}")
            continue

        field = FIELD_ALIASES.get(key)
        if not field:
            # 콜론 없이 쓴 간단한 문장도 지원한다.
            matched_alias = next((alias for alias in FIELD_ALIASES if line.startswith(alias)), None)
            if matched_alias:
                field = FIELD_ALIASES[matched_alias]
                value = line[len(matched_alias) :].strip()

        if field:
            if "평균" in value or "대비" in value:
                warnings.append(f"평균 대비 조건은 아직 지원하지 않습니다: {line}")
                continue
            try:
                rules.append(_parse_metric(field, value))
            except ValueError:
                warnings.append(f"숫자를 확인해 주세요: {line}")
            continue

        if not name and len(lines) == 1:
            name = line[:40]
        else:
            warnings.append(f"이 문장은 아직 지원하지 않습니다: {line}")

    exclusions = list(dict.fromkeys(exclusions))
    return ParseResult(name, rules, markets, exclusions, warnings)


def validate_rule(rule: dict) -> dict:
    field = str(rule.get("field", ""))
    operator = str(rule.get("operator", ""))
    if field not in FIELD_LABELS:
        raise ValueError("조건 항목을 다시 선택해 주세요.")
    if operator not in OPERATOR_LABELS:
        raise ValueError("비교 방법을 다시 선택해 주세요.")
    try:
        value = float(rule.get("value"))
    except (TypeError, ValueError):
        raise ValueError("필터 값을 숫자로 입력해 주세요.") from None
    if not math.isfinite(value):
        raise ValueError("필터 값을 숫자로 입력해 주세요.")
    value2 = None
    if operator == "between":
        try:
            value2 = float(rule.get("value2"))
        except (TypeError, ValueError):
            raise ValueError("범위의 끝 값을 숫자로 입력해 주세요.") from None
        if not math.isfinite(value2):
            raise ValueError("범위의 끝 값을 숫자로 입력해 주세요.")
    return _rule(field, operator, value, value2)
