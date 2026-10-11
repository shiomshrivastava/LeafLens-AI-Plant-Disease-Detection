"""LeafLens local FastAPI: existing real AI inference plus private saved history."""
from __future__ import annotations

import io
import os
import logging
import warnings
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError

if os.getenv('LEAFLENS_BACKEND_MODE', 'local').strip().lower() == 'cloud':
    from remote_ai_engine import analysis_engine
else:
    from inference_engine import analysis_engine
from recommendations import build_recommendations
from iot_sensor import router as iot_router, is_configured as iot_is_configured
from history_store import (
    configured, verified_user as _verified_user, save_analysis, read_history, remove_one, clear_history,
)
from admin_api import router as admin_router, require_active_account

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger('leaflens.api')
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

def configured_cors_origins() -> list[str]:
    """Local development origins plus explicit HTTPS production site origins."""
    origins = ['http://localhost:5173', 'http://127.0.0.1:5173']
    for item in os.getenv('LEAFLENS_CORS_ORIGINS', '').split(','):
        origin = item.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.path
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise RuntimeError('LEAFLENS_CORS_ORIGINS must contain HTTPS origins only.')
        origins.append(origin)
    return list(dict.fromkeys(origins))


app = FastAPI(title='LeafLens Real AI Backend', version='0.2.0')
app.include_router(iot_router)
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_methods=['GET', 'POST', 'DELETE'],
    allow_headers=['Content-Type', 'Authorization'],
)


async def verified_user(authorization: str | None) -> str:
    # Existing endpoints now reject banned/blocked sessions on EVERY request.
    uid = await _verified_user(authorization)
    await require_active_account(uid)
    return uid


@app.get('/api/health')
def health():
    return {**analysis_engine.status(), 'history_configured': configured(), 'history_limit': 10, 'iot_configured': iot_is_configured()}


@app.get('/api/analyses')
async def analyses(authorization: str | None = Header(None)):
    uid = await verified_user(authorization)
    try:
        items = await read_history(uid)
        # Recompute older recommendations on read (including low-confidence ones
        # saved with the previous generic fallback). This upgrades the History
        # view + History PDF without changing Supabase schema or other fields.
        # New analyses already persist the current v2 recommendations.
        for item in items:
            result = item.get('report')
            if isinstance(result, dict):
                rec = result.get('recommendations')
                if not isinstance(rec, dict) or rec.get('version') != 2:
                    result['recommendations'] = build_recommendations(result)
        return {'items': items, 'limit': 10}
    except Exception:
        LOG.exception('Failed to read analysis history')
        raise HTTPException(status_code=502, detail='Could not load saved history. Check backend terminal.')


@app.delete('/api/analyses/{analysis_id}')
async def delete_analysis(analysis_id: str, authorization: str | None = Header(None)):
    uid = await verified_user(authorization)
    try:
        await remove_one(uid, analysis_id)
        return {'deleted': True, 'id': analysis_id}
    except HTTPException:
        raise
    except Exception:
        LOG.exception('Failed to remove analysis %s', analysis_id)
        raise HTTPException(status_code=502, detail='Could not fully delete analysis. Try again.')


@app.delete('/api/analyses')
async def delete_all_analyses(authorization: str | None = Header(None)):
    uid = await verified_user(authorization)
    try:
        count = await clear_history(uid)
        return {'deleted_count': count}
    except Exception:
        LOG.exception('History clear failed or was partial')
        raise HTTPException(status_code=502, detail='Could not finish clearing history. Some records may remain; refresh and retry.')


@app.post('/api/analyze')
async def analyze(file: UploadFile = File(...), authorization: str | None = Header(None)):
    # Verify the real Supabase user before performing expensive inference.
    uid = await verified_user(authorization)
    if file.content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(status_code=415, detail='Use a JPEG, PNG, or WebP image.')
    try:
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if not raw:
        raise HTTPException(status_code=400, detail='Image is empty.')
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail='Maximum image size is 10 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise HTTPException(status_code=415, detail='Unsupported image format.')
                w, h = source.size
                if w < 8 or h < 8 or w * h > MAX_PIXELS:
                    raise HTTPException(status_code=422, detail='Invalid image dimensions.')
                image = ImageOps.exif_transpose(source).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=422, detail='Image could not be decoded safely.') from exc

    try:
        report = await run_in_threadpool(analysis_engine.run, image)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception('Real AI inference failed')
        raise HTTPException(status_code=500, detail='Real AI inference failed. Check the Python terminal.') from exc

    # Model-4 is transparent rule-based advice, computed AFTER AI analysis.
    # Must be attached before save_analysis() stores result_data in Supabase.
    report['recommendations'] = build_recommendations(report)

    # Validation rejections still return their useful explanation to the user,
    # but do NOT fill up the latest-10 analysis history.
    saveable = report.get('decision') in {
        'HEALTHY', 'DISEASED_ANALYSIS_COMPLETE', 'REVIEW_CROP_DISAGREEMENT'
    }
    report['saved_analysis_id'] = None
    report['history_warning'] = None
    if saveable:
        try:
            analysis_id, removed, warning = await save_analysis(uid, file.filename or 'leaf.jpg', image, report)
            report['saved_analysis_id'] = analysis_id
            report['history_warning'] = warning
            if removed:
                LOG.info('Automatically removed %s old analyses for authenticated user', removed)
        except Exception:
            LOG.exception('Real inference succeeded but Supabase history save failed')
            report['history_warning'] = 'Analysis completed, but could not save to history. Check backend terminal.'
    return report
