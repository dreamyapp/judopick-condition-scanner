from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from paths import data_dir, env_candidates


SERVICE_NAME = "JudopickConditionScanner"
FALLBACK_FILE = data_dir() / "credentials.json"

for candidate in env_candidates():
    if candidate.is_file():
        load_dotenv(candidate, override=False)
        break


@dataclass(frozen=True)
class Credentials:
    app_key: str
    secret_key: str
    base_url: str
    source: str = "personal"

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.secret_key)

    @property
    def is_mock(self) -> bool:
        return "mockapi" in self.base_url


def _keyring_get(name: str) -> str:
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, name) or ""
    except Exception:
        return ""


def _keyring_set(name: str, value: str) -> bool:
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, name, value)
        return True
    except Exception:
        return False


def _fallback_read() -> dict:
    try:
        return json.loads(FALLBACK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fallback_write(data: dict) -> None:
    FALLBACK_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        FALLBACK_FILE.chmod(0o600)
    except OSError:
        pass


def get_credentials() -> Credentials:
    fallback = _fallback_read()
    app_key = _keyring_get("app_key") or os.getenv("KIWOOM_APP_KEY", "").strip() or fallback.get("app_key", "")
    secret_key = (
        _keyring_get("secret_key")
        or os.getenv("KIWOOM_SECRET_KEY", "").strip()
        or fallback.get("secret_key", "")
    )
    base_url = (
        _keyring_get("base_url")
        or os.getenv("KIWOOM_BASE_URL", "").strip()
        or fallback.get("base_url", "")
        or "https://api.kiwoom.com"
    )
    return Credentials(app_key, secret_key, base_url.rstrip("/"))


def save_credentials(app_key: str, secret_key: str, use_mock: bool) -> str:
    app_key = app_key.strip()
    secret_key = secret_key.strip()
    if not app_key or not secret_key:
        raise ValueError("App Key와 App Secret을 모두 입력해 주세요.")
    base_url = "https://mockapi.kiwoom.com" if use_mock else "https://api.kiwoom.com"

    values = {"app_key": app_key, "secret_key": secret_key, "base_url": base_url}
    stored_in_keyring = all(_keyring_set(key, value) for key, value in values.items())
    if stored_in_keyring:
        if FALLBACK_FILE.exists():
            try:
                FALLBACK_FILE.unlink()
            except OSError:
                pass
        return "운영체제 보안 저장소"

    _fallback_write(values)
    return "사용자 전용 설정 파일"
