"""Authenticated LeafLens history in Supabase PostgREST + private Storage.

Only the local FastAPI process holds a service-role/secret key. The browser never
sees it. Every operation first verifies the caller's Supabase access token and
filters analyses by that caller's verified user ID.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from PIL import Image

LOG = logging.getLogger('leaflens.history')
URL = os.getenv('SUPABASE_URL', '').rstrip('/')
PUBLIC_KEY = os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip()
SECRET_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
BUCKET = 'analysis-images'
MAX_RECORDS = 10
MAX_NAMES = 140
LOCKS: dict[str, asyncio.Lock] = {}
LOCK_GUARD = threading.Lock()


def configured() -> bool:
    return bool(URL.startswith('https://') and PUBLIC_KEY and SECRET_KEY)


def _lock(uid: str) -> asyncio.Lock:
    with LOCK_GUARD:
        if uid not in LOCKS:
            LOCKS[uid] = asyncio.Lock()
        return LOCKS[uid]


def _admin_headers(extra: dict | None = None) -> dict[str, str]:
    # Legacy JWT service_role keys use Bearer; modern sb_secret_* keys use apikey
    # and MUST NOT be sent as a JWT bearer token.
    headers = {'apikey': SECRET_KEY}
    if not SECRET_KEY.startswith('sb_secret_'):
        headers['Authorization'] = f'Bearer {SECRET_KEY}'
    if extra:
        headers.update(extra)
    return headers


def _check(response: httpx.Response, context: str):
    if response.status_code >= 400:
        LOG.error('Supabase %s failed: HTTP %s %s', context, response.status_code, response.text[:400])
        raise RuntimeError(f'{context} failed (Supabase HTTP {response.status_code}). See backend log.')
    return response


async def verified_user(authorization: str | None) -> str:
    """Never trust a user_id from a frontend request body or URL."""
    if not configured():
        raise HTTPException(status_code=503, detail='History service not configured: check backend/.env and restart.')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Sign in to use your private analysis history.')
    token = authorization[7:].strip()
    if not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail='Invalid session. Please sign in again.')
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f'{URL}/auth/v1/user',
                headers={'apikey': PUBLIC_KEY, 'Authorization': f'Bearer {token}'},
            )
        if res.status_code != 200:
            raise HTTPException(status_code=401, detail='Your session expired. Please sign in again.')
        uid = res.json().get('id')
        return str(uuid.UUID(uid))
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        LOG.warning('Auth verification failed: %s', type(exc).__name__)
        raise HTTPException(status_code=401, detail='Unable to verify your session. Please sign in again.') from exc


async def _query(client: httpx.AsyncClient, path: str, method: str = 'GET', *, params=None, payload=None, extra_headers=None):
    res = await client.request(method, f'{URL}{path}', params=params, json=payload,
                               headers=_admin_headers(extra_headers), timeout=30)
    return _check(res, f'{method} {path.split("?")[0]}')


async def _rows(client: httpx.AsyncClient, uid: str, *, limit: int | None = None):
    params = {
        'user_id': f'eq.{uid}', 'select': '*',
        'order': 'created_at.desc,id.desc',
    }
    if limit is not None:
        params['limit'] = str(limit)
    response = await _query(client, '/rest/v1/analyses', params=params)
    return response.json()


async def _signed_url(client: httpx.AsyncClient, path: str | None) -> str | None:
    if not path:
        return None
    response = await _query(client,
        f'/storage/v1/object/sign/{BUCKET}/{quote(path, safe="/")}', method='POST',
        payload={'expiresIn': 3600})
    url = response.json().get('signedURL') or response.json().get('signedUrl')
    if not url:
        raise RuntimeError('Supabase did not return an image signed URL.')
    if url.startswith('https://'):
        return url
    if url.startswith('/storage/v1/'):
        return URL + url
    if url.startswith('/object/'):
        return URL + '/storage/v1' + url
    raise RuntimeError('Unexpected private image URL format from Supabase.')


async def _with_urls(client: httpx.AsyncClient, row: dict):
    # Return just the user's own signed images. Signed URLs are short-lived.
    try:
        return {
            'id': row['id'], 'image_name': row['image_name'],
            'created_at': row['created_at'],
            'report': {
                **row.get('result_data', {}),
                'overlay_image': await _signed_url(client, row.get('overlay_path')),
                'mask_image': await _signed_url(client, row.get('mask_path')),
            },
            'image_url': await _signed_url(client, row.get('image_path')),
        }
    except Exception:
        LOG.exception('Could not generate signed URLs for analysis %s', row.get('id'))
        raise


async def read_history(uid: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        rows = await _rows(client, uid, limit=MAX_RECORDS)
        limiter = asyncio.Semaphore(6)
        async def resolved(row: dict):
            async with limiter:
                return await _with_urls(client, row)
        return await asyncio.gather(*(resolved(row) for row in rows))


def _webp(original: Image.Image) -> bytes:
    copy = original.copy()
    copy.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    blob = io.BytesIO()
    copy.save(blob, 'WEBP', quality=84, method=4)
    return blob.getvalue()


def _decode_inline_image(value: str | None, *, mask: bool) -> tuple[bytes, str, str] | None:
    if not value:
        return None
    prefix, sep, encoded = value.partition(',')
    if not sep or not prefix.startswith('data:image/png;base64'):
        raise RuntimeError('Unexpected inference image format.')
    with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as im:
        if mask:
            buf = io.BytesIO()
            im.convert('L').save(buf, 'PNG', optimize=True)
            return buf.getvalue(), 'image/png', 'mask.png'
        return _webp(im.convert('RGB')), 'image/webp', 'overlay.webp'


async def _upload(client: httpx.AsyncClient, path: str, content: bytes, mime: str):
    response = await client.post(
        f'{URL}/storage/v1/object/{BUCKET}/{quote(path, safe="/")}',
        content=content,
        headers=_admin_headers({'Content-Type': mime, 'x-upsert': 'false'}),
        timeout=65,
    )
    _check(response, 'private image upload')


async def _remove_objects(client: httpx.AsyncClient, paths: list[str]):
    if not paths:
        return
    # Supabase Storage bulk remove endpoint, same API used by storage.remove().
    response = await _query(client, f'/storage/v1/object/{BUCKET}', method='DELETE',
                            payload={'prefixes': paths})
    value = response.json()
    if isinstance(value, dict) and value.get('error'):
        raise RuntimeError(f'Supabase storage deletion failed: {value["error"]}')


async def _delete_row(client: httpx.AsyncClient, uid: str, row: dict):
    paths = [row[k] for k in ('image_path', 'overlay_path', 'mask_path') if row.get(k)]
    # Remove objects before DB row, so failures do not silently orphan files.
    await _remove_objects(client, paths)
    await _query(client, '/rest/v1/analyses', method='DELETE',
                 params={'id': f'eq.{row["id"]}', 'user_id': f'eq.{uid}'})


async def _trim(client: httpx.AsyncClient, uid: str) -> int:
    rows = await _rows(client, uid)
    to_delete = rows[MAX_RECORDS:]
    for row in to_delete:
        await _delete_row(client, uid, row)
    return len(to_delete)


async def save_analysis(uid: str, file_name: str, original: Image.Image, report: dict) -> tuple[str, int, str | None]:
    """Persist analysis and uploaded imagery, keeping at most 10 per user.

    Caller gets visible warning on any failure; never claims that unsaved data
    is persistent. Serializes concurrent saves for the same user in one process.
    """
    async with _lock(uid):
        report_id = str(uuid.uuid4())
        prefix = f'{uid}/{report_id}'
        original_path = f'{prefix}/original.webp'
        overlay = _decode_inline_image(report.get('overlay_image'), mask=False)
        mask = _decode_inline_image(report.get('mask_image'), mask=True)
        objects = [(original_path, _webp(original), 'image/webp')]
        if overlay:
            objects.append((f'{prefix}/{overlay[2]}', overlay[0], overlay[1]))
        if mask:
            objects.append((f'{prefix}/{mask[2]}', mask[0], mask[1]))
        data = {k: v for k, v in report.items() if k not in ('overlay_image', 'mask_image')}
        record = {
            'id': report_id, 'user_id': uid,
            'image_name': Path(file_name).name[:MAX_NAMES] or 'leaf-image',
            'image_path': original_path,
            'overlay_path': objects[1][0] if overlay else None,
            'mask_path': objects[-1][0] if mask else None,
            'crop': (report.get('model0c') or {}).get('predicted_crop'),
            'health_status': (report.get('model1') or {}).get('status'),
            'disease': (report.get('model2') or {}).get('disease'),
            'disease_confidence': (report.get('model2') or {}).get('confidence'),
            'severity': (report.get('model3') or {}).get('severity'),
            'affected_percent': (report.get('model3') or {}).get('affected_percent'),
            'result_status': report['decision'],
            'result_data': data,
        }
        async with httpx.AsyncClient() as client:
            uploaded = []
            committed = False
            try:
                for path, raw, mime in objects:
                    await _upload(client, path, raw, mime)
                    uploaded.append(path)
                await _query(client, '/rest/v1/analyses', method='POST', payload=record,
                             extra_headers={'Prefer': 'return=minimal'})
                committed = True
            except Exception:
                if uploaded and not committed:
                    try:
                        await _remove_objects(client, uploaded)
                    except Exception:
                        LOG.exception('Compensation cleanup failed after upload error for %s', report_id)
                raise
            try:
                trimmed = await _trim(client, uid)
                return report_id, trimmed, None
            except Exception as exc:
                LOG.exception("Oldest-analysis cleanup failed for %s", uid)
                return report_id, 0, "Saved, but cleanup of older images failed. Retry later; check backend logs."


async def remove_one(uid: str, analysis_id: str):
    try:
        uuid.UUID(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid analysis ID.') from exc
    async with _lock(uid):
        async with httpx.AsyncClient() as client:
            rows = await _query(client, '/rest/v1/analyses', params={
                'user_id': f'eq.{uid}', 'id': f'eq.{analysis_id}', 'select': '*', 'limit': '1',
            })
            hits = rows.json()
            if not hits:
                raise HTTPException(status_code=404, detail='Analysis not found in your history.')
            await _delete_row(client, uid, hits[0])


async def clear_history(uid: str) -> int:
    async with _lock(uid):
        async with httpx.AsyncClient() as client:
            rows = await _rows(client, uid)
            for row in rows:
                await _delete_row(client, uid, row)
            return len(rows)
