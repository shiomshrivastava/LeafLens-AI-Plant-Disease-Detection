"""Read-only wrapper around the user's validated six-stage desktop pipeline.

Only paths are changed: checkpoints are read from backend/model_assets.
No weights are edited and no predictions are fabricated.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from PIL import Image

import pipeline_source as pipeline

LOG = logging.getLogger('leaflens.inference')
ASSETS = Path(__file__).resolve().parent / 'model_assets'
FILES = {
    'Model0A': ASSETS / 'Model0A' / 'MODEL0A_V3_THRESHOLD_CONFIG.json',
    'Model0B config': ASSETS / 'Model0B' / 'MODEL0B_FINAL_HF' / 'config.json',
    'Model0B weights': ASSETS / 'Model0B' / 'MODEL0B_FINAL_HF' / 'model.safetensors',
    'Model0B processor': ASSETS / 'Model0B' / 'MODEL0B_FINAL_HF' / 'preprocessor_config.json',
    'Model0C weights': ASSETS / 'Model0C' / 'MODEL0C_FINAL_BEST.pt',
    'Model0C info': ASSETS / 'Model0C' / 'MODEL0C_MODEL_INFO.json',
    'Model0C ECDF': ASSETS / 'Model0C' / 'MODEL0C_PORTABLE_ECDF.npz',
    'Model0C code': ASSETS / 'Model0C' / 'MODEL0C_LOCAL_INFERENCE.py',
    'Model1': ASSETS / 'Model1' / 'MODEL1_BEST_MODEL.keras',
    'Model2': ASSETS / 'Model2' / 'MODEL2_V4_SIGLIP2_BEST.pt',
    'Model3': ASSETS / 'Model3' / 'MODEL3_FINAL_BEST.keras',
}


def preflight() -> dict[str, Any]:
    missing = [str(p.relative_to(ASSETS)) for p in FILES.values() if not p.is_file()]
    messages = []
    # 0B's HF config must have true label names because the optional training .pt
    # is not included in the copied inference-only asset set.
    config = FILES['Model0B config']
    if config.is_file():
        try:
            id2label = json.loads(config.read_text(encoding='utf-8'))['id2label']
            names = [str(id2label[str(i)]) for i in range(3)]
            if 'usableleaf' not in [pipeline.normalized_crop(x) for x in names] or len(set(names)) != 3:
                messages.append('Model0B/config.json lacks verified three-class labels; copy original MODEL0B_SIGLIP2_BEST.pt to Model0B if available, or verify and configure labels manually. Never guess label order.')
        except (KeyError, TypeError, ValueError, OSError):
            messages.append('Model0B/config.json is missing valid id2label mapping; verify original label order before inference.')
    return {'assets_present': not missing, 'missing': missing, 'warnings': messages}


class AnalysisEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._models: tuple[Any, Any, Any, Any] | None = None
        self._error: str | None = None

    def status(self) -> dict[str, Any]:
        pf = preflight()
        return {
            'api_running': True,
            'models_loaded': self._models is not None,
            'asset_files_found': pf['assets_present'],
            'missing': pf['missing'],
            'warnings': pf['warnings'],
            'load_error': self._error,
            'note': 'File presence does not prove model compatibility; first prediction loads and verifies weights.',
        }

    def _load(self):
        pf = preflight()
        if pf['missing']:
            raise RuntimeError('Missing required model assets: ' + ', '.join(pf['missing']))
        # Paths in the original pipeline_source.py refer to the old Final models
        # directory. Override these module constants ONLY IN MEMORY.
        pipeline.A_DIR = ASSETS / 'Model0A'
        pipeline.B_DIR = ASSETS / 'Model0B'
        pipeline.C_DIR = ASSETS / 'Model0C'
        pipeline.M1_FILE = FILES['Model1']
        pipeline.M2_FILE = FILES['Model2']
        pipeline.M3_FILE = FILES['Model3']
        # Prevent accidental matplotlib window/file creation in a service.
        import torch
        device_mode = os.environ.get('LEAFLENS_DEVICE', 'auto').casefold()
        if device_mode not in ('auto', 'cpu', 'cuda'):
            raise RuntimeError('LEAFLENS_DEVICE must be auto, cpu, or cuda.')
        if device_mode == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but PyTorch cannot access CUDA.')
        device = torch.device('cuda' if device_mode == 'cuda' or (device_mode == 'auto' and torch.cuda.is_available()) else 'cpu')
        LOG.info('Loading verified pipeline using %s (may take several minutes)', device)
        a = pipeline.Model0A()
        b = pipeline.Model0B(device)
        c = pipeline.Model0C(device)
        downstream = pipeline.Downstream(device)
        self._models = a, b, c, downstream
        self._error = None
        LOG.info('All six stages loaded. No training or checkpoint writing performed.')

    @staticmethod
    def _image_as_png_url(image: Image.Image) -> str:
        output = io.BytesIO()
        image.save(output, format='PNG', optimize=True)
        return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')

    def run(self, image: Image.Image) -> dict[str, Any]:
        # Lock also prevents simultaneous heavy GPU inference and double initialization.
        with self._lock:
            if self._models is None:
                try:
                    self._load()
                except Exception as exc:
                    self._error = f'{type(exc).__name__}: {exc}'
                    LOG.exception('Real model initialization failed')
                    raise RuntimeError('Real AI models could not load. ' + self._error) from exc
            a, b, c, downstream = self._models
            from PIL import Image as PILImage
            import numpy as np
            with __import__('contextlib').redirect_stdout(io.StringIO()):
                report = pipeline.run_full_pipeline(image, a, b, c, downstream)
            stages = pipeline.concise_stage_summary(report)
            result = pipeline.serializable(report)
            result['stage_summary'] = stages
            result['explanation'] = pipeline.human_explanation(report)
            result['severity_basis'] = 'all_segmentation_image_pixels_not_leaf_only'
            result['quality_gate_notice'] = 'Model-0A is provisional, not the verified original V3 calculation.'
            result['crop_ood_notice'] = 'Model-0C can accept unsupported crops; acceptance is not a guarantee.'
            result['overlay_image'] = None
            result['mask_image'] = None

            m = report.get('model3')
            if m is not None:
                mask = np.asarray(m['binary_mask'], dtype=np.uint8) * 255
                # Overlay and binary mask match the ORIGINAL image dimensions.
                mask_pil = PILImage.fromarray(mask, 'L').resize(image.size, PILImage.Resampling.NEAREST)
                tint = PILImage.new('RGBA', image.size, (240, 71, 44, 0))
                alpha = mask_pil.point(lambda v: int(v * 0.58))
                tint.putalpha(alpha)
                output = PILImage.alpha_composite(image.convert('RGBA'), tint).convert('RGB')
                result['overlay_image'] = self._image_as_png_url(output)
                result['mask_image'] = self._image_as_png_url(mask_pil)
            return result


analysis_engine = AnalysisEngine()
