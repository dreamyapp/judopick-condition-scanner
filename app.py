from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Flask, jsonify, render_template, request

import storage
from condition_parser import FIELD_LABELS, OPERATOR_LABELS, parse_condition_text, validate_rule
from credentials import Credentials, get_credentials, save_credentials
from key_import import KeyImportError, find_downloaded_keys, open_downloads_folder
from kiwoom_client import KiwoomClient, KiwoomError
from paths import resource_path
from scanner import scan_custom, scan_kiwoom, scan_signal
from signal_formula import TIMEFRAMES, looks_like_signal_formula, parse_signal_formula, validate_signal_formula


APP_VERSION = "0.4.0"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(resource_path("templates")),
    static_folder=str(resource_path("static")),
)
storage.initialize()

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="condition-search")
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _ok(**payload):
    return jsonify({"ok": True, **payload})


def _error(message: str, status: int = 400):
    return jsonify({"ok": False, "message": message}), status


def _test_and_save_credentials(app_key: str, secret_key: str, use_mock: bool) -> tuple[dict, str]:
    app_key = app_key.strip()
    secret_key = secret_key.strip()
    if not app_key or not secret_key:
        raise ValueError("App Key와 App Secret을 모두 입력해 주세요.")
    base_url = "https://mockapi.kiwoom.com" if use_mock else "https://api.kiwoom.com"
    result = KiwoomClient(Credentials(app_key, secret_key, base_url)).test_connection()
    location = save_credentials(app_key, secret_key, use_mock)
    return result, location


def _condition_summary(condition: dict) -> str:
    if condition.get("mode") == "kiwoom":
        return "영웅문에 저장된 조건식"
    if condition.get("mode") == "signal":
        timeframe = condition.get("timeframe") or "?"
        return f"{'일봉' if timeframe == 'D' else timeframe + '분봉'} · 직접 만든 수식"
    labels = [rule.get("label", "") for rule in condition.get("rules", []) if rule.get("label")]
    return " · ".join(labels) if labels else "조건을 입력해 주세요"


def _condition_export_text(condition: dict) -> str:
    if condition.get("mode") == "kiwoom":
        return f"조건식명: {condition['name']}\n종류: 영웅문 저장 조건식"
    if condition.get("mode") == "signal":
        return condition.get("raw_text", "")
    market_names = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}
    lines = [f"조건식명: {condition['name']}"]
    lines.append("시장: " + ", ".join(market_names.get(item, item) for item in condition.get("markets", [])))
    for rule in condition.get("rules", []):
        lines.append(rule.get("label", ""))
    if condition.get("exclusions"):
        lines.append("제외: " + ", ".join(condition["exclusions"]))
    return "\n".join(line for line in lines if line)


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.get("/api/bootstrap")
def bootstrap():
    credentials = get_credentials()
    conditions = storage.list_conditions()
    for condition in conditions:
        condition["summary"] = _condition_summary(condition)
    return _ok(
        version=APP_VERSION,
        credentials={
            "configured": credentials.configured,
            "mode": "mock" if credentials.is_mock else "real",
            "source": credentials.source,
        },
        conditions=conditions,
        fields=[{"value": key, "label": label} for key, label in FIELD_LABELS.items()],
        operators=[{"value": key, "label": label} for key, label in OPERATOR_LABELS.items()],
    )


@app.post("/api/settings/credentials")
def settings_credentials():
    payload = request.get_json(silent=True) or {}
    try:
        result, location = _test_and_save_credentials(
            str(payload.get("app_key", "")),
            str(payload.get("secret_key", "")),
            bool(payload.get("use_mock", False)),
        )
        return _ok(message=f"키움 {result['mode']} 서버 연결에 성공했습니다. {location}에 저장했습니다.")
    except (ValueError, OSError, KiwoomError) as exc:
        return _error(str(exc))


@app.post("/api/settings/import-downloaded")
def settings_import_downloaded():
    payload = request.get_json(silent=True) or {}
    try:
        downloaded = find_downloaded_keys()
        result, _location = _test_and_save_credentials(
            downloaded.app_key,
            downloaded.app_secret,
            bool(payload.get("use_mock", False)),
        )
        return _ok(
            message=f"키 파일을 찾아 키움 {result['mode']} 서버에 연결했습니다.",
            account_hint=downloaded.account_hint,
            files=[downloaded.app_key_file.name, downloaded.app_secret_file.name],
        )
    except (KeyImportError, ValueError, OSError, KiwoomError) as exc:
        return _error(str(exc))


@app.post("/api/settings/open-downloads")
def settings_open_downloads():
    try:
        open_downloads_folder()
        return _ok(message="다운로드 폴더를 열었습니다.")
    except OSError:
        return _error("다운로드 폴더를 열지 못했습니다.")


@app.post("/api/settings/test")
def settings_test():
    try:
        result = KiwoomClient().test_connection()
        return _ok(message=f"키움 {result['mode']} 서버에 연결되었습니다.")
    except KiwoomError as exc:
        return _error(str(exc))


