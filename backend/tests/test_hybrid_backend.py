"""Offline hybrid deployment regression tests; never load real AI weights."""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import remote_ai_engine as remote
import ai_worker


def _image():
    return Image.new('RGB', (32, 32), '#42945c')


def test_cloud_mode_does_not_import_local_inference_engine():
    env = os.environ.copy()
    env['LEAFLENS_BACKEND_MODE'] = 'cloud'
    code = (
        "import app, sys; "
        "assert app.analysis_engine.__class__.__name__ == 'RemoteAnalysisEngine'; "
        "assert 'inference_engine' not in sys.modules; "
        "assert app.health()['inference_mode'] == 'remote_worker'"
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr


def test_worker_requires_long_secret_and_https(monkeypatch):
    monkeypatch.delenv('LEAFLENS_AI_WORKER_TOKEN', raising=False)
    monkeypatch.setenv('LEAFLENS_AI_WORKER_URL', 'https://example.com')
    with pytest.raises(RuntimeError, match='token'):
        remote.worker_settings()
    monkeypatch.setenv('LEAFLENS_AI_WORKER_TOKEN', 's' * 48)
    monkeypatch.setenv('LEAFLENS_AI_WORKER_URL', 'http://external.example.com')
    with pytest.raises(RuntimeError, match='HTTPS'):
        remote.worker_settings()
    monkeypatch.setenv('LEAFLENS_AI_WORKER_URL', 'https://example.com')
    assert remote.worker_settings()[0] == 'https://example.com'


def test_remote_engine_forwards_only_worker_token(monkeypatch):
    monkeypatch.setenv('LEAFLENS_AI_WORKER_TOKEN', 's' * 48)
    monkeypatch.setenv('LEAFLENS_AI_WORKER_URL', 'https://example.com')
    seen = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'decision': 'HEALTHY', 'stage_summary': []}

    class FakeClient:
        def __init__(self, **kw):
            assert kw['follow_redirects'] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, headers, files):
            seen.append((url, headers, files))
            return FakeResponse()

    monkeypatch.setattr(remote.httpx, 'Client', FakeClient)
    report = remote.analysis_engine.run(_image())
    assert report['decision'] == 'HEALTHY'
    assert seen[0][0] == 'https://example.com/internal/analyze'
    assert seen[0][1] == {'X-Worker-Key': 's' * 48}
    assert seen[0][2]['file'][1][:8] == bytes.fromhex('89504e470d0a1a0a')


def test_ai_worker_rejects_unauthorized_requests(monkeypatch):
    monkeypatch.setenv('LEAFLENS_AI_WORKER_TOKEN', 'w' * 48)
    client = TestClient(ai_worker.app)
    assert client.get('/').status_code == 404
    assert client.get('/internal/health').status_code == 401
    assert client.post('/internal/analyze', files={'file': ('leaf.png', b'ignored', 'image/png')}).status_code == 401


def test_ai_worker_accepts_authenticated_inference_offline(monkeypatch):
    monkeypatch.setenv('LEAFLENS_AI_WORKER_TOKEN', 'w' * 48)
    output = io.BytesIO()
    _image().save(output, format='PNG')
    with patch('ai_worker.analysis_engine.run', return_value={'decision': 'HEALTHY'}) as run:
        result = TestClient(ai_worker.app).post(
            '/internal/analyze',
            headers={'X-Worker-Key': 'w' * 48},
            files={'file': ('leaf.png', output.getvalue(), 'image/png')},
        )
    assert result.status_code == 200
    assert result.json()['decision'] == 'HEALTHY'
    run.assert_called_once()


def test_cors_adds_only_explicit_https_origins(monkeypatch):
    import app
    monkeypatch.setenv(
        'LEAFLENS_CORS_ORIGINS',
        'https://leaflens-demo.vercel.app, https://preview.example.org/',
    )
    origins = app.configured_cors_origins()
    assert 'http://127.0.0.1:5173' in origins
    assert 'https://leaflens-demo.vercel.app' in origins
    assert 'https://preview.example.org' in origins
    monkeypatch.setenv('LEAFLENS_CORS_ORIGINS', 'http://attacker.example.org')
    with pytest.raises(RuntimeError, match='HTTPS'):
        app.configured_cors_origins()


def test_cloud_iot_returns_offline_without_database(monkeypatch):
    import cloud_iot
    from fastapi.testclient import TestClient
    import app
    monkeypatch.setattr(cloud_iot, 'is_configured', lambda: False)
    import os
    # Do not touch production databases during offline unit tests.
    assert not cloud_iot.is_configured()
    # Test direct endpoint method, rather than the local-mode app router.
    import asyncio
    result = asyncio.run(cloud_iot.current_reading())
    assert result['online'] is False
    assert result['temperature_c'] is None


def test_cloud_iot_fresh_reading(monkeypatch):
    import asyncio
    import cloud_iot
    from datetime import datetime, timezone
    monkeypatch.setenv('SUPABASE_URL', 'https://demo.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'test-secret')
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return [{'temperature_c': 26.1, 'humidity_percent': 61.2,
                     'updated_at': datetime.now(timezone.utc).isoformat()}]
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, url, headers, params):
            assert url.endswith('/rest/v1/leaflens_iot_latest')
            assert params['device_id'] == 'eq.leaflens-demo'
            return FakeResponse()
    monkeypatch.setattr(cloud_iot.httpx, 'AsyncClient', FakeClient)
    result = asyncio.run(cloud_iot.current_reading())
    assert result['online'] is True
    assert result['temperature_c'] == 26.1
