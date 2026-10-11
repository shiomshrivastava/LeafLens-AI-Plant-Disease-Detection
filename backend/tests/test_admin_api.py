"""Offline unit tests; no network requests or real user modifications."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

# Import the real lightweight history module; injecting a stub into sys.modules
# breaks collection of other offline API tests in the same pytest session.
import admin_api as a
ADMIN = '00000000-0000-4000-8000-000000000001'
TARGET = '00000000-0000-4000-8000-000000000002'


def run(coro):
    return asyncio.run(coro)


def test_restriction_expired_vs_active():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert not a._active_restriction(None)
    assert not a._active_restriction({'status':'temporary_block','expires_at':past})
    assert a._active_restriction({'status':'temporary_block','expires_at':future})
    assert a._active_restriction({'status':'permanent_ban','expires_at':None})
    assert a._active_restriction({'status':'temporary_block','expires_at':'bad timestamp'})


def test_active_check_denies_banned(monkeypatch):
    async def get_restriction(_uid):
        return {'status': 'permanent_ban', 'expires_at':None}
    monkeypatch.setattr(a, '_get_restriction', get_restriction)
    with pytest.raises(HTTPException) as err:
        run(a.require_active_account(TARGET))
    assert err.value.status_code == 403


def test_non_admin_denied(monkeypatch):
    async def verified(_auth):
        return ADMIN
    async def permitted(_uid):
        return False
    async def active(_uid):
        return None
    # Stub only the authentication boundary for this test, not the global
    # history_store module. This remains fully offline and reaches the 403 check.
    monkeypatch.setattr(a, 'verified_user', verified)
    monkeypatch.setattr(a, '_is_admin', permitted)
    monkeypatch.setattr(a, 'require_active_account', active)
    with pytest.raises(HTTPException) as err:
        run(a._admin_id('Bearer whatever'))
    assert err.value.status_code == 403


def test_self_and_admin_are_protected(monkeypatch):
    async def other_is_admin(_uid):
        return True
    monkeypatch.setattr(a,'_is_admin',other_is_admin)
    with pytest.raises(HTTPException) as self_error:
        run(a._check_target(ADMIN, ADMIN))
    assert self_error.value.status_code == 403
    with pytest.raises(HTTPException) as other_error:
        run(a._check_target(ADMIN, TARGET))
    assert other_error.value.status_code == 403


def test_user_search_only_exposes_allowed_fields(monkeypatch):
    async def admin(_auth):
        return ADMIN
    class FakeResponse:
        headers = {'content-range':'0-0/1'}
        def __init__(self, rows):
            self.rows = rows
        def json(self):
            return self.rows
    async def req(method,path,**kw):
        if path.endswith('/profiles'):
            return FakeResponse([{'id': TARGET, 'display_name':'Test User',
                                  'email':'never-reveal@example.com'}])
        if path.endswith('/account_restrictions'):
            return FakeResponse([])
        raise AssertionError(path)
    monkeypatch.setattr(a,'_admin_id',admin)
    monkeypatch.setattr(a,'_request',req)
    reply = run(a.users(authorization='x', search='', page=1))
    assert reply['total'] == 1
    assert reply['items'][0] == {'id':TARGET,'display_name':'Test User',
                                  'status':'active','expires_at':None}
    assert 'email' not in str(reply)


def test_block_db_before_auth_and_then_audit(monkeypatch):
    events=[]
    async def admin(_auth): return ADMIN
    async def target_check(_admin,_target): return None
    async def restriction(_uid): return None
    async def save(*args): events.append(('db',args))
    async def auth(*args): events.append(('auth',args))
    async def audit(*args): events.append(('audit',args))
    monkeypatch.setattr(a,'_admin_id',admin)
    monkeypatch.setattr(a,'_check_target',target_check)
    monkeypatch.setattr(a,'_get_restriction',restriction)
    monkeypatch.setattr(a,'_upsert_restriction',save)
    monkeypatch.setattr(a,'_auth_ban',auth)
    monkeypatch.setattr(a,'_audit',audit)
    body=a.RestrictRequest(action='block_24h',reason='Repeated app abuse',confirm_account_id=TARGET)
    reply=run(a.moderate_user(TARGET,body,authorization='Bearer x'))
    assert reply['status']=='temporary_block'
    assert [x[0] for x in events] == ['db','auth','audit']
    assert events[1][1][1]=='24h'


def test_mismatch_rejected_without_actions(monkeypatch):
    async def admin(_auth): return ADMIN
    monkeypatch.setattr(a,'_admin_id',admin)
    body=a.RestrictRequest(action='ban',reason='Verified severe abuse',
                           confirm_account_id=ADMIN)
    with pytest.raises(HTTPException) as err:
        run(a.moderate_user(TARGET,body,authorization='Bearer x'))
    assert err.value.status_code==400


def test_account_delete_route_removed():
    assert not any(
        route.path == '/api/admin/users/{target_id}' and 'DELETE' in route.methods
        for route in a.router.routes
    )
