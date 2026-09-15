from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import requests
import websocket

from credentials import Credentials, get_credentials
from paths import data_dir


TOKEN_FILE = data_dir() / "token.json"


class KiwoomError(RuntimeError):
    pass


def _safe_number(value, absolute: bool = False) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace(" ", "").strip()
    if not text:
        return 0.0
    try:
        number = float(text)
        return abs(number) if absolute else number
    except ValueError:
        return 0.0


def clean_code(value: str) -> str:
    code = str(value or "").strip()
    if code.startswith("A") and len(code) >= 7:
        code = code[1:]
    return code.split("_")[0]


class KiwoomClient:
    def __init__(self, credentials: Credentials | None = None):
        self.credentials = credentials or get_credentials()
        if not self.credentials.configured:
            raise KiwoomError("먼저 키움 API 키를 설정해 주세요.")
        self._token = ""
        self._expires_at: datetime | None = None
        self._token_lock = threading.Lock()
        self._load_token()

    @property
    def websocket_url(self) -> str:
        host = "mockapi.kiwoom.com" if self.credentials.is_mock else "api.kiwoom.com"
        return f"wss://{host}:10000/api/dostk/websocket"

    def _credential_fingerprint(self) -> str:
        raw = f"{self.credentials.base_url}|{self.credentials.app_key}|{self.credentials.secret_key}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def _load_token(self) -> None:
        try:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            if data.get("fingerprint") != self._credential_fingerprint():
                return
            expires = datetime.fromisoformat(data.get("expires_at", ""))
            if datetime.now() < expires - timedelta(minutes=10):
                self._token = data.get("token", "")
                self._expires_at = expires
        except (OSError, ValueError, TypeError):
            return

    def _save_token(self) -> None:
        if not self._token or not self._expires_at:
            return
        TOKEN_FILE.write_text(
            json.dumps(
                {
                    "fingerprint": self._credential_fingerprint(),
                    "token": self._token,
                    "expires_at": self._expires_at.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        try:
            TOKEN_FILE.chmod(0o600)
        except OSError:
            pass

    def token(self) -> str:
        with self._token_lock:
            if self._token and self._expires_at:
                if datetime.now() < self._expires_at - timedelta(minutes=10):
                    return self._token

            try:
                response = requests.post(
                    f"{self.credentials.base_url}/oauth2/token",
                    headers={"Content-Type": "application/json;charset=UTF-8"},
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self.credentials.app_key,
                        "secretkey": self.credentials.secret_key,
                    },
                    timeout=15,
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise KiwoomError("키움 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.") from exc

            if data.get("return_code") not in (0, "0"):
                message = data.get("return_msg") or "API 키를 확인해 주세요."
                raise KiwoomError(f"키움 연결 실패: {message}")
            self._token = data.get("token", "")
            if not self._token:
                raise KiwoomError("키움에서 접근 토큰을 받지 못했습니다.")
            expires_text = str(data.get("expires_dt", ""))
            try:
                self._expires_at = datetime.strptime(expires_text, "%Y%m%d%H%M%S")
            except ValueError:
                self._expires_at = datetime.now() + timedelta(hours=23)
            self._save_token()
            return self._token

    def test_connection(self) -> dict:
        self.token()
        return {"ok": True, "mode": "모의투자" if self.credentials.is_mock else "실전투자"}

    def post(self, api_id: str, body: dict, path: str, timeout: int = 20) -> dict:
        try:
            response = requests.post(
                f"{self.credentials.base_url}{path}",
                headers={
                    "Content-Type": "application/json;charset=UTF-8",
                    "authorization": f"Bearer {self.token()}",
                    "api-id": api_id,
                },
                json=body,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise KiwoomError("종목 정보를 받지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
        if data.get("return_code") not in (None, 0, "0"):
            raise KiwoomError(data.get("return_msg") or "키움 조회에 실패했습니다.")
        return data

    def stock_list(self, market_code: str) -> list[dict]:
        data = self.post("ka10099", {"mrkt_tp": market_code}, "/api/dostk/stkinfo", timeout=30)
        return data.get("list") or []

    def stock_quotes(self, codes: list[str]) -> list[dict]:
        if not codes:
            return []
        data = self.post(
            "ka10095",
            {"stk_cd": "|".join(codes)},
            "/api/dostk/stkinfo",
            timeout=30,
        )
        for key in ("atn_stk_infr", "stk_infr", "list", "output"):
            rows = data.get(key)
            if isinstance(rows, list):
                return rows
        # 일부 환경에서는 단일 종목 응답이 최상위 객체로 온다.
        return [data] if data.get("stk_cd") else []

    def _open_condition_socket(self):
        try:
            ws = websocket.create_connection(self.websocket_url, timeout=15)
            ws.send(json.dumps({"trnm": "LOGIN", "token": self.token()}))
            response = self._receive(ws, "LOGIN")
        except (OSError, websocket.WebSocketException) as exc:
            raise KiwoomError("키움 실시간 서버에 연결하지 못했습니다.") from exc
        if response.get("return_code") not in (0, "0"):
            ws.close()
            raise KiwoomError(response.get("return_msg") or "키움 실시간 로그인에 실패했습니다.")
        return ws

    @staticmethod
    def _receive(ws, expected: str) -> dict:
        while True:
            try:
                message = json.loads(ws.recv())
            except (ValueError, websocket.WebSocketTimeoutException) as exc:
                raise KiwoomError("키움 응답 시간이 초과되었습니다.") from exc
            if message.get("trnm") == "PING":
                ws.send(json.dumps(message))
                continue
            if message.get("trnm") == expected:
                return message

    def saved_conditions(self) -> list[dict]:
        ws = self._open_condition_socket()
        try:
            ws.send(json.dumps({"trnm": "CNSRLST"}))
            response = self._receive(ws, "CNSRLST")
            if response.get("return_code") not in (0, "0"):
                raise KiwoomError(response.get("return_msg") or "키움 조건식을 불러오지 못했습니다.")
            result = []
            for row in response.get("data") or []:
                if isinstance(row, dict):
                    seq, name = row.get("seq"), row.get("name")
                elif isinstance(row, (list, tuple)) and len(row) >= 2:
                    seq, name = row[0], row[1]
                else:
                    continue
                result.append({"seq": str(seq), "name": str(name)})
            return result
        finally:
            ws.close()

    def search_saved_condition(self, seq: str) -> list[dict]:
        ws = self._open_condition_socket()
        try:
            # 공식 흐름상 목록 조회를 먼저 해야 한다.
            ws.send(json.dumps({"trnm": "CNSRLST"}))
            self._receive(ws, "CNSRLST")

            request = {
                "trnm": "CNSRREQ",
                "seq": str(seq),
                "search_type": "0",
                "stex_tp": "K",
            }
            results: list[dict] = []
            while True:
                ws.send(json.dumps(request))
                response = self._receive(ws, "CNSRREQ")
                if response.get("return_code") not in (0, "0"):
                    raise KiwoomError(response.get("return_msg") or "조건검색에 실패했습니다.")
                rows = response.get("data") or []
                results.extend(row for row in rows if isinstance(row, dict))
                if response.get("cont_yn") != "Y" or not response.get("next_key"):
                    break
                request["cont_yn"] = "Y"
                request["next_key"] = response["next_key"]
            return results
        finally:
            ws.close()


def normalize_condition_result(row: dict) -> dict:
    code = clean_code(row.get("9001") or row.get("jmcode") or row.get("stk_cd") or "")
    return {
        "code": code,
        "name": row.get("302") or row.get("stk_nm") or code,
        "price": _safe_number(row.get("10") or row.get("cur_prc"), absolute=True),
        "change_rate": _safe_number(row.get("12") or row.get("flu_rt")),
        "volume": _safe_number(row.get("13") or row.get("trde_qty"), absolute=True),
        "trading_value": _safe_number(row.get("trde_prica") or row.get("acc_trde_prica"), absolute=True) * 1_000_000,
        "market_cap": _safe_number(row.get("mac"), absolute=True) * 100_000_000,
    }
