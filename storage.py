from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from paths import data_dir


DB_PATH = data_dir() / "conditions.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize() -> None:
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS conditions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'custom',
                raw_text TEXT NOT NULL DEFAULT '',
                rules_json TEXT NOT NULL DEFAULT '[]',
                markets_json TEXT NOT NULL DEFAULT '["KOSPI", "KOSDAQ"]',
                exclusions_json TEXT NOT NULL DEFAULT '[]',
                timeframe TEXT NOT NULL DEFAULT '',
                kiwoom_seq TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(conditions)")}
        if "timeframe" not in columns:
            db.execute("ALTER TABLE conditions ADD COLUMN timeframe TEXT NOT NULL DEFAULT ''")


def _decode(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["rules"] = json.loads(item.pop("rules_json") or "[]")
    item["markets"] = json.loads(item.pop("markets_json") or "[]")
    item["exclusions"] = json.loads(item.pop("exclusions_json") or "[]")
    return item


def list_conditions() -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM conditions ORDER BY updated_at DESC, name COLLATE NOCASE"
        ).fetchall()
    return [_decode(row) for row in rows]


def get_condition(condition_id: str) -> dict | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM conditions WHERE id = ?", (condition_id,)).fetchone()
    return _decode(row) if row else None


def save_condition(payload: dict, condition_id: str | None = None) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("조건식 이름을 입력해 주세요.")
    mode = payload.get("mode", "custom")
    if mode not in {"custom", "kiwoom", "signal"}:
        raise ValueError("지원하지 않는 조건식 종류입니다.")

    now = datetime.now().isoformat(timespec="seconds")
    condition_id = condition_id or uuid.uuid4().hex
    existing = get_condition(condition_id)
    created_at = existing["created_at"] if existing else now
    values = (
        condition_id,
        name,
        mode,
        str(payload.get("raw_text", "")),
        json.dumps(payload.get("rules", []), ensure_ascii=False),
        json.dumps(payload.get("markets", ["KOSPI", "KOSDAQ"]), ensure_ascii=False),
        json.dumps(payload.get("exclusions", []), ensure_ascii=False),
        str(payload.get("timeframe", "")),
        payload.get("kiwoom_seq"),
        created_at,
        now,
    )
    with _connect() as db:
        db.execute(
            """
            INSERT INTO conditions
              (id, name, mode, raw_text, rules_json, markets_json, exclusions_json,
               timeframe, kiwoom_seq, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              mode=excluded.mode,
              raw_text=excluded.raw_text,
              rules_json=excluded.rules_json,
              markets_json=excluded.markets_json,
              exclusions_json=excluded.exclusions_json,
              timeframe=excluded.timeframe,
              kiwoom_seq=excluded.kiwoom_seq,
              updated_at=excluded.updated_at
            """,
            values,
        )
    return get_condition(condition_id)


def import_kiwoom_conditions(items: list[dict]) -> list[dict]:
    imported = []
    for item in items:
        seq = str(item.get("seq", "")).strip()
        name = str(item.get("name", "")).strip()
        if not seq or not name:
            continue
        imported.append(
            save_condition(
                {
                    "name": name,
                    "mode": "kiwoom",
                    "kiwoom_seq": seq,
                    "raw_text": "영웅문에 저장된 조건식",
                    "rules": [],
                    "markets": ["KOSPI", "KOSDAQ"],
                    "exclusions": [],
                },
                condition_id=f"kiwoom-{seq}",
            )
        )
    return imported


def delete_condition(condition_id: str) -> bool:
    with _connect() as db:
        cursor = db.execute("DELETE FROM conditions WHERE id = ?", (condition_id,))
    return cursor.rowcount > 0
