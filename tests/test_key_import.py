import os

import pytest

from key_import import KeyImportError, find_downloaded_keys


def test_finds_matching_key_files(tmp_path):
    (tmp_path / "12345678_appkey.txt").write_text("app-key-value", encoding="utf-8")
    (tmp_path / "12345678_appsecret.txt").write_text("app-secret-value", encoding="utf-8")

    result = find_downloaded_keys(tmp_path)

    assert result.app_key == "app-key-value"
    assert result.app_secret == "app-secret-value"
    assert result.account_hint == "끝 5678"


def test_uses_latest_duplicate_download(tmp_path):
    original = tmp_path / "12345678_appkey.txt"
    duplicate = tmp_path / "12345678_appkey (1).txt"
    original.write_text("old-key", encoding="utf-8")
    duplicate.write_text("new-key", encoding="utf-8")
    (tmp_path / "12345678_appsecret.txt").write_text("secret", encoding="utf-8")
    os.utime(duplicate, (original.stat().st_mtime + 10, original.stat().st_mtime + 10))

    result = find_downloaded_keys(tmp_path)

    assert result.app_key == "new-key"


def test_explains_when_pair_is_missing(tmp_path):
    (tmp_path / "12345678_appkey.txt").write_text("key", encoding="utf-8")

    with pytest.raises(KeyImportError, match="두 파일"):
        find_downloaded_keys(tmp_path)
