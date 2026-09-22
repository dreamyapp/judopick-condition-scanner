import pytest
import sqlite3

from signal_formula import parse_signal_formula, signal_on_latest_bar, validate_signal_formula
from scanner import scan_signal
import storage


FORMULA = """TP=(H+L+C)/3;
P=TP/1000;
W0=V/100000000;
CW=Sum(W0);
CP=Sum(P\\*W0);
NEW=DATE!=DATE(1);
BW=ValueWhen(1,NEW,CW(1));
BP=ValueWhen(1,NEW,CP(1));
W=CW-BW;
PW=CP-BP;
VW=IF(W==0,0,(PW/W)\\*1000);
UP=VW>VW(1);
BRK=C(1)<=VW(1) && C>VW;
SUP=C(1)>VW(1) && L<=VW && C>VW;
SIG=NEW==0 && VW>0 && UP && (BRK || SUP);
SIG && SIG(1)==0
\\--------"""


def bar(date, time, high, low, close, volume=100):
    return {"cntr_tm": f"{date}{time}00", "high_pric": str(high),
            "low_pric": str(low), "cur_prc": str(close), "trde_qty": str(volume)}


def test_accepts_pasted_formula_with_markdown_escaping():
    parsed = parse_signal_formula(FORMULA)
    assert parsed["mode"] == "signal"
    assert "직접 만든 수식" in parsed["description"]
    assert validate_signal_formula(FORMULA.replace(" && L<=VW", "&#x20; && L<=VW"))


def test_accepts_user_modified_formula():
    assert validate_signal_formula(FORMULA.replace("UP=VW>VW(1)", "UP=VW<VW(1)"))


def test_rejects_unknown_function():
    with pytest.raises(ValueError, match="지원하지 않습니다"):
        validate_signal_formula("MYSTERY(C,20)>0")


def test_latest_breakout_is_first_signal_only():
    bars = [
        bar("20260921", "1530", 100, 100, 100),
        bar("20260922", "0900", 100, 100, 100),
        bar("20260922", "0905", 99, 99, 99),
        bar("20260922", "0910", 104, 100, 104),
    ]
    assert signal_on_latest_bar(bars)
    assert not signal_on_latest_bar(bars + [bar("20260922", "0915", 105, 101, 105)])


def test_first_bar_of_day_never_signals():
    assert not signal_on_latest_bar([bar("20260922", "0900", 105, 95, 105)])


def test_support_rebound_signals():
    bars = [
        bar("20260921", "1530", 99, 99, 99),
        bar("20260922", "0900", 100, 100, 100),
        bar("20260922", "0905", 102, 102, 102),
        bar("20260922", "0910", 103, 103, 103),
        bar("20260922", "0915", 104, 100, 104),
    ]
    assert signal_on_latest_bar(bars)


class FakeClient:
    def stock_list(self, market):
        return [{"code": "000001", "name": "테스트"}]

    def minute_chart(self, code, timeframe):
        assert code == "000001" and timeframe == "5"
        return [bar("20260921", "1530", 99, 99, 99),
                bar("20260922", "0900", 100, 100, 100),
                bar("20260922", "0905", 99, 99, 99),
                bar("20260922", "0910", 104, 100, 104)]


def test_scan_signal_uses_latest_chart(monkeypatch):
    monkeypatch.setattr("scanner.time.sleep", lambda _: None)
    results = scan_signal({"raw_text": FORMULA, "timeframe": "5",
                           "markets": ["KOSPI"], "exclusions": []}, client=FakeClient())
    assert [item["code"] for item in results] == ["000001"]


def test_signal_condition_can_be_saved_without_changing_other_conditions(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "conditions.db")
    storage.initialize()
    old = storage.save_condition({"name": "기존 조건", "rules": [], "mode": "custom"})
    signal = storage.save_condition({"name": "VWAP", "mode": "signal",
                                     "raw_text": FORMULA, "timeframe": "5"})
    assert storage.get_condition(signal["id"])["timeframe"] == "5"
    assert storage.get_condition(old["id"])["mode"] == "custom"


def test_existing_database_adds_timeframe_without_deleting_conditions(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE conditions (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
            raw_text TEXT NOT NULL, rules_json TEXT NOT NULL,
            markets_json TEXT NOT NULL, exclusions_json TEXT NOT NULL,
            kiwoom_seq TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        db.execute("""INSERT INTO conditions VALUES
            ('old', '보존', 'custom', '', '[]', '["KOSPI"]', '[]', NULL, 'a', 'a')""")
    monkeypatch.setattr(storage, "DB_PATH", path)
    storage.initialize()
    assert storage.get_condition("old")["name"] == "보존"
    assert storage.get_condition("old")["timeframe"] == ""
