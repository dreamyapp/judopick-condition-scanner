from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "Judopick Condition Scanner"


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def data_dir() -> Path:
    override = os.getenv("JUDOPICK_CONDITION_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    elif os.name == "nt":
        path = Path(os.getenv("APPDATA", Path.home())) / APP_DIR_NAME
    else:
        path = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_candidates() -> list[Path]:
    candidates = [resource_root() / ".env"]
    # 개발 중에는 주도픽 루트의 키를 재사용한다.
    if not getattr(sys, "frozen", False):
        candidates.append(resource_root().parent / ".env")
    return candidates
