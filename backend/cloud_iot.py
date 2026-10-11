"""Cloud-only IoT last-reading viewer. ESP32 uploads to Supabase Edge Function.
No local model, Wi-Fi/LAN discovery, or device token required on Render.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

LOG = logging.getLogger('leaflens.cloud_iot')
router = APIRouter(prefix='/api/iot', tags=['IoT Sensor'])
STALE_SECONDS = 20.0


def is_configured() -> bool:
    return (os.getenv('SUPABASE_URL', '').startswith('https://')
            and bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()))


def _headers() -> dict[str, str]:
    secret = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    result = {'apikey': secret}
    if not secret.startswith('sb_secret_'):
        result['Authorization'] = 'Bearer ' + secret
    return result


@router.get('/current')
async def current_reading():
    response = {
        'configured': is_configured(),
        'online': False,
        'source': 'ESP32 + DHT11',
        'temperature_c': None,
        'humidity_percent': None,
        'updated_at': None,
        'age_seconds': None,
        'stale_after_seconds': int(STALE_SECONDS),
    }
    if not is_configured():
        return response
    try:
        url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/leaflens_iot_latest'
        async with httpx.AsyncClient(timeout=8) as client:
            reply = await client.get(url, headers=_headers(), params={
                'device_id': 'eq.leaflens-demo',
                'select': 'temperature_c,humidity_percent,updated_at',
                'limit': 1,
            })
        reply.raise_for_status()
        rows = reply.json()
        if not isinstance(rows, list) or not rows:
            return response
        row = rows[0]
        updated_at = str(row['updated_at'])
        timestamp = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        age = max(0, (datetime.now(timezone.utc) - timestamp).total_seconds())
        response.update(updated_at=updated_at, age_seconds=round(age, 1), online=age <= STALE_SECONDS)
        if response['online']:
            response.update(temperature_c=row['temperature_c'], humidity_percent=row['humidity_percent'])
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError) as exc:
        LOG.warning('Cloud IoT reading unavailable (%s)', type(exc).__name__)
    return response


@router.post('/readings')
async def local_upload_not_supported():
    # Cloud ESP32 uses device-authenticated Supabase Edge Function instead.
    raise HTTPException(status_code=503, detail='Send IoT readings to the configured Supabase Edge Function.')
