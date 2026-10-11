"""LeafLens privacy-preserving admin API.

Requires the five admin tables created in Step 1 and a server-only Supabase
secret in backend/.env. This module NEVER returns emails, user metadata,
private analyses, images, or auth tokens to the admin UI.

Important: protection on direct Supabase calls is provided by the separate
SQL_STEP3_RESTRICTIONS.sql (apply it before using moderation routes).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from history_store import verified_user

LOG = logging.getLogger('leaflens.admin')
router = APIRouter(prefix='/api/admin', tags=['Admin'])
URL = os.getenv('SUPABASE_URL', '').rstrip('/')
KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
LIMIT = 25


def _config_check():
    if not URL.startswith('https://') or not KEY:
        raise HTTPException(503, 'Admin service is not configured on the backend.')


def _headers(*, write: bool = False) -> dict[str, str]:
    _config_check()
    # sb_secret_* is an API key, not a JWT. Do not send it in Authorization.
    headers = {'apikey': KEY}
    if not KEY.startswith('sb_secret_'):
        headers['Authorization'] = f'Bearer {KEY}'
    if write:
        headers['Content-Type'] = 'application/json'
    return headers


async def _request(method: str, path: str, *, params=None, payload=None,
                   prefer: str | None = None) -> httpx.Response:
    headers = _headers(write=payload is not None)
    if prefer:
        headers['Prefer'] = prefer
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.request(method, URL + path, params=params,
                                       json=payload, headers=headers)
    except httpx.HTTPError as exc:
        LOG.warning('Admin service network error: %s', type(exc).__name__)
        raise HTTPException(502, 'Admin database service could not be reached.') from exc
    if res.status_code >= 400:
        # Never expose Supabase internals or user details to the browser.
        LOG.error('Admin upstream error: %s %s HTTP %s: %s', method,
                  path.split('?')[0], res.status_code, res.text[:200])
        raise HTTPException(502, 'Admin operation failed. Check the backend terminal.')
    return res


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(400, 'Invalid account ID.') from exc


def _now():
    return datetime.now(timezone.utc)


def _active_restriction(row: dict | None) -> bool:
    if not row:
        return False
    if row.get('status') == 'permanent_ban':
        return True
    if row.get('status') != 'temporary_block':
        return False
    expiry = row.get('expires_at')
    if not isinstance(expiry, str):
        return True  # Fail closed on malformed restriction.
    try:
        return datetime.fromisoformat(expiry.replace('Z', '+00:00')) > _now()
    except ValueError:
        return True


async def _get_restriction(user_id: str) -> dict | None:
    res = await _request('GET', '/rest/v1/account_restrictions', params={
        'select': 'status,reason,expires_at,created_at', 'user_id': f'eq.{user_id}',
        'limit': '1',
    })
    rows = res.json()
    return rows[0] if rows else None


async def require_active_account(user_id: str) -> None:
    """Use on every authenticated LeafLens API request (not just admin URLs)."""
    restriction = await _get_restriction(user_id)
    if _active_restriction(restriction):
        raise HTTPException(403, 'This account is restricted. Please contact support.')


async def _is_admin(user_id: str) -> bool:
    res = await _request('GET', '/rest/v1/admin_accounts', params={
        'select': 'user_id', 'user_id': f'eq.{user_id}', 'limit': '1',
    })
    return bool(res.json())


async def _admin_id(authorization: str | None) -> str:
    uid = await verified_user(authorization)  # verify genuine Supabase token
    await require_active_account(uid)
    if not await _is_admin(uid):
        raise HTTPException(403, 'Admin access required.')
    return uid


async def _check_target(admin_id: str, target_id: str):
    if admin_id == target_id:
        raise HTTPException(403, 'Cannot moderate your own admin account.')
    if await _is_admin(target_id):
        raise HTTPException(403, 'Cannot moderate another administrator.')
    # Lookup is server side only, and result is never returned to browser.
    res = await _request('GET', f'/auth/v1/admin/users/{target_id}')
    if not isinstance(res.json(), dict) or not res.json().get('id'):
        raise HTTPException(404, 'Account not found.')


async def _audit(admin_id: str, target_id: str, action: str, reason: str):
    await _request('POST', '/rest/v1/moderation_audit_logs', payload={
        'admin_id': admin_id, 'target_user_id': target_id,
        'action': action, 'reason': reason,
    }, prefer='return=minimal')


async def _auth_ban(target_id: str, duration: str):
    await _request('PUT', f'/auth/v1/admin/users/{target_id}',
                   payload={'ban_duration': duration})


async def _upsert_restriction(target_id: str, status: str,
                              reason: str, expiry: str | None):
    await _request('POST', '/rest/v1/account_restrictions', payload={
        'user_id': target_id, 'status': status, 'reason': reason,
        'expires_at': expiry, 'updated_at': _now().isoformat(),
    }, prefer='resolution=merge-duplicates,return=minimal')


async def _delete_restriction(target_id: str):
    await _request('DELETE', '/rest/v1/account_restrictions', params={
        'user_id': f'eq.{target_id}',
    }, prefer='return=minimal')


@router.get('/me')
async def admin_me(authorization: str | None = Header(None)):
    await _admin_id(authorization)
    return {'admin': True}


@router.get('/users')
async def users(authorization: str | None = Header(None),
                search: str = Query('', max_length=80),
                page: int = Query(1, ge=1, le=10000)):
    await _admin_id(authorization)
    search = search.strip()
    params = {
        'select': 'id,display_name',
        'order': 'display_name.asc.nullslast,id.asc',
        'limit': str(LIMIT), 'offset': str((page - 1) * LIMIT),
    }
    if search:
        # Prevent PostgREST filter syntax injection and accidental wildcards.
        if re.fullmatch(r'[0-9a-fA-F-]{36}', search):
            try:
                params['id'] = 'eq.' + _uuid(search)
            except HTTPException:
                params['display_name'] = 'ilike.*' + re.sub(r'[^\w \-]', '', search) + '*'
        else:
            safe = re.sub(r'[^\w \-]', '', search, flags=re.UNICODE).strip()
            if not safe:
                return {'items': [], 'page': page, 'page_size': LIMIT, 'total': 0}
            params['display_name'] = 'ilike.*' + safe.replace(' ', '*') + '*'
    res = await _request('GET', '/rest/v1/profiles', params=params, prefer='count=exact')
    profiles = res.json()
    ids = [p['id'] for p in profiles]
    restrictions = {}
    if ids:
        match = ','.join(ids)
        rows = (await _request('GET', '/rest/v1/account_restrictions', params={
            'select': 'user_id,status,expires_at', 'user_id': f'in.({match})',
        })).json()
        restrictions = {r['user_id']: r for r in rows}
    items = []
    for p in profiles:
        restriction = restrictions.get(p['id'])
        status = 'active'
        if _active_restriction(restriction):
            status = 'banned' if restriction['status'] == 'permanent_ban' else 'blocked'
        items.append({
            'id': p['id'],
            'display_name': (p.get('display_name') or 'Unnamed user')[:100],
            'status': status,
            'expires_at': restriction.get('expires_at') if status == 'blocked' else None,
        })
    range_header = res.headers.get('content-range', '')
    try:
        total = int(range_header.split('/')[-1])
    except ValueError:
        total = None
    return {'items': items, 'page': page, 'page_size': LIMIT, 'total': total}


async def _count(path: str, *, filters=None) -> int:
    params = {'select': 'id', 'limit': '0', **(filters or {})}
    res = await _request('GET', path, params=params, prefer='count=exact')
    try:
        return int(res.headers['content-range'].split('/')[-1])
    except (KeyError, ValueError) as exc:
        raise HTTPException(502, 'Cannot read aggregate count.') from exc


@router.get('/stats')
async def stats(authorization: str | None = Header(None)):
    await _admin_id(authorization)
    # Counts only, no private rows or filenames are returned.
    total_users, total_analyses, healthy, diseased, review = await asyncio.gather(
        _count('/rest/v1/profiles'),
        _count('/rest/v1/analyses'),
        _count('/rest/v1/analyses', filters={'result_status': 'eq.HEALTHY'}),
        _count('/rest/v1/analyses', filters={'result_status': 'eq.DISEASED_ANALYSIS_COMPLETE'}),
        _count('/rest/v1/analyses', filters={'result_status': 'eq.REVIEW_CROP_DISAGREEMENT'}),
    )
    return {'total_users': total_users, 'total_saved_analyses': total_analyses,
            'healthy_analyses': healthy, 'diseased_analyses': diseased,
            'review_analyses': review}


@router.get('/system')
async def system_status(authorization: str | None = Header(None)):
    await _admin_id(authorization)
    # Do not publish keys, full health internals, files, or private rows.
    await _count('/rest/v1/profiles')
    return {'api': 'online', 'supabase_database': 'online',
            'note': 'IoT connectivity is displayed on the existing Weather page.'}


class RestrictRequest(BaseModel):
    action: Literal['block_24h', 'block_7d', 'ban', 'unblock']
    reason: str = Field(min_length=8, max_length=500)
    confirm_account_id: str = Field(min_length=36, max_length=36)


# In-process protection against accidental concurrent admin clicks.
# Production multi-replica deployment should use a transactional job system.
_LOCKS: dict[str, asyncio.Lock] = {}


@router.post('/users/{target_id}/moderate')
async def moderate_user(target_id: str, body: RestrictRequest,
                        authorization: str | None = Header(None)):
    admin_id = await _admin_id(authorization)
    target_id = _uuid(target_id)
    if body.confirm_account_id != target_id:
        raise HTTPException(400, 'Confirmation account ID does not match.')
    async with _LOCKS.setdefault(target_id, asyncio.Lock()):
        await _check_target(admin_id, target_id)
        reason = body.reason.strip()
        if len(reason) < 8:
            raise HTTPException(422, 'A meaningful moderation reason is required.')
        current = await _get_restriction(target_id)
        if body.action == 'unblock':
            # Auth first: if DB cleanup fails, RLS protection stays in place.
            await _auth_ban(target_id, 'none')
            await _delete_restriction(target_id)
            event = 'remove_ban' if current and current.get('status') == 'permanent_ban' else 'unblock'
            status = 'active'
            until = None
        else:
            if body.action == 'ban':
                event, status, duration, expiry = 'permanent_ban', 'permanent_ban', '876000h', None
            else:
                hours = 24 if body.action == 'block_24h' else 168
                event, status, duration = 'temporary_block', 'temporary_block', f'{hours}h'
                expiry = (_now() + timedelta(hours=hours)).isoformat()
            # DB restriction first: immediately blocks backend and RLS requests.
            await _upsert_restriction(target_id, status, reason, expiry)
            await _auth_ban(target_id, duration)
            until = expiry
        await _audit(admin_id, target_id, event, reason)
    return {'account_id': target_id, 'status': status, 'expires_at': until}


@router.get('/audit')
async def audit_log(authorization: str | None = Header(None),
                    page: int = Query(1, ge=1, le=10000)):
    await _admin_id(authorization)
    res = await _request('GET', '/rest/v1/moderation_audit_logs', params={
        'select': 'id,admin_id,target_user_id,action,reason,created_at',
        'order': 'created_at.desc', 'limit': str(LIMIT),
        'offset': str((page - 1) * LIMIT),
    })
    return {'items': res.json(), 'page': page}


class CaseRequest(BaseModel):
    account_id: str
    reason: str = Field(min_length=8, max_length=1000)


@router.get('/cases')
async def get_cases(authorization: str | None = Header(None),
                    page: int = Query(1, ge=1, le=10000)):
    await _admin_id(authorization)
    res = await _request('GET', '/rest/v1/moderation_cases', params={
        'select': 'id,user_id,reason,status,created_at,resolved_at',
        'order': 'created_at.desc', 'limit': str(LIMIT),
        'offset': str((page - 1) * LIMIT),
    })
    return {'items': res.json(), 'page': page}


@router.post('/cases')
async def add_case(body: CaseRequest, authorization: str | None = Header(None)):
    admin_id = await _admin_id(authorization)
    target_id = _uuid(body.account_id)
    await _check_target(admin_id, target_id)
    res = await _request('POST', '/rest/v1/moderation_cases', payload={
        'user_id': target_id, 'reason': body.reason.strip(), 'status': 'open',
    }, prefer='return=representation')
    return {'case_id': res.json()[0]['id'], 'status': 'open'}


@router.post('/cases/{case_id}/resolve')
async def resolve_case(case_id: str, authorization: str | None = Header(None)):
    await _admin_id(authorization)
    case_id = _uuid(case_id)
    res = await _request('PATCH', '/rest/v1/moderation_cases',
                         params={'id': f'eq.{case_id}', 'status': 'neq.resolved'},
                         payload={'status': 'resolved', 'resolved_at': _now().isoformat()},
                         prefer='return=representation')
    if not res.json():
        raise HTTPException(404, 'Unresolved case not found.')
    return {'case_id': case_id, 'status': 'resolved'}