@app.post("/api/parse")
def parse_text():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return _error("조건식을 붙여넣어 주세요.")
    if looks_like_signal_formula(text):
        try:
            return _ok(parsed=parse_signal_formula(text))
        except ValueError as exc:
            return _error(str(exc))
    return _ok(parsed={"mode": "custom", **parse_condition_text(text).as_dict()})


@app.post("/api/conditions")
def create_condition():
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("mode") == "signal":
            validate_signal_formula(str(payload.get("raw_text", "")))
            if str(payload.get("timeframe", "")) not in TIMEFRAMES:
                raise ValueError("검색할 차트 봉을 선택해 주세요.")
            payload["rules"] = []
        elif payload.get("mode", "custom") == "custom":
            if looks_like_signal_formula(str(payload.get("raw_text", ""))):
                raise ValueError("수식은 '조건식 확인'을 눌러 확인해 주세요.")
            payload["rules"] = [validate_rule(rule) for rule in payload.get("rules", [])]
        condition = storage.save_condition(payload)
        condition["summary"] = _condition_summary(condition)
        return _ok(condition=condition)
    except ValueError as exc:
        return _error(str(exc))


@app.put("/api/conditions/<condition_id>")
def update_condition(condition_id: str):
    if not storage.get_condition(condition_id):
        return _error("조건식을 찾지 못했습니다.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("mode", "custom") == "custom":
            if looks_like_signal_formula(str(payload.get("raw_text", ""))):
                raise ValueError("수식은 '조건식 확인'을 눌러 확인해 주세요.")
            payload["rules"] = [validate_rule(rule) for rule in payload.get("rules", [])]
        elif payload.get("mode") == "signal":
            validate_signal_formula(str(payload.get("raw_text", "")))
            if str(payload.get("timeframe", "")) not in TIMEFRAMES:
                raise ValueError("검색할 차트 봉을 선택해 주세요.")
            payload["rules"] = []
        condition = storage.save_condition(payload, condition_id)
        condition["summary"] = _condition_summary(condition)
        return _ok(condition=condition)
    except ValueError as exc:
        return _error(str(exc))


@app.delete("/api/conditions/<condition_id>")
def delete_condition(condition_id: str):
    if not storage.delete_condition(condition_id):
        return _error("조건식을 찾지 못했습니다.", 404)
    return _ok(message="조건식을 삭제했습니다.")


@app.get("/api/conditions/<condition_id>/export")
def export_condition(condition_id: str):
    condition = storage.get_condition(condition_id)
    if not condition:
        return _error("조건식을 찾지 못했습니다.", 404)
    return _ok(text=_condition_export_text(condition))


@app.post("/api/conditions/import-kiwoom")
def import_kiwoom():
    try:
        items = KiwoomClient().saved_conditions()
        imported = storage.import_kiwoom_conditions(items)
        return _ok(
            message=f"영웅문 조건식 {len(imported)}개를 불러왔습니다.",
            count=len(imported),
        )
    except KiwoomError as exc:
        return _error(str(exc))


def _set_job(job_id: str, **changes) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes)


def _run_search(job_id: str, condition: dict) -> None:
    try:
        def progress(percent: int, message: str) -> None:
            _set_job(job_id, progress=percent, message=message)

        if condition.get("mode") == "kiwoom":
            progress(20, "키움에서 조건에 맞는 종목을 찾고 있습니다.")
            results = scan_kiwoom(condition)
        elif condition.get("mode") == "signal":
            results = scan_signal(condition, progress=progress)
        else:
            results = scan_custom(condition, progress=progress)
        _set_job(
            job_id,
            status="done",
            progress=100,
            message=f"{len(results):,}개 종목을 찾았습니다.",
            results=results,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except (KiwoomError, ValueError) as exc:
        _set_job(job_id, status="error", message=str(exc), progress=0)
    except Exception:
        logger.exception("조건검색 중 예상하지 못한 오류")
        _set_job(
            job_id,
            status="error",
            message="검색 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.",
            progress=0,
        )


@app.post("/api/search")
def start_search():
    payload = request.get_json(silent=True) or {}
    condition_id = str(payload.get("condition_id", ""))
    condition = storage.get_condition(condition_id)
    if not condition:
        return _error("먼저 검색할 조건식을 선택해 주세요.")
    if not get_credentials().configured:
        return _error("먼저 키움 연결 정보를 설정해 주세요.")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "condition_id": condition_id,
            "status": "running",
            "progress": 1,
            "message": "검색을 시작합니다.",
            "results": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    _executor.submit(_run_search, job_id, condition)
    return _ok(job_id=job_id)


@app.get("/api/search/<job_id>")
def search_status(job_id: str):
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return _error("검색 기록을 찾지 못했습니다.", 404)
    return _ok(job=job)


@app.get("/api/health")
def health():
    return _ok(version=APP_VERSION)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5217, debug=False)
