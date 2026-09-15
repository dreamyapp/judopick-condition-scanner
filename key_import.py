from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


KEY_FILE_PATTERN = re.compile(r"^(?P<account>.+)_(?P<kind>appkey|appsecret)(?: \(\d+\))?$", re.IGNORECASE)


class KeyImportError(ValueError):
    pass


@dataclass(frozen=True)
class DownloadedKeys:
    app_key: str
    app_secret: str
    app_key_file: Path
    app_secret_file: Path
    account_hint: str


def downloads_dir() -> Path:
    override = os.getenv("JUDOPICK_DOWNLOADS_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            value_name = "{374DE290-123F-4565-9164-39C4925E467B}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
            return Path(os.path.expandvars(value))
        except (OSError, ImportError):
            pass

    return Path.home() / "Downloads"


def _read_key(path: Path) -> str:
    try:
        if path.stat().st_size > 50_000:
            raise KeyImportError("키 파일의 크기가 너무 큽니다.")
        raw = path.read_bytes()
    except OSError as exc:
        raise KeyImportError(f"{path.name} 파일을 읽지 못했습니다.") from exc

    text = ""
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="ignore")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if "=" in line:
            value = line.split("=", 1)[1].strip().strip("\"'")
            if value:
                return value
        if ":" in line:
            value = line.split(":", 1)[1].strip().strip("\"'")
            if value and " " not in value:
                return value

    if len(lines) == 1:
        return lines[0].strip("\"'")

    candidates = re.findall(r"[A-Za-z0-9_\-]{20,}", text)
    if candidates:
        return max(candidates, key=len)
    raise KeyImportError(f"{path.name} 파일에서 키 값을 찾지 못했습니다.")


def _account_hint(account: str) -> str:
    digits = "".join(character for character in account if character.isdigit())
    return f"끝 {digits[-4:]}" if len(digits) >= 4 else "확인됨"


def find_downloaded_keys(folder: Path | None = None) -> DownloadedKeys:
    folder = folder or downloads_dir()
    if not folder.is_dir():
        raise KeyImportError("다운로드 폴더를 찾지 못했습니다. 아래의 ‘키 파일 2개 직접 선택’을 눌러주세요.")

    pairs: dict[str, dict[str, Path]] = {}
    try:
        files = list(folder.iterdir())
    except OSError as exc:
        raise KeyImportError("다운로드 폴더를 열 수 없습니다. 아래의 ‘키 파일 2개 직접 선택’을 눌러주세요.") from exc

    for path in files:
        if not path.is_file() or path.suffix.lower() != ".txt":
            continue
        match = KEY_FILE_PATTERN.match(path.stem)
        if not match:
            continue
        account = match.group("account")
        kind = match.group("kind").lower()
        current = pairs.setdefault(account, {}).get(kind)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            pairs[account][kind] = path

    complete = [
        (account, files_by_kind)
        for account, files_by_kind in pairs.items()
        if "appkey" in files_by_kind and "appsecret" in files_by_kind
    ]
    if not complete:
        raise KeyImportError(
            "다운로드 폴더에서 App Key와 App Secret 파일을 찾지 못했습니다. "
            "키움에서 두 파일을 모두 내려받았는지 확인해 주세요."
        )

    account, selected = max(
        complete,
        key=lambda item: max(item[1]["appkey"].stat().st_mtime, item[1]["appsecret"].stat().st_mtime),
    )
    return DownloadedKeys(
        app_key=_read_key(selected["appkey"]),
        app_secret=_read_key(selected["appsecret"]),
        app_key_file=selected["appkey"],
        app_secret_file=selected["appsecret"],
        account_hint=_account_hint(account),
    )


def open_downloads_folder() -> None:
    folder = downloads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    elif os.name == "nt":
        os.startfile(str(folder))
    else:
        subprocess.Popen(["xdg-open", str(folder)])
