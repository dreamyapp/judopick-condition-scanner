"""Compatibility helpers for chart-signal conditions."""

from __future__ import annotations

from formula_engine import compile_formula, evaluate_latest, looks_like_formula


TIMEFRAMES = {"1", "3", "5", "10", "15", "30", "45", "60", "D"}

DEFAULT_FORMULA = """TP=(H+L+C)/3;
P=TP/1000;
W0=V/100000000;
CW=Sum(W0);
CP=Sum(P*W0);
NEW=DATE!=DATE(1);
BW=ValueWhen(1,NEW,CW(1));
BP=ValueWhen(1,NEW,CP(1));
W=CW-BW;
PW=CP-BP;
VW=IF(W==0,0,(PW/W)*1000);
UP=VW>VW(1);
BRK=C(1)<=VW(1)&&C>VW;
SUP=C(1)>VW(1)&&L<=VW&&C>VW;
SIG=NEW==0&&VW>0&&UP&&(BRK||SUP);
SIG&&SIG(1)==0"""


def looks_like_signal_formula(text: str) -> bool:
    return looks_like_formula(text)


def validate_signal_formula(text: str) -> str:
    return compile_formula(text).description


def parse_signal_formula(text: str) -> dict:
    description = validate_signal_formula(text)
    return {
        "name": "", "mode": "signal", "rules": [],
        "markets": ["KOSPI", "KOSDAQ"], "exclusions": [],
        "warnings": [], "description": description,
    }


def signal_on_latest_bar(bars: list[dict]) -> bool:
    return evaluate_latest(compile_formula(DEFAULT_FORMULA), bars)[0]
