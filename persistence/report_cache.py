import json
import os
from typing import Any

from config import settings

_CACHE_FILE = os.path.join(settings.data_dir, "prev_report_cache.json")
_MAX_BYTES   = 480_000   # mirrors GAS DocumentProperties limit


def read_cache() -> dict[str, Any]:
    """Return cache dict. Returns {} on missing file or JSON error — never raises."""
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_cache(cache: dict[str, Any]) -> bool:
    """Write cache to disk. Skips write if serialized size exceeds 480 KB.

    Returns True if written, False if skipped.
    """
    try:
        serialized = json.dumps(cache, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > _MAX_BYTES:
            return False
        os.makedirs(settings.data_dir, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(serialized)
        return True
    except Exception:
        return False
