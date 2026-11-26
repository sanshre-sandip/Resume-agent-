"""Small JSON file store used instead of a database for local runs."""
import json
import os
import fcntl
import tempfile
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import settings

_lock = threading.RLock()
_resume_locks_guard = threading.Lock()
_resume_locks: dict[str, threading.RLock] = {}
_root = Path(settings.data_dir).expanduser()


def _path(collection: str) -> Path:
    return _root / f"{collection}.json"


@contextmanager
def lock_resume(resume_id: str):
    """Serialize mutations for one resume across request threads in this app process."""
    with _resume_locks_guard:
        lock = _resume_locks.setdefault(resume_id, threading.RLock())
    with lock:
        yield


@contextmanager
def _process_lock():
    _root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(_root, 0o700)
    except OSError:
        pass
    with (_root / ".store.lock").open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read(collection: str) -> list[dict[str, Any]]:
    path = _path(collection)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise RuntimeError(f"Data file {path.name} has an invalid structure.")
        return data
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Data file {path.name} is corrupt; it was not overwritten.") from exc


def _write(collection: str, rows: list[dict[str, Any]]) -> None:
    _root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _path(collection)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{collection}-", suffix=".tmp", dir=_root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(rows, temporary, indent=2, ensure_ascii=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def list_records(collection: str) -> list[dict[str, Any]]:
    with _lock, _process_lock():
        return _read(collection)


def get_record(collection: str, key: str, value: Any) -> dict[str, Any] | None:
    with _lock, _process_lock():
        return next((row for row in _read(collection) if row.get(key) == value), None)


def save_record(collection: str, record: dict[str, Any], key: str = "id") -> dict[str, Any]:
    with _lock, _process_lock():
        rows = _read(collection)
        for index, row in enumerate(rows):
            if row.get(key) == record.get(key):
                rows[index] = record
                break
        else:
            rows.append(record)
        _write(collection, rows)
    return record


def delete_records(collection: str, predicate) -> int:
    with _lock, _process_lock():
        rows = _read(collection)
        kept = [row for row in rows if not predicate(row)]
        removed = len(rows) - len(kept)
        if removed:
            _write(collection, kept)
        return removed


def create_record(collection: str, record: dict[str, Any], unique_fields: tuple[str, ...] = ("id",)) -> bool:
    with _lock, _process_lock():
        rows = _read(collection)
        if any(all(row.get(field) == record.get(field) for field in unique_fields) for row in rows):
            return False
        rows.append(record)
        _write(collection, rows)
        return True


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
