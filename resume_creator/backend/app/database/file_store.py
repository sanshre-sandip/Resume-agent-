"""Small JSON file store used instead of a database for local runs."""
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import settings

_lock = threading.RLock()
_root = Path(os.getenv("DATA_DIR", str(Path(settings.generated_dir).parent / "data")))


def _path(collection: str) -> Path:
    return _root / f"{collection}.json"


def _read(collection: str) -> list[dict[str, Any]]:
    path = _path(collection)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(collection: str, rows: list[dict[str, Any]]) -> None:
    _root.mkdir(parents=True, exist_ok=True)
    path = _path(collection)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def list_records(collection: str) -> list[dict[str, Any]]:
    with _lock:
        return _read(collection)


def get_record(collection: str, key: str, value: Any) -> dict[str, Any] | None:
    with _lock:
        return next((row for row in _read(collection) if row.get(key) == value), None)


def save_record(collection: str, record: dict[str, Any], key: str = "id") -> dict[str, Any]:
    with _lock:
        rows = _read(collection)
        for index, row in enumerate(rows):
            if row.get(key) == record.get(key):
                rows[index] = record
                break
        else:
            rows.append(record)
        _write(collection, rows)
    return record


def now_iso() -> str:
    return datetime.utcnow().isoformat()
