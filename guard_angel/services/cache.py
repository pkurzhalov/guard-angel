from __future__ import annotations
from pathlib import Path
import json, threading

_CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "last_rows.json"
_LOCK = threading.Lock()

def load_cache() -> dict:
    try:
        with _LOCK:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if _CACHE_PATH.exists():
                return json.loads(_CACHE_PATH.read_text())
    except Exception:
        pass
    return {}

def save_cache(data: dict) -> None:
    with _LOCK:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(data, indent=2))
