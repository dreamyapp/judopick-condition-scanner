import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server

import app as app_module
import storage


playwright = pytest.importorskip("playwright.sync_api")


def test_browser_shows_results_empty_state_and_retry(tmp_path, monkeypatch):
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.exists():
        chrome_path = shutil.which("google-chrome") or shutil.which("chrome")
        if not chrome_path:
            pytest.skip("브라우저 테스트용 Chrome이 없습니다")
        chrome = Path(chrome_path)

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "conditions.db")
    monkeypatch.setattr(app_module, "LAST_RESULTS_FILE", tmp_path / "last_search.json")
    monkeypatch.setattr(app_module, "get_credentials", lambda: SimpleNamespace(configured=True, is_mock=False, source="personal"))
    storage.initialize()
    with app_module._jobs_lock:
        app_module._jobs.clear()
    condition = storage.save_condition({
        "name": "화면 검색", "mode": "signal", "raw_text": "C>C(1)",
        "timeframe": "5", "markets": ["KOSPI"], "exclusions": [], "rules": [],
    })
    rows = [{"code": f"{number:06d}", "name": f"종목 {number}",
             "price": 1000 + number, "volume": number, "found_at": "12:00:00",
             "bar_time": "20260923120000"} for number in range(205)]
    monkeypatch.setattr(app_module, "scan_signal", lambda condition, progress: list(rows))

    server = make_server("127.0.0.1", 0, app_module.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as engine:
            browser = engine.chromium.launch(executable_path=str(chrome), headless=True)
            try:
                page = browser.new_page(viewport={"width": 1360, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                page.locator(f'.condition-item[data-id="{condition["id"]}"]').click()
                page.locator("#searchButton").click()
                page.locator("#resultsTitle").filter(has_text="205개 종목을 찾았습니다").wait_for()
                assert page.locator("#resultsBody tr").count() == 100
                page.locator("#moreResultsButton").click()
                page.wait_for_function('document.querySelectorAll("#resultsBody tr").length === 200')
                page.locator("#moreResultsButton").click()
                page.wait_for_function('document.querySelectorAll("#resultsBody tr").length === 205')

                page.reload()
                page.locator("#resultsTitle").filter(has_text="205개 종목을 찾았습니다").wait_for()
                assert page.locator("#resultsBody tr").count() == 100

                rows.clear()
                page.locator("#searchAgainButton").click()
                page.locator("#resultsTitle").filter(has_text="0개 종목을 찾았습니다").wait_for()
                assert page.locator("#resultsEmpty").is_visible()
                assert not page.locator("#resultsTableWrap").is_visible()

                rows.append({"code": "000001", "name": "복구 종목", "price": 1000,
                             "volume": 100, "found_at": "12:00:00", "bar_time": "20260923120000"})
                first_page_error = {"pending": True}

                def fail_once(route):
                    if first_page_error["pending"]:
                        first_page_error["pending"] = False
                        route.fulfill(status=500, content_type="application/json",
                                      body='{"ok":false,"message":"결과를 잠시 불러오지 못했습니다."}')
                    else:
                        route.continue_()

                page.route(lambda url: "/api/search/" in url and "/results?offset=0" in url, fail_once)
                page.locator("#searchAgainButton").click()
                page.locator("#resultsError").wait_for(state="visible")
                assert page.locator("#retryResultsButton").is_visible()
                page.locator("#retryResultsButton").click()
                page.locator("#resultsBody tr").get_by_text("복구 종목").wait_for()

                page.locator("#newConditionButton").click()
                assert page.get_by_text("하나씩 만들기").count() == 0
                assert page.locator(".rule-row").count() == 0
                assert page.locator(".exclusion-check:checked").count() == 0
                assert page.locator("#signalTimeframe").is_visible()
                page.locator("#conditionName").fill("수식과 필터")
                page.locator("#conditionText").fill("C>C(1)")
                page.locator("#signalTimeframe").select_option("5")
                page.locator("#addRuleButton").click()
                assert page.locator(".rule-field").input_value() == "market_cap"
                page.locator(".rule-value").fill("1000")
                with page.expect_response(lambda response: response.url.endswith("/api/conditions")
                                          and response.request.method == "POST"):
                    page.locator("#saveButton").click()
                page.locator(".rule-row").wait_for()
                saved = next(item for item in storage.list_conditions() if item["name"] == "수식과 필터")
                assert saved["rules"][0]["value"] == 100_000_000_000
                assert saved["timeframe"] == "5"
                page.locator(".remove-rule").click()
                with page.expect_response(lambda response: response.url.endswith(f"/api/conditions/{saved['id']}")
                                          and response.request.method == "PUT"):
                    page.locator("#saveButton").click()
                assert storage.get_condition(saved["id"])["rules"] == []
                assert not errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
