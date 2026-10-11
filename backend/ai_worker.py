"""Laptop-only AI inference service for LeafLens hybrid deployment.

Run from the backend folder:
    python -m uvicorn ai_worker:app --host 127.0.0.1 --port 8001

Expose ONLY port 8001 through an HTTPS tunnel, never the existing local
FastAPI/admin server on port 8000. All worker endpoints require a dedicated
32+ character secret passed in the X-Worker-Key header.
"""
from __future__ import annotations

import io
import os
import secrets
import warnings
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from inference_engine import analysis_engine

MAX_TRANSFER_BYTES = 80 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

app = FastAPI(
    title='LeafLens Private AI Worker',
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware('http')
async def restrict_worker(request: Request, call_next):
    if request.url.path not in ('/internal/analyze', '/internal/health'):
        return JSONResponse(status_code=404, content={'detail': 'Not found'})
    expected = os.getenv('LEAFLENS_AI_WORKER_TOKEN', '').strip()
    if len(expected) < 32 or 'REPLACE' in expected.upper() or 'PLACEHOLDER' in expected.upper():
        return JSONResponse(status_code=503, content={'detail': 'AI worker token is not configured.'})
    provided = request.headers.get('x-worker-key', '')
    if not provided or not secrets.compare_digest(provided, expected):
        return JSONResponse(status_code=401, content={'detail': 'Unauthorized AI worker access.'})
    return await call_next(request)


@app.get('/internal/health')
def health():
    return analysis_engine.status()


@app.post('/internal/analyze')
async def analyze(file: UploadFile = File(...)):
    if file.content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(status_code=415, detail='Unsupported image format.')
    try:
        raw = await file.read(MAX_TRANSFER_BYTES + 1)
    finally:
        await file.close()
    if not raw or len(raw) > MAX_TRANSFER_BYTES:
        raise HTTPException(status_code=413, detail='Invalid AI worker upload size.')
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
        return await run_in_threadpool(analysis_engine.run, image)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail='AI model unavailable on laptop.') from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail='AI worker inference failed.') from exc
