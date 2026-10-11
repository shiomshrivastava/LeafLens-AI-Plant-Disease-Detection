"""Cloud-side adapter for the existing LeafLens analysis API.

Only the laptop AI worker loads real model weights. The cloud API validates
the user's Supabase session before invoking this adapter, then saves the
result to the user's private history as before.
"""
from __future__ import annotations

import io
import logging
import os
from urllib.parse import urlsplit

import httpx
from PIL import Image

LOG = logging.getLogger('leaflens.remote_ai')
MAX_TRANSFER_BYTES = 80 * 1024 * 1024


def worker_settings() -> tuple[str, str]:
    """Fail closed: no default tunnel address or insecure public transport."""
    base = os.getenv('LEAFLENS_AI_WORKER_URL', '').strip().rstrip('/')
    token = os.getenv('LEAFLENS_AI_WORKER_TOKEN', '').strip()
    if len(token) < 32 or 'REPLACE' in token.upper() or 'PLACEHOLDER' in token.upper():
        raise RuntimeError('AI worker security token is not configured.')
    parsed = urlsplit(base)
    local_http = parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')
    if not (parsed.scheme == 'https' or local_http):
        raise RuntimeError('AI worker requires an HTTPS URL (HTTP allowed only for local tests).')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError('Invalid AI worker URL configuration.')
    if parsed.path not in ('', '/'):
        raise RuntimeError('AI worker URL must not include a path.')
    return base, token


class RemoteAnalysisEngine:
    """Drop-in implementation of the existing analysis_engine interface."""

    def status(self) -> dict:
        try:
            worker_settings()
            ready = True
        except RuntimeError:
            ready = False
        return {
            'api_running': True,
            'models_loaded': None,  # Unknown until a worker request is made.
            'asset_files_found': None,  # Weights are intentionally not in the cloud.
            'missing': [],
            'warnings': [],
            'load_error': None,
            'inference_mode': 'remote_worker',
            'worker_configured': ready,
            'note': 'Cloud API uses a separate laptop AI worker. Status does not prove the worker is online.',
        }

    def run(self, image: Image.Image) -> dict:
        base, token = worker_settings()
        payload = io.BytesIO()
        # Lossless transfer preserves the validated input for segmentation.
        image.save(payload, format='PNG')
        raw = payload.getvalue()
        if len(raw) > MAX_TRANSFER_BYTES:
            raise RuntimeError('Image is too large to transfer to the AI worker.')
        try:
            with httpx.Client(timeout=httpx.Timeout(300.0, connect=12.0), follow_redirects=False) as client:
                response = client.post(
                    base + '/internal/analyze',
                    headers={'X-Worker-Key': token},
                    files={'file': ('leaf.png', raw, 'image/png')},
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError('AI worker timed out. Check that the laptop and tunnel are running.') from exc
        except httpx.RequestError as exc:
            LOG.warning('AI worker connection unavailable: %s', type(exc).__name__)
            raise RuntimeError('AI worker is offline. Start the laptop worker and HTTPS tunnel.') from exc

        if response.status_code in (401, 403):
            raise RuntimeError('AI worker authentication failed. Check the shared worker token.')
        if response.status_code == 503:
            raise RuntimeError('AI worker is not ready. Check the laptop model server.')
        if response.status_code != 200:
            raise RuntimeError(f'AI worker request failed (HTTP {response.status_code}).')
        try:
            report = response.json()
        except ValueError as exc:
            raise RuntimeError('AI worker returned invalid JSON.') from exc
        if not isinstance(report, dict) or not isinstance(report.get('decision'), str):
            raise RuntimeError('AI worker returned an invalid analysis report.')
        return report


analysis_engine = RemoteAnalysisEngine()
