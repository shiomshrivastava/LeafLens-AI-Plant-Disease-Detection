"""Offline tests: no live Supabase account or trained weights required."""
import io
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import app
import history_store

client = TestClient(app.app)
USER_ID = '11111111-1111-4111-8111-111111111111'


def image_bytes():
    out = io.BytesIO()
    Image.new('RGB', (160, 160), '#32774b').save(out, format='PNG')
    return out.getvalue()


def mock_auth():
    return patch('app.verified_user', new=AsyncMock(return_value=USER_ID))


def test_health_reports_real_readiness():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['api_running'] is True
    assert r.json()['history_limit'] == 10


def test_no_auth_denies_history():
    r = client.get('/api/analyses')
    assert r.status_code in (401, 503)


def test_invalid_format_rejected_after_auth():
    with mock_auth():
        r = client.post('/api/analyze', files={'file': ('bad.txt', b'hello', 'text/plain')})
    assert r.status_code == 415


def test_nonimage_rejected_after_auth():
    with mock_auth():
        r = client.post('/api/analyze', files={'file': ('bad.png', b'hello', 'image/png')})
    assert r.status_code == 422


def test_non_leaf_does_not_persist():
    result = {'decision': 'NOT_USABLE_LEAF', 'stage_summary': [], 'explanation': 'Non-leaf'}
    with mock_auth(), patch('app.analysis_engine.run', return_value=result), \
            patch('app.save_analysis', new_callable=AsyncMock) as save:
        r = client.post('/api/analyze', files={'file': ('face.png', image_bytes(), 'image/png')})
    assert r.status_code == 200
    assert r.json()['saved_analysis_id'] is None
    save.assert_not_awaited()


def test_successful_inference_saved_under_verified_user():
    result = {'decision': 'HEALTHY', 'stage_summary': [], 'model1': {'status': 'HEALTHY'}}
    fake_save = AsyncMock(return_value=('22222222-2222-4222-8222-222222222222', 0, None))
    with mock_auth(), patch('app.analysis_engine.run', return_value=result), \
            patch('app.save_analysis', new=fake_save):
        r = client.post('/api/analyze', files={'file': ('leaf.png', image_bytes(), 'image/png')})
    assert r.status_code == 200
    assert r.json()['saved_analysis_id'] == '22222222-2222-4222-8222-222222222222'
    assert fake_save.await_args.args[0] == USER_ID


def test_save_failure_must_be_disclosed_not_faked():
    result = {'decision': 'HEALTHY', 'stage_summary': [], 'model1': {'status': 'HEALTHY'}}
    with mock_auth(), patch('app.analysis_engine.run', return_value=result), \
            patch('app.save_analysis', new=AsyncMock(side_effect=RuntimeError('offline'))):
        r = client.post('/api/analyze', files={'file': ('leaf.png', image_bytes(), 'image/png')})
    assert r.status_code == 200
    assert r.json()['saved_analysis_id'] is None
    assert 'could not save' in r.json()['history_warning']


def test_list_is_scoped_to_verified_user():
    loader = AsyncMock(return_value=[])
    with mock_auth(), patch('app.read_history', new=loader):
        r = client.get('/api/analyses')
    assert r.status_code == 200
    assert r.json() == {'items': [], 'limit': 10}
    loader.assert_awaited_once_with(USER_ID)


def test_delete_one_only_authenticated_user():
    deleter = AsyncMock()
    with mock_auth(), patch('app.remove_one', new=deleter):
        r = client.delete('/api/analyses/22222222-2222-4222-8222-222222222222')
    assert r.status_code == 200
    deleter.assert_awaited_once_with(USER_ID, '22222222-2222-4222-8222-222222222222')


def test_clear_all_only_authenticated_user():
    clearer = AsyncMock(return_value=3)
    with mock_auth(), patch('app.clear_history', new=clearer):
        r = client.delete('/api/analyses')
    assert r.status_code == 200
    assert r.json() == {'deleted_count': 3}
    clearer.assert_awaited_once_with(USER_ID)


def test_webp_is_downsized():
    image = Image.new('RGB', (3000, 2000), '#219a66')
    data = history_store._webp(image)
    with Image.open(io.BytesIO(data)) as result:
        assert max(result.size) <= 1600


def test_auth_header_required():
    # Verify the actual authorization guard doesn't accept a supplied user_id.
    import asyncio
    with patch('history_store.configured', return_value=True):
        try:
            asyncio.run(history_store.verified_user(''))
        except Exception as exc:
            assert getattr(exc, 'status_code', None) == 401
        else:
            raise AssertionError('Missing access token must be rejected')
