import time
from types import SimpleNamespace

import app as app_module
import storage


def _prepare(tmp_path, monkeypatch, fake_scan):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "conditions.db")
    monkeypatch.setattr(app_module, "LAST_RESULTS_FILE", tmp_path / "last_search.json")
    monkeypatch.setattr(app_module, "get_credentials", lambda: SimpleNamespace(configured=True))
    monkeypatch.setattr(app_module, "scan_signal", fake_scan)
    storage.initialize()
    with app_module._jobs_lock:
        app_module._jobs.clear()
    condition = storage.save_condition({
        "name": "검색 테스트", "mode": "signal", "raw_text": "C>C(1)",
        "timeframe": "5", "markets": ["KOSPI"], "exclusions": [], "rules": [],
    })
    return app_module.app.test_client(), condition


def _completed_job(client, condition_id):
    started = client.post("/api/search", json={"condition_id": condition_id})
    assert started.status_code == 200
    job_id = started.json["job_id"]
    for _ in range(100):
        job = client.get(f"/api/search/{job_id}").json["job"]
        if job["status"] != "running":
            return job_id, job
        time.sleep(0.01)
    raise AssertionError("검색 작업이 완료되지 않았습니다")


def test_completed_results_are_paged_and_survive_app_restart(tmp_path, monkeypatch):
    rows = [{"code": f"{number:06d}", "name": f"종목 {number}",
             "price": 1000 + number, "volume": number, "found_at": "12:00:00",
             "bar_time": "20260923120000"} for number in range(205)]

    def fake_scan(condition, progress):
        progress(99, "결과를 준비하고 있습니다.")
        return rows

    client, condition = _prepare(tmp_path, monkeypatch, fake_scan)
    job_id, job = _completed_job(client, condition["id"])
    assert job["status"] == "done"
    assert job["progress"] == 100
    assert job["result_count"] == 205
    assert "results" not in job

    for offset, expected_length in [(0, 100), (100, 100), (200, 5)]:
        page = client.get(f"/api/search/{job_id}/results?offset={offset}").json
        assert page["ok"] and page["total"] == 205
        assert len(page["results"]) == expected_length
        assert page["results"][0]["code"] == f"{offset:06d}"
        assert page["mode"] == "signal" and page["timeframe"] == "5"

    latest = client.get("/api/search/latest").json
    assert latest["available"] and latest["job_id"] == job_id
    assert latest["condition_id"] == condition["id"]
    with app_module._jobs_lock:
        app_module._jobs.clear()
    restored = client.get(f"/api/search/{job_id}/results?offset=200").json
    assert restored["total"] == 205 and len(restored["results"]) == 5


def test_zero_matches_return_visible_empty_result(tmp_path, monkeypatch):
    client, condition = _prepare(tmp_path, monkeypatch, lambda condition, progress: [])
    job_id, job = _completed_job(client, condition["id"])
    assert job["status"] == "done" and job["result_count"] == 0
    page = client.get(f"/api/search/{job_id}/results?offset=0").json
    assert page["ok"] and page["results"] == [] and page["total"] == 0
