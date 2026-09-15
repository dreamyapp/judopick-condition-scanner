import pytest

from condition_parser import parse_condition_text, validate_rule


def test_parses_full_korean_condition():
    result = parse_condition_text(
        """조건식명: 거래량 급증주
시장: 코스피, 코스닥
등락률: 3% 이상
현재가: 1만원 이상 5만원 이하
거래대금: 100억 원 이상
제외: ETF, ETN, 스팩"""
    )

    assert result.name == "거래량 급증주"
    assert result.markets == ["KOSPI", "KOSDAQ"]
    assert result.exclusions == ["ETF", "ETN", "스팩"]
    assert result.warnings == []
    assert result.rules[0]["field"] == "change_rate"
    assert result.rules[0]["value"] == 3
    assert result.rules[1]["operator"] == "between"
    assert result.rules[1]["value"] == 10_000
    assert result.rules[1]["value2"] == 50_000
    assert result.rules[2]["value"] == 10_000_000_000


def test_warns_for_unsupported_average_condition():
    result = parse_condition_text("20일 평균 거래량 대비: 200% 이상")
    assert not result.rules
    assert result.warnings


def test_validate_rule_rejects_unknown_field():
    with pytest.raises(ValueError):
        validate_rule({"field": "unknown", "operator": "gte", "value": 1})

