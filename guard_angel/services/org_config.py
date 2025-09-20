from __future__ import annotations
from pathlib import Path
import json, threading

_BASE = Path(__file__).resolve().parents[2] / ".cache"
_PATH = _BASE / "org_config.json"
_LOCK = threading.Lock()

_DEFAULT = {
  "org": {
    "name": "",
    "street": "",
    "city_state_zip": "",
    "bank_name": "",
    "routing_number": "",
    "account_number": "",
    "address": ""
  },
  "drivers": {}
}

def _ensure_compat(cfg: dict) -> dict:
    cfg = json.loads(json.dumps(cfg))
    org = cfg.setdefault("org", {})
    for k, v in _DEFAULT["org"].items():
        org.setdefault(k, v)
    if not org.get("street") and not org.get("city_state_zip") and org.get("address"):
        parts = [p.strip() for p in org["address"].split(",", 1)]
        if parts:
            org["street"] = parts[0]
            if len(parts) > 1:
                org["city_state_zip"] = parts[1]
    street = org.get("street", "").strip()
    csz = org.get("city_state_zip", "").strip()
    org["address"] = f"{street}, {csz}".strip(", ")
    return cfg

def load() -> dict:
    with _LOCK:
        _BASE.mkdir(parents=True, exist_ok=True)
        if _PATH.exists():
            try:
                return _ensure_compat(json.loads(_PATH.read_text()))
            except Exception:
                pass
        return _ensure_compat(_DEFAULT)

def save(cfg: dict) -> None:
    with _LOCK:
        _BASE.mkdir(parents=True, exist_ok=True)
        cfg = _ensure_compat(cfg)
        _PATH.write_text(json.dumps(cfg, indent=2))

def get_org() -> dict:
    return load().get("org", {})

def get_driver(driver_tab: str) -> dict:
    return load().get("drivers", {}).get(driver_tab, {})

def set_org(**kwargs) -> None:
    cfg = load()
    cfg["org"].update({k: v for k, v in kwargs.items() if v is not None})
    save(cfg)

def set_driver(driver_tab: str, **kwargs) -> None:
    cfg = load()
    cfg.setdefault("drivers", {}).setdefault(driver_tab, {}).update(
        {k: v for k, v in kwargs.items() if v is not None}
    )
    save(cfg)
