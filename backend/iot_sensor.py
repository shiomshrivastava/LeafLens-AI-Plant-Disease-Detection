"""Small local-only DHT11 receiver for LeafLens.

The ESP32 sends readings over the home LAN to FastAPI. This does not need
Supabase or external internet. Values are intentionally held in RAM only;
the dashboard shows OFFLINE if no fresh readings arrive.
"""
from __future__ import annotations

import math
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix='/api/iot', tags=['IoT Sensor'])
_DEVICE_KEY = os.getenv('LEAFLENS_IOT_KEY', '').strip()
_STALE_AFTER_SECONDS = 20.0
_lock = threading.Lock()
_reading: dict | None = None
_arrived_monotonic: float | None = None


class DHT11Reading(BaseModel):
    temperature_c: float = Field(ge=-10.0, le=60.0)
    humidity_percent: float = Field(ge=0.0, le=100.0)


def is_configured() -> bool:
    # Enforce a nontrivial device token; this is different from Supabase keys.
    return len(_DEVICE_KEY) >= 20 and 'REPLACE' not in _DEVICE_KEY.upper()


@router.post('/readings')
def accept_reading(payload: DHT11Reading, x_device_key: str | None = Header(default=None, alias='X-Device-Key')):
    if not is_configured():
        raise HTTPException(status_code=503, detail='IoT device key is not configured in backend/.env.')
    if not x_device_key or not secrets.compare_digest(x_device_key, _DEVICE_KEY):
        raise HTTPException(status_code=401, detail='Invalid ESP32 device key.')
    if not math.isfinite(payload.temperature_c) or not math.isfinite(payload.humidity_percent):
        raise HTTPException(status_code=422, detail='Invalid sensor values.')
    now = datetime.now(timezone.utc).isoformat()
    global _reading, _arrived_monotonic
    with _lock:
        _reading = {
            'temperature_c': round(payload.temperature_c, 1),
            'humidity_percent': round(payload.humidity_percent, 1),
            'updated_at': now,
        }
        _arrived_monotonic = time.monotonic()
    return {'received': True, 'updated_at': now}


@router.get('/current')
def current_reading():
    with _lock:
        latest = _reading.copy() if _reading is not None else None
        last_arrival = _arrived_monotonic

    age = max(0.0, time.monotonic() - last_arrival) if last_arrival is not None else None
    online = bool(latest and age is not None and age <= _STALE_AFTER_SECONDS)
    return {
        'configured': is_configured(),
        'online': online,
        'source': 'ESP32 + DHT11',
        'temperature_c': latest['temperature_c'] if online else None,
        'humidity_percent': latest['humidity_percent'] if online else None,
        'updated_at': latest['updated_at'] if latest else None,
        'age_seconds': round(age, 1) if age is not None else None,
        'stale_after_seconds': int(_STALE_AFTER_SECONDS),
    }
