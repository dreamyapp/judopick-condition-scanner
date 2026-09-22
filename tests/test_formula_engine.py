import pytest

from formula_engine import compile_formula, evaluate_latest, looks_like_formula
from scanner import scan_signal


def bar(date, close, volume=100):
    return {"dt": date, "open_pric": str(close), "high_pric": str(close),
            "low_pric": str(close), "cur_prc": str(close), "trde_qty": str(volume)}


def test_custom_average_crossup_on_daily_bars():
    formula = compile_formula("A=MA(C,3); CROSSUP(C,A)")
    matched, latest = evaluate_latest(formula, [
        bar("20260918", 10), bar("20260919", 12), bar("20260920", 11),
        bar("20260921", 10), bar("20260922", 13),
    ])
    assert matched
    assert latest["dt"] == "20260922"


def test_last_signal_is_not_latched_after_previous_bar():
    formula = compile_formula("C>MA(C,2) && C(1)<=REF(MA(C,2),1)")
    bars = [bar("20260919", 10), bar("20260920", 9), bar("20260921", 12)]
    assert evaluate_latest(formula, bars)[0]
    assert not evaluate_latest(formula, bars + [bar("20260922", 13)])[0]


def test_sum_ema_hhv_llv_and_valuewhen():
    formula = compile_formula("A=SUM(V,2); B=EMA(C,2); D=VALUEWHEN(1,C>10,C); A==200 && B>10 && HHV(C,2)==12 && LLV(C,2)==11 && D==12")
    assert evaluate_latest(formula, [bar("20260920", 10), bar("20260921", 11), bar("20260922", 12)])[0]


def test_multiline_formula_and_html_escapes():
    formula = compile_formula("X=C>MA(C,2);\nX &&\nC(1) &lt;= REF(MA(C,2),1)")
    assert evaluate_latest(formula, [bar("20260920", 10), bar("20260921", 9), bar("20260922", 12)])[0]
    assert compile_formula("```text\nC>MA(C,2)\n```")
    assert compile_formula("A=C;\\\nA>C(1)")


def test_numeric_indicator_alone_is_not_a_stock_search_signal():
    with pytest.raises(ValueError, match="마지막 줄에는 종목을 찾을 신호 조건"):
        compile_formula("AVWAP=MA(C,20); AVWAP")
    assert compile_formula("AVWAP=MA(C,20); C>AVWAP")


@pytest.mark.parametrize("source", [
    "__import__('os').system('true')", "C.__class__", "[C for x in V]",
    "C[0]", "C=10; C>0", "X=X+1; X>0", "MA(C,0)>0", "REF(C,-1)>0",
])
def test_unsafe_or_invalid_formula_is_rejected(source):
    with pytest.raises(ValueError):
        compile_formula(source)


def test_korean_rules_stay_out_of_formula_parser():
    assert not looks_like_formula("조건식명: 거래량 증가\n현재가: 1만원 이상")
    assert looks_like_formula("C>MA(C,20)")


def test_daily_scanner_uses_daily_chart():
    class Client:
        def stock_list(self, market):
            return [{"code": "123456", "name": "예시"}]

        def daily_chart(self, code):
            assert code == "123456"
            return [bar("20260921", 10), bar("20260922", 12)]

    results = scan_signal({"raw_text": "C>C(1)", "timeframe": "D",
                           "markets": ["KOSPI"], "exclusions": []}, client=Client())
    assert results[0]["bar_time"] == "20260922"
