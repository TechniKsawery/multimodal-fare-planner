"""Wspólna obsługa OPCJONALNYCH, nieoficjalnych źródeł cen (DB przez db-vendo-client, PKP IC).

Zasady (patrz fares/README.md, sekcja "Nieoficjalne źródła cen"):
- DOMYŚLNIE WYŁĄCZONE. Włącza je dopiero zmienna środowiskowa UNOFFICIAL_PRICES=1.
- Każde źródło ma limit zapytań na minutę (UNOFFICIAL_PRICES_PER_MINUTE, domyślnie 20) i cache
  na dysku (UNOFFICIAL_PRICES_TTL_MIN, domyślnie 360 min), żeby nie obciążać cudzych serwerów.
- Gdy źródło nie odpowie, przekroczono limit albo wyłączono — wołający wraca do obecnych danych.
- Wynik zawsze jest etykietowany jako "szacunek" z breakdown["zrodlo"] wskazującym nieoficjalne źródło.
"""

import json
import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_calls: dict[str, list[float]] = {}


def enabled(source: str) -> bool:
    """Czy nieoficjalne źródło `source` ("db" / "pkp") jest włączone przełącznikiem."""
    if os.environ.get("UNOFFICIAL_PRICES", "").strip().lower() not in ("1", "true", "yes"):
        return False
    allowed = os.environ.get("UNOFFICIAL_PRICES_SOURCES", "db,pkp")
    return source in {s.strip() for s in allowed.split(",")}


def allow_request(source: str) -> bool:
    """Limit zapytań na minutę (okno przesuwne). False = przekroczono, użyj fallbacku."""
    limit = int(os.environ.get("UNOFFICIAL_PRICES_PER_MINUTE", "20"))
    now = time.monotonic()
    with _lock:
        recent = [t for t in _calls.get(source, []) if now - t < 60]
        if len(recent) >= limit:
            _calls[source] = recent
            return False
        recent.append(now)
        _calls[source] = recent
        return True


def _cache_file(source: str) -> Path:
    base = Path(os.environ.get("UNOFFICIAL_PRICES_CACHE_DIR", ".cache/unofficial_prices"))
    return base / f"{source}.json"


def cache_get(source: str, key: str):
    ttl = float(os.environ.get("UNOFFICIAL_PRICES_TTL_MIN", "360")) * 60
    try:
        entry = json.loads(_cache_file(source).read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return None
    if entry and time.time() - entry["ts"] < ttl:
        return entry["value"]
    return None


def cache_set(source: str, key: str, value) -> None:
    path = _cache_file(source)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[key] = {"ts": time.time(), "value": value}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # cache jest tylko optymalizacją
