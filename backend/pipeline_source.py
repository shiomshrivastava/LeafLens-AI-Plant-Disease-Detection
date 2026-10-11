"""Major Project | Final Human-Friendly Single-Image Inference.

Run as a normal Python file or inside Jupyter with %run.

IMPORTANT:
* 0A is a PROVISIONAL implementation using documented V3 thresholds. The
  original 0A metric-calculation/source code was not supplied. DO NOT describe
  its outputs as reproduced final V3 validation until checked against that code.
* 0B and 0C load saved trained model weights, no training.
* 0C has limited unknown-crop detection reliability; accepted != guaranteed valid.
* Existing Model-1 / Model-2 / Model-3 behavior is retained as closely as possible.
* This script never modifies model files. Reports go to separate local folder.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(r"E:\Major Project\Final models")
MODEL0 = ROOT / "Model 0"
A_DIR = MODEL0 / "Model0A_V3_Final_Validation"
B_DIR = MODEL0 / "Model0B_SigLIP2_Final"
C_DIR = MODEL0 / "MODEL0C_FINAL_READY"

M1_FILE = ROOT / "Model_1_31Crop_Backbone_Comparison" / "MODEL1_BEST_MODEL.keras"
M2_FILE = ROOT / "Model_2_V4_SigLIP2_54Class" / "MODEL2_V4_SIGLIP2_BEST.pt"
M3_FILE = ROOT / "Model_3_PlantSeg_Final" / "MODEL3_FINAL_BEST.keras"

OUTPUT_DIR = Path(r"E:\Major Project\MODEL0_PIPELINE_TEST_RESULTS")

M0B_THRESHOLD = 0.4853
M1_THRESHOLD = 0.51
M3_THRESHOLD = 0.33
SEVERITY_MILD_MAX = 19.497952
SEVERITY_MODERATE_MAX = 50.379752

# REQUIRED only if the original HF config AND .pt BOTH lack meaningful class labels.
# Example: ("USABLE_LEAF", "LEAF_PRESENT_NOT_USABLE", "NON_LEAF")
# WARNING: Do not guess the order. Inspect your saved checkpoint/config first.
MODEL0B_LABEL_ORDER_OVERRIDE = None

# If crop assigned by Model-2 conflicts with 0C, don't silently report a disease.
STRICT_CROP_AGREEMENT = True  # A disagreement is FLAGGED, not silently ignored

A_DEFAULT = dict(
    MIN_DIMENSION=128, GRID_SIZE=4,
    LOCAL_TOP25_THRESHOLD=80.0, SHARP_TILE_THRESHOLD=60.0,
    MIN_SHARP_TILE_FRACTION=0.125, DARK_MEAN_THRESHOLD=40.0,
    BRIGHT_MEAN_THRESHOLD=215.0, MAX_DARK_PIXEL_RATIO=0.60,
    MAX_BRIGHT_PIXEL_RATIO=0.50, MIN_CONTRAST_STD=20.0,
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def pretty(x):
    return str(x).replace("___", " ").replace("__", " ").replace("_", " ").strip().title()


def normalized_crop(x):
    return "".join(ch for ch in str(x).casefold() if ch.isalnum())


def find_numeric(obj, key, candidates=None):
    """Find an exact named numeric threshold, including nested configs."""
    if candidates is None:
        candidates = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).upper() == key and isinstance(v, (int, float)) and not isinstance(v, bool):
                candidates.append(float(v))
            find_numeric(v, key, candidates)
    elif isinstance(obj, list):
        for v in obj:
            find_numeric(v, key, candidates)
    return candidates[0] if candidates else None


class Model0A:
    """Quality-gate implementation from documented thresholds, not exact V3 replay."""
    def __init__(self):
        self.params = A_DEFAULT.copy()
        cfg = A_DIR / "MODEL0A_V3_THRESHOLD_CONFIG.json"
        if cfg.is_file():
            raw = read_json(cfg)
            for k in self.params:
                val = find_numeric(raw, k)
                if val is not None:
                    self.params[k] = val
        else:
            print("[0A] WARNING: exact config JSON absent; documented defaults used")
        print("[0A] Provisional quality calculations; ORIGINAL validator code not provided")

    def predict(self, image):
        import numpy as np
        from PIL import Image
        p = self.params
        width, height = image.size
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        mean, std = float(gray.mean()), float(gray.std())
        dark_ratio = float(np.mean(gray < p["DARK_MEAN_THRESHOLD"]))
        bright_ratio = float(np.mean(gray > p["BRIGHT_MEAN_THRESHOLD"]))
        n = int(p["GRID_SIZE"])
        # PROVISIONAL Laplacian tile sharpness; exact original tiling/calculation unknown.
        scores = []
        for ty in range(n):
            for tx in range(n):
                y0, y1 = (ty * height) // n, ((ty + 1) * height) // n
                x0, x1 = (tx * width) // n, ((tx + 1) * width) // n
                a = gray[y0:y1, x0:x1]
                if min(a.shape) < 3:
                    scores.append(0.0)
                else:
                    mid = a[1:-1, 1:-1]
                    lap = (a[:-2, 1:-1] + a[2:, 1:-1] +
                           a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * mid)
                    scores.append(float(np.var(lap)))
        topn = max(1, int(math.ceil(len(scores) * 0.25)))
        top25 = float(np.mean(sorted(scores, reverse=True)[:topn]))
        sharp_frac = float(np.mean(np.asarray(scores) >= p["SHARP_TILE_THRESHOLD"]))
        failed = []
        if min(width, height) < p["MIN_DIMENSION"]: failed.append("LOW_RESOLUTION")
        if top25 < p["LOCAL_TOP25_THRESHOLD"]: failed.append("BLUR_LOCAL_TOP25")
        if sharp_frac < p["MIN_SHARP_TILE_FRACTION"]: failed.append("TOO_FEW_SHARP_TILES")
        if mean < p["DARK_MEAN_THRESHOLD"]: failed.append("TOO_DARK")
        if mean > p["BRIGHT_MEAN_THRESHOLD"]: failed.append("TOO_BRIGHT")
        if dark_ratio > p["MAX_DARK_PIXEL_RATIO"]: failed.append("TOO_MANY_DARK_PIXELS")
        if bright_ratio > p["MAX_BRIGHT_PIXEL_RATIO"]: failed.append("TOO_MANY_BRIGHT_PIXELS")
        if std < p["MIN_CONTRAST_STD"]: failed.append("LOW_CONTRAST")
        return {
            "accepted": not failed, "reasons": failed,
            "quality_metrics": {"width": width, "height": height, "brightness_mean": mean,
                                "contrast_std": std, "dark_ratio": dark_ratio,
                                "bright_ratio": bright_ratio, "top25_sharpness": top25,
                                "sharp_tile_fraction": sharp_frac},
            "verification": "PROVISIONAL_THRESHOLDS_ORIGINAL_V3_FORMULA_NOT_VERIFIED",
        }


def infer_b_labels(model, checkpoint_path):
    """Never silently assume LABEL_0 maps to USABLE_LEAF."""
    if MODEL0B_LABEL_ORDER_OVERRIDE is not None:
        v = list(MODEL0B_LABEL_ORDER_OVERRIDE)
        if len(v) != 3: raise RuntimeError("MODEL0B_LABEL_ORDER_OVERRIDE must contain 3 labels")
        return v, "manual verified override"
    mapping = getattr(model.config, "id2label", None)
    if mapping:
        labels = [mapping.get(i, mapping.get(str(i), "")) for i in range(3)]
        if any("USABLE" in str(x).upper() for x in labels) and all(labels):
            return [str(x) for x in labels], "HF config"
    # Common checkpoint metadata keys; use only if clearly labeled.
    import torch
    if checkpoint_path.is_file():
        ck = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if isinstance(ck, dict):
            for k in ("class_to_idx", "label_to_idx", "class_mapping"):
                d = ck.get(k)
                if isinstance(d, dict) and len(d) == 3:
                    try:
                        labels = [None] * 3
                        for name, i in d.items(): labels[int(i)] = str(name)
                        if all(labels) and any("USABLE" in x.upper() for x in labels):
                            return labels, "checkpoint:" + k
                    except Exception:
                        pass
            for k in ("idx_to_class", "idx_to_label"):
                d = ck.get(k)
                if isinstance(d, dict) and len(d) == 3:
                    labels = [str(d.get(i, d.get(str(i), ""))) for i in range(3)]
                    if all(labels) and any("USABLE" in x.upper() for x in labels):
                        return labels, "checkpoint:" + k
            for k in ("class_names", "classes", "labels"):
                v = ck.get(k)
                if isinstance(v, (list, tuple)) and len(v) == 3:
                    labels = [str(x) for x in v]
                    if any("USABLE" in x.upper() for x in labels):
                        return labels, "checkpoint:" + k
    raise RuntimeError(
        "Model-0B label order is UNKNOWN. Check MODEL0B_FINAL_HF/config.json "
        "or checkpoint metadata, then set MODEL0B_LABEL_ORDER_OVERRIDE to the VERIFIED class order. "
        "Cannot safely continue with guessed labels."
    )


class Model0B:
    def __init__(self, device):
        import torch
        from transformers import SiglipForImageClassification, SiglipImageProcessor
        folder = B_DIR / "MODEL0B_FINAL_HF"
        if not folder.is_dir(): raise FileNotFoundError(folder)
        self.model = SiglipForImageClassification.from_pretrained(
            str(folder), local_files_only=True).to(device).eval()
        try:
            self.processor = SiglipImageProcessor.from_pretrained(str(folder), local_files_only=True)
        except Exception:
            self.processor = SiglipImageProcessor(do_resize=True, size={"height": 224, "width": 224},
                resample=2, do_rescale=True, rescale_factor=1.0 / 255.0,
                do_normalize=True, image_mean=[0.5] * 3, image_std=[0.5] * 3)
            print("[0B] WARNING: manual fallback image processor; verify against original")
        self.labels, origin = infer_b_labels(self.model, B_DIR / "MODEL0B_SIGLIP2_BEST.pt")
        canon = [normalized_crop(x) for x in self.labels]
        if len(set(canon)) != 3 or "usableleaf" not in canon:
            raise RuntimeError("0B labels invalid: " + repr(self.labels))
        self.good_idx = canon.index("usableleaf")
        self.device = device
        self.torch = torch
        print(f"[0B] Labels: {self.labels} ({origin}) | accepted threshold={M0B_THRESHOLD}")

    def predict(self, image):
        t = self.processor(images=image, return_tensors="pt")["pixel_values"].to(self.device)
        with self.torch.inference_mode():
            logits = self.model(pixel_values=t).logits
            probs = self.torch.softmax(logits, dim=-1)[0].cpu().tolist()
        top = max(range(len(probs)), key=probs.__getitem__)
        return {"accepted": bool(top == self.good_idx and probs[self.good_idx] >= M0B_THRESHOLD),
                "predicted_class": self.labels[top], "confidence": probs[top],
                "usable_probability": probs[self.good_idx],
                "probabilities": dict(zip(self.labels, probs)), "threshold": M0B_THRESHOLD}


def align_0c_backbone_to_checkpoint(model, checkpoint_keys):
    """Keep strict checkpoint loading across SigLIP wrapper naming variants.

    Original training checkpoint has backbone.embeddings.* keys.
    Some Transformers versions construct backbone.vision_model.embeddings.*.
    Only unwrap the redundant vision_model wrapper when this produces an
    EXACT match. No keys are discarded and no trained weights are changed.
    """
    expected = set(checkpoint_keys)
    existing = set(model.state_dict())

    if existing == expected:
        return "direct"

    if hasattr(model.backbone, "vision_model"):
        old_backbone = model.backbone
        model.backbone = old_backbone.vision_model
        if set(model.state_dict()) == expected:
            return "unwrapped vision_model (exact key match)"
        model.backbone = old_backbone

    missing = sorted(expected - set(model.state_dict()))
    unexpected = sorted(set(model.state_dict()) - expected)
    raise RuntimeError(
        "Model-0C architecture/checkpoint mismatch remains after safe "
        "compatibility check. Missing expected keys (first 5): "
        + repr(missing[:5])
        + "; unexpected model keys (first 5): "
        + repr(unexpected[:5])
        + ". Strict loading was NOT bypassed."
    )


class Model0C:
    """Loads original packaged model and ECDF once; same inference math as shipped script."""
    def __init__(self, device):
        import numpy as np
        import torch
        path = C_DIR / "MODEL0C_LOCAL_INFERENCE.py"
        for n in ("MODEL0C_FINAL_BEST.pt", "MODEL0C_MODEL_INFO.json", "MODEL0C_PORTABLE_ECDF.npz"):
            if not (C_DIR / n).is_file(): raise FileNotFoundError(C_DIR / n)
        spec = importlib.util.spec_from_file_location("packaged_model0c", path)
        if not spec or not spec.loader: raise RuntimeError("Can't import shipped Model0C inference")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module
        self.device, self.torch = device, torch
        info = read_json(C_DIR / "MODEL0C_MODEL_INFO.json")
        obj = torch.load(C_DIR / "MODEL0C_FINAL_BEST.pt", map_location="cpu", weights_only=False)
        # Patch the packaged architecture IN MEMORY (package files remain unchanged).
        # Also fixes the optional --crosscheck-c call to the packaged run() function.
        checkpoint_keys = frozenset(obj["model_state"].keys())
        shipped_model_class = module.Model0C

        class CheckpointCompatibleModel0C(shipped_model_class):
            def __init__(self):
                super().__init__()
                self.checkpoint_naming = align_0c_backbone_to_checkpoint(
                    self, checkpoint_keys
                )

        module.Model0C = CheckpointCompatibleModel0C
        self.model = module.Model0C().eval()
        self.model.load_state_dict(obj["model_state"], strict=True)
        print("[0C] Checkpoint architecture:", self.model.checkpoint_naming)
        self.model.to(device)
        del obj
        idx_to_crop = {int(v): str(k) for k, v in info["crop_to_idx"].items()}
        if len(idx_to_crop) != 15: raise RuntimeError("Model-0C should support 15 crops")
        self.idx_to_crop = idx_to_crop
        self.am_scale = float(info.get("am_scale", 30.0))
        self.threshold = float(info["ensemble"]["threshold"])
        with np.load(C_DIR / "MODEL0C_PORTABLE_ECDF.npz", allow_pickle=False) as z:
            self.softmax_ref = np.asarray(z["softmax_id_sorted"], dtype=np.float64)
            self.energy_ref = np.asarray(z["energy_id_sorted"], dtype=np.float64)
        if min(len(self.softmax_ref), len(self.energy_ref)) != 597:
            raise RuntimeError("ECDF reference should have 597 validation values")
        print(f"[0C] 15 crops, ECDF reference loaded, threshold={self.threshold:.9f}")

    def predict(self, image):
        import numpy as np
        from PIL import Image
        t = self.torch
        a = np.asarray(image.convert("RGB").resize((224, 224), Image.Resampling.BICUBIC),
                       dtype=np.uint8).copy()
        pix = t.from_numpy(a).permute(2, 0, 1).unsqueeze(0).float().div_(127.5).sub_(1).to(self.device)
        with t.inference_mode():
            embed = self.model.backbone(pixel_values=pix).pooler_output.float().cpu().numpy()
            weight = self.model.am_head.weight.detach().float().cpu().numpy()
        embed, weight = embed.astype(np.float64), weight.astype(np.float64)
        embed /= np.maximum(np.linalg.norm(embed, axis=-1, keepdims=True), 1e-12)
        weight /= np.maximum(np.linalg.norm(weight, axis=-1, keepdims=True), 1e-12)
        logits = self.am_scale * (embed @ weight.T)
        m = logits.max(axis=1)
        e = np.exp(logits - m[:, None])
        probs = (e / e.sum(axis=1, keepdims=True))[0]
        sm = float(probs.max())
        en = float((m + np.log(e.sum(axis=1)))[0])
        score = (0.84 * np.searchsorted(self.softmax_ref, sm, side="right") / len(self.softmax_ref)
                 + 0.16 * np.searchsorted(self.energy_ref, en, side="right") / len(self.energy_ref))
        best = int(probs.argmax())
        accepted = bool(score >= self.threshold)
        return {"accepted": accepted,
                "predicted_crop": self.idx_to_crop[best] if accepted else "UNKNOWN",
                "top_crop_guess": self.idx_to_crop[best],
                "crop_softmax": sm, "ensemble_score": float(score),
                "ensemble_threshold": self.threshold,
                "warning": "Unknown crops (especially Brassica relatives) may be falsely accepted"}

    def crosscheck_packaged_script(self, image_path):
        # Important: independent reference script loads model a second time, so optional.
        from PIL import Image, ImageOps
        with Image.open(image_path) as src:
            img = ImageOps.exif_transpose(src).convert("RGB")
        fast = self.predict(img)
        slow = self.module.run(str(image_path))
        if fast["accepted"] != slow["supported_crop"]:
            raise AssertionError(f"C accepted mismatch fast={fast} ref={slow}")
        if fast["top_crop_guess"] != slow["top_crop_guess"]:
            raise AssertionError(f"C crop mismatch fast={fast} ref={slow}")
        if abs(fast["ensemble_score"] - slow["ensemble_score"]) > 2e-5:
            raise AssertionError(f"C score mismatch fast={fast} ref={slow}")
        return True


class Downstream:
    def __init__(self, device):
        import torch
        import numpy as np
        import tensorflow as tf
        from transformers import SiglipVisionConfig, SiglipVisionModel, SiglipImageProcessor
        # Avoid TensorFlow reserving the entire GPU before PyTorch inference.
        try:
            for gpu in tf.config.list_physical_devices("GPU"):
                tf.config.experimental.set_memory_growth(gpu, True)
        except RuntimeError:
            pass
        for p in (M1_FILE, M2_FILE, M3_FILE):
            if not p.is_file(): raise FileNotFoundError(f"Missing downstream model: {p}")
        self.np, self.tf, self.torch, self.device = np, tf, torch, device
        self.m1 = tf.keras.models.load_model(M1_FILE, compile=False)
        self.m3 = tf.keras.models.load_model(M3_FILE, compile=False)
        self.m1_h, self.m1_w = (int(x) for x in self.m1.input_shape[1:3])
        self.m3_h, self.m3_w = (int(x) for x in self.m3.input_shape[1:3])
        def has_rescaling(obj):
            if not hasattr(obj, "layers"): return False
            return any(isinstance(layer, tf.keras.layers.Rescaling) or
                       (hasattr(layer, "layers") and has_rescaling(layer)) for layer in obj.layers)
        self.m3_has_rescaling = has_rescaling(self.m3)
        ck = torch.load(M2_FILE, map_location="cpu", weights_only=False)
        for key in ("model_state", "disease_to_idx", "crop_to_idx"):
            if key not in ck: raise RuntimeError("Model-2 missing key: " + key)
        disease_map, crop_map = ck["disease_to_idx"], ck["crop_to_idx"]
        if len(disease_map) != 54 or len(crop_map) != 15:
            raise RuntimeError("Model-2 expected 54 diseases / 15 crops")
        self.diseases = [name for name, ix in sorted(disease_map.items(), key=lambda kv: kv[1])]
        self.crops = [name for name, ix in sorted(crop_map.items(), key=lambda kv: kv[1])]
        cfg = SiglipVisionConfig(hidden_size=768, intermediate_size=3072,
            num_hidden_layers=12, num_attention_heads=12, num_channels=3,
            image_size=224, patch_size=16, hidden_act="gelu_pytorch_tanh",
            layer_norm_eps=1e-6, attention_dropout=0.0)
        class Model2(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = SiglipVisionModel(cfg).vision_model
                self.shared = torch.nn.Sequential(torch.nn.LayerNorm(768), torch.nn.Linear(768,512),
                                                  torch.nn.GELU(), torch.nn.Dropout(0.30))
                self.crop_head = torch.nn.Sequential(torch.nn.Linear(512,256),torch.nn.GELU(),
                                      torch.nn.Dropout(0.20),torch.nn.Linear(256,15))
                self.disease_head = torch.nn.Sequential(torch.nn.Linear(512,512),torch.nn.GELU(),
                                      torch.nn.Dropout(0.30),torch.nn.Linear(512,54))
            def forward(self, pixels):
                o = self.backbone(pixel_values=pixels)
                feat = o.pooler_output if o.pooler_output is not None else o.last_hidden_state.mean(dim=1)
                shared = self.shared(feat)
                return self.crop_head(shared), self.disease_head(shared)
        self.m2 = Model2()
        state = {k.removeprefix("module."): v for k, v in ck["model_state"].items()}
        self.m2.load_state_dict(state, strict=True)
        self.m2.to(device).eval()
        self.proc2 = SiglipImageProcessor(do_resize=True, size={"height":224,"width":224},
            resample=2, do_rescale=True, rescale_factor=1/255.,
            do_normalize=True, image_mean=[0.5,0.5,0.5], image_std=[0.5,0.5,0.5])
        print("[1-3] Original Model-1/2/3 loaded and strict Model-2 weights verified")

    def health(self, image):
        from PIL import Image
        a = self.np.asarray(image.resize((self.m1_w, self.m1_h), Image.Resampling.BILINEAR), dtype=self.np.float32)
        pred = self.np.asarray(self.m1.predict(a[None], verbose=0))
        if pred.shape == (1, 1): dp = float(pred[0, 0])
        elif pred.shape == (1, 2): dp = float(pred[0, 1])
        else: raise RuntimeError("Unsupported Model-1 output shape: " + str(pred.shape))
        return {"status": "DISEASED" if dp >= M1_THRESHOLD else "HEALTHY",
                "diseased_probability": dp, "healthy_probability": 1.0 - dp,
                "threshold": M1_THRESHOLD}

    def disease(self, image):
        pixels = self.proc2(images=image, return_tensors="pt")["pixel_values"].to(self.device)
        with self.torch.inference_mode():
            cp, dp = self.m2(pixels)
            cp = self.torch.softmax(cp, dim=-1)[0].cpu().numpy()
            dp = self.torch.softmax(dp, dim=-1)[0].cpu().numpy()
        top = self.np.argsort(-dp)[:3]
        def parts(idx):
            raw = self.diseases[int(idx)]
            if "___" in raw: c, d = raw.split("___", 1)
            elif "::" in raw: c, d = raw.split("::", 1)
            else: c, d = "", raw
            return {"raw_label": raw, "crop": pretty(c), "disease": pretty(d),
                    "confidence": float(dp[int(idx)])}
        pred = parts(top[0])
        pred["top3"] = [parts(x) for x in top]
        best_c = int(cp.argmax())
        pred["aux_crop"] = pretty(self.crops[best_c])
        pred["aux_crop_confidence"] = float(cp[best_c])
        return pred

    def segment(self, image):
        from PIL import Image
        a = self.np.asarray(image.resize((self.m3_w, self.m3_h), Image.Resampling.BILINEAR),
                            dtype=self.np.float32)
        if not self.m3_has_rescaling: a = a / 255.0
        pred = self.m3.predict(a[None], verbose=0)
        if isinstance(pred, list): pred = pred[0]
        prob = self.np.asarray(pred)[0]
        if prob.ndim == 3 and prob.shape[-1] in (1, 2):
            prob = prob[..., -1] if prob.shape[-1] == 2 else prob[..., 0]
        if prob.ndim != 2: raise RuntimeError("Unexpected Model-3 mask shape " + str(prob.shape))
        mask = prob >= M3_THRESHOLD
        affected = float(mask.mean() * 100)
        level = ("MILD" if affected <= SEVERITY_MILD_MAX else
                 "MODERATE" if affected <= SEVERITY_MODERATE_MAX else "SEVERE")
        return {"affected_percent": affected, "severity": level,
                "diseased_pixels": int(mask.sum()), "total_mask_pixels": int(mask.size),
                "probability_mask": prob, "binary_mask": mask,
                "input_rgb": a, "severity_note": "Percent of segmentation image pixels; leaf-area mask not applied"}



# ============================================================================
# USER SETTINGS - these folder paths already worked in your Windows Model-0 test
# ============================================================================
IMAGE_PATH = None   # None = Windows file picker; or r"E:\photos\leaf.jpg"
SAVE_DASHBOARD = False  # True -> save PNG for college demo/screenshot
SAVE_JSON_REPORT = False # True -> save readable JSON alongside image
SHOW_DASHBOARD = True
REPORT_DIR = Path(r"E:\Major Project\FINAL_PIPELINE_RESULTS")

# Do not add test-set labels to the actual prediction: inference sees ONLY RGB.
STAGE_DETAILS = {
    '0A': ('Image Quality Check', 'Rule-based image quality gate (provisional V3 computation)'),
    '0B': ('Is It a Usable Leaf?', 'Trained three-class SigLIP2 leaf validator'),
    '0C': ('Which Crop / Supported?', 'Trained 15-crop SigLIP2 AM-Softmax + calibrated ECDF gate'),
    '1': ('Healthy or Diseased?', 'Trained binary health status classifier'),
    '2': ('Which Disease?', 'Trained 54-disease classifier with auxiliary crop head'),
    '3': ('Where & How Severe?', 'Trained diseased-region segmentation with mask-based severity'),
}


def pick_one_image():
    if IMAGE_PATH is not None:
        chosen = Path(IMAGE_PATH)
        if not chosen.is_file():
            raise FileNotFoundError(f'Image not found: {chosen}')
        return chosen
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    try:
        window.attributes('-topmost', True)
        chosen = filedialog.askopenfilename(
            title='Major Project - Select ONE leaf image',
            filetypes=[('Image files', '*.jpg *.jpeg *.png *.bmp *.webp'),
                       ('All files', '*.*')])
    finally:
        window.destroy()
    return Path(chosen) if chosen else None


def run_full_pipeline(image, gate_a, gate_b, gate_c, downstream):
    """Strict sequential inference; never passes ground-truth/folder labels in."""
    report = {
        'decision': None,
        'message': None,
        'model0a': None, 'model0b': None, 'model0c': None,
        'model1': None, 'model2': None, 'model3': None,
        'crop_agreement': None,
    }

    print('\n[1/6] Model-0A: checking image quality...')
    report['model0a'] = gate_a.predict(image)
    if not report['model0a']['accepted']:
        report['decision'] = 'RETAKE_IMAGE'
        report['message'] = 'Image quality check failed. Please take a clearer photo.'
        return report

    print('[2/6] Model-0B: checking leaf usability...')
    report['model0b'] = gate_b.predict(image)
    if not report['model0b']['accepted']:
        report['decision'] = 'NOT_USABLE_LEAF'
        report['message'] = 'Usable leaf not verified. Try a clear single-leaf photograph.'
        return report

    print('[3/6] Model-0C: supported crop validation...')
    report['model0c'] = gate_c.predict(image)
    if not report['model0c']['accepted']:
        report['decision'] = 'CROP_NOT_VERIFIED'
        report['message'] = 'Crop not verified among the 15 supported crops. No disease diagnosis is shown.'
        return report

    print('[4/6] Model-1: healthy versus diseased...')
    report['model1'] = downstream.health(image)
    if report['model1']['status'] == 'HEALTHY':
        report['decision'] = 'HEALTHY'
        report['message'] = ('Leaf appears healthy according to Model-1. '
                             'Disease classification and segmentation are not needed.')
        return report

    print('[5/6] Model-2: predicting crop/disease + top three...')
    report['model2'] = downstream.disease(image)
    crop_0c = report['model0c']['predicted_crop']
    crop_2 = report['model2']['crop'] or report['model2']['aux_crop']
    same = normalized_crop(crop_0c) == normalized_crop(crop_2)
    report['crop_agreement'] = {
        'agree': same, 'model0c_crop': crop_0c, 'model2_crop': crop_2
    }
    if not same:
        print('      WARNING: Model-0C and Model-2 crop predictions disagree.')

    print('[6/6] Model-3: lesion mask, overlay and severity...')
    report['model3'] = downstream.segment(image)

    if same:
        report['decision'] = 'DISEASED_ANALYSIS_COMPLETE'
        report['message'] = 'Disease prediction and segmentation completed.'
    else:
        report['decision'] = 'REVIEW_CROP_DISAGREEMENT'
        report['message'] = ('The crop predicted by Model-0C differs from Model-2. '
                             'Disease label and severity are exploratory; review before relying on them.')
    return report


def concise_stage_summary(report):
    """Every stage has one explicitly reported PASS/REJECT/SKIPPED/REVIEW state."""
    stages = []
    a = report.get('model0a')
    b = report.get('model0b')
    c = report.get('model0c')
    h = report.get('model1')
    d = report.get('model2')
    s = report.get('model3')

    stages.append({'id':'0A', 'status':('PASS' if a['accepted'] else 'REJECT') if a else 'SKIPPED',
                   'detail': ('Clear enough (provisional check)' if a['accepted']
                              else 'Quality problem: ' + ', '.join(a.get('reasons', []))) if a else 'Not run'})
    stages.append({'id':'0B', 'status':('PASS' if b['accepted'] else 'REJECT') if b else 'SKIPPED',
                   'detail': (f"{pretty(b['predicted_class'])} | model confidence {b['confidence']:.1%}"
                              if b else 'Skipped because an earlier gate stopped the pipeline')})
    stages.append({'id':'0C', 'status':('PASS' if c['accepted'] else 'REJECT') if c else 'SKIPPED',
                   'detail': (f"Crop guess: {pretty(c['top_crop_guess'])} | ECDF score: "
                              f"{c['ensemble_score']:.4f} (threshold {c['ensemble_threshold']:.4f})"
                              if c else 'Skipped because an earlier gate stopped the pipeline')})
    stages.append({'id':'1', 'status':'PASS' if h else 'SKIPPED',
                   'detail': (f"{pretty(h['status'])} | healthy {h['healthy_probability']:.1%} / "
                              f"diseased {h['diseased_probability']:.1%}" if h else
                              'Skipped because an earlier gate stopped the pipeline')})
    stages.append({'id':'2', 'status':('REVIEW' if d and report['crop_agreement'] and
                                     not report['crop_agreement']['agree'] else 'PASS') if d else 'SKIPPED',
                   'detail': (f"{pretty(d['crop'] or d['aux_crop'])} - {d['disease']} "
                              f"| disease softmax {d['confidence']:.1%}" if d else
                              ('Healthy leaf: not needed' if h and h['status']=='HEALTHY' else
                               'Skipped because an earlier gate stopped the pipeline'))})
    stages.append({'id':'3', 'status':('REVIEW' if s and report['crop_agreement'] and
                                     not report['crop_agreement']['agree'] else 'PASS') if s else 'SKIPPED',
                   'detail': (f"Mask coverage {s['affected_percent']:.2f}% - "
                              f"{s['severity']} (whole mask canvas, not leaf-only area)" if s else
                              ('Healthy leaf: not needed' if h and h['status']=='HEALTHY' else
                               'Skipped because an earlier gate stopped the pipeline'))})
    return stages


def human_explanation(report):
    d = report['decision']
    if d == 'RETAKE_IMAGE':
        reasons = report['model0a'].get('reasons', [])
        return 'Retake the photo with good lighting and sharp focus. ' + (
            'Quality flags: ' + ', '.join(reasons) if reasons else 'Image did not meet quality requirements.')
    if d == 'NOT_USABLE_LEAF':
        return 'No usable leaf was confirmed. Photograph one visible leaf in focus.'
    if d == 'CROP_NOT_VERIFIED':
        return ('The image passed image/leaf checks but crop support was uncertain. '
                'The nearest crop label is only a guess; do not use it as an identification.')
    if d == 'HEALTHY':
        return ('No disease is predicted by the trained health classifier. '
                'A healthy prediction does not rule out every possible disease.')
    if d == 'REVIEW_CROP_DISAGREEMENT':
        return ('Crop models disagree: the disease is NOT verified. The shown mask and severity '
                'are an exploratory segmentation result, not a confirmed diagnosis.')
    return ('A diseased state was predicted; disease class and disease-region mask are shown. '
            'Percentages are model estimates, not a laboratory diagnosis.')


def print_readable_report(report, image_path):
    stages = concise_stage_summary(report)
    print('\n' + '=' * 90)
    print('                 COMPLETE PLANT LEAF ANALYSIS')
    print('=' * 90)
    print('IMAGE:', image_path.name)
    print('FINAL RESULT:', report['decision'].replace('_', ' '))
    print('EXPLANATION:', human_explanation(report))
    print('-' * 90)
    for x in stages:
        friendly, purpose = STAGE_DETAILS[x['id']]
        print(f"Model-{x['id']}: {friendly} [{x['status']}]")
        print('   ', x['detail'])
    if report['model2']:
        print('\nTOP-3 DISEASE PREDICTIONS:')
        for ix, item in enumerate(report['model2']['top3'], 1):
            print(f"   {ix}. {item['crop']} - {item['disease']}: {item['confidence']:.1%}")
    if report['model3']:
        m = report['model3']
        print(f"\nSEGMENTED REGION: {m['diseased_pixels']:,}/{m['total_mask_pixels']:,} "
              f"pixels = {m['affected_percent']:.2f}%, severity: {m['severity']}")
    print('\nIMPORTANT LIMITATIONS:')
    print(' - 0A quality calculation is provisional (exact original V3 code unavailable).')
    print(' - 0C ECDF score is NOT a confidence probability; OOD rejection is imperfect.')
    print(' - 3 severity uses all output pixels as denominator, NOT segmented leaf pixels.')
    print(' - Model-4 treatment recommendations have not been integrated.')
    print('=' * 90)
    return stages


def dashboard(image, report, image_name, save_to=None, show=True):
    """Readable standalone visual: status + what each model did + segmentation."""
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import FancyBboxPatch
    from textwrap import fill

    stages = concise_stage_summary(report)
    decision = report['decision']
    severity = report.get('model3')
    disease = report.get('model2')
    crop = report.get('model0c')
    health = report.get('model1')
    warning = (decision in ('REVIEW_CROP_DISAGREEMENT', 'CROP_NOT_VERIFIED',
                            'NOT_USABLE_LEAF', 'RETAKE_IMAGE'))
    tint = '#fff0df' if warning else ('#e8f4e8' if decision == 'HEALTHY' else '#e8f0ff')
    border = '#cc832f' if warning else ('#26865a' if decision == 'HEALTHY' else '#285bc1')

    fig = plt.figure(figsize=(17, 12.9), facecolor='#f7faf8')
    gs = GridSpec(5, 6, figure=fig, height_ratios=[0.72, 2.45, 0.68, 2.10, 1.00],
                  hspace=0.45, wspace=0.32, left=0.035, right=0.97,
                  top=0.97, bottom=0.035)

    def panel_text(ax, title, lines, face='#ffffff', edge='#dde7df', font=11.5):
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_facecolor(face)
        for spine in ax.spines.values():
            spine.set_visible(True); spine.set_edgecolor(edge); spine.set_linewidth(1.5)
        ax.text(0.035, 0.94, title, ha='left', va='top', fontsize=13.5,
                fontweight='bold', color='#183b2a', transform=ax.transAxes)
        body='\n\n'.join(lines)
        ax.text(0.035, 0.80, body, va='top', ha='left', fontsize=font,
                linespacing=1.35, color='#26392e', transform=ax.transAxes)

    header = fig.add_subplot(gs[0, :]); header.axis('off')
    header.add_patch(FancyBboxPatch((0, 0.05), 1, 0.91,
                     boxstyle='round,pad=0.01,rounding_size=0.025',
                     fc=tint, ec=border, lw=1.6, transform=header.transAxes))
    header.text(0.025, 0.68, 'PLANT LEAF ANALYSIS  |  ' + decision.replace('_',' '),
                va='center', ha='left', fontsize=18, weight='bold', color='#183b2a')
    header.text(0.025, 0.26, fill(human_explanation(report), width=115),
                va='center', ha='left', fontsize=11.0, color='#31483a')

    ax_img = fig.add_subplot(gs[1, 0:2]); ax_img.imshow(image)
    ax_img.set_title('Input photograph', fontweight='bold', fontsize=13)
    ax_img.axis('off')

    ax_mask = fig.add_subplot(gs[1, 2:4])
    if severity:
        prob = np.asarray(severity['probability_mask'])
        ax_mask.imshow(prob, cmap='magma', vmin=0, vmax=1)
        ax_mask.set_title('Model-3: Disease probability', fontweight='bold', fontsize=13)
    else:
        ax_mask.text(0.5, 0.5, 'Not required / Not run', ha='center', va='center',
                     fontsize=13, color='#62736a', transform=ax_mask.transAxes)
        ax_mask.set_title('Model-3: Probability map', fontsize=13, fontweight='bold')
    ax_mask.axis('off')

    ax_overlay = fig.add_subplot(gs[1, 4:6])
    if severity:
        binary = np.asarray(severity['binary_mask']).astype(bool)
        background = np.asarray(image.resize(
            (binary.shape[1], binary.shape[0])))
        ax_overlay.imshow(background)
        ax_overlay.imshow(np.ma.masked_where(~binary, binary), cmap='autumn',
                          alpha=0.58, vmin=0, vmax=1)
        ax_overlay.set_title('Model-3: Diseased-area overlay', fontsize=13, fontweight='bold')
    else:
        ax_overlay.text(0.5, 0.5, 'Not required / Not run', ha='center', va='center',
                        fontsize=13, color='#62736a', transform=ax_overlay.transAxes)
        ax_overlay.set_title('Model-3: Overlay', fontsize=13, fontweight='bold')
    ax_overlay.axis('off')

    mid = fig.add_subplot(gs[2, :]); mid.axis('off')
    mid.text(0.01, 0.55, 'MODEL-BY-MODEL EXPLANATION', fontsize=15,
             fontweight='bold', va='center', color='#20462e')

    # Six clear cards, each with a distinct status (no unlabeled blank stage).
    for ix, stage in enumerate(stages):
        row = ix // 3
        col = ix % 3
        sub = fig.add_subplot(gs[3, 2*col:2*col+2])
        # Nested vertical offsets via manually adjusted axes rectangles
        bbox = sub.get_position()
        new_height = bbox.height * 0.48
        new_y = bbox.y0 + (1-row)*bbox.height*0.51
        sub.set_position([bbox.x0, new_y, bbox.width, new_height])
        status = stage['status']
        boxcolor = {'PASS':'#f0f9f1','REJECT':'#fff0e9','REVIEW':'#fff6db',
                    'SKIPPED':'#f3f5f4'}[status]
        boxedge = {'PASS':'#8ac3a0','REJECT':'#db907f','REVIEW':'#d9bd65',
                   'SKIPPED':'#d7dbd8'}[status]
        label, description = STAGE_DETAILS[stage['id']]
        sub.set_facecolor(boxcolor)
        for spine in sub.spines.values():
            spine.set_visible(True); spine.set_edgecolor(boxedge)
        sub.set_xticks([]); sub.set_yticks([])
        sub.set_xlim(0, 1); sub.set_ylim(0, 1)
        sub.text(0.035, 0.87, f"MODEL-{stage['id']}  |  {label}",
                 ha='left', va='top', fontweight='bold', color='#193c2b', fontsize=11.6)
        sub.text(0.96, 0.87, status, va='top', ha='right', fontsize=10.5,
                 fontweight='bold', color=('#ad4d28' if status in ('REJECT','REVIEW') else '#22744a'))
        from textwrap import wrap
        wrapped='\n'.join(wrap(stage['detail'], width=49, break_long_words=False)[:3])
        sub.text(0.035, 0.56, wrapped, ha='left', va='top', fontsize=10.0, color='#34483a',
                 linespacing=1.30)

    footer = fig.add_subplot(gs[4,:]); footer.axis('off')
    cropname = pretty(crop['predicted_crop']) if crop and crop['accepted'] else 'Not verified'
    disname = disease['disease'] if disease else ('No disease predicted' if health and
                                                health['status']=='HEALTHY' else 'Not assessed')
    dislevel = f"{severity['affected_percent']:.1f}% / {severity['severity']}" if severity else 'Not assessed'
    footer.text(0.01, 0.96,
                f"CROP: {cropname}     |     DISEASE: {disname}     |     MASK COVERAGE: {dislevel}",
                va='top', ha='left', fontsize=12.5, fontweight='bold', color='#244d35')
    if disease:
        top3_text = 'TOP-3:  ' + '  |  '.join(
            f"{x['crop']} - {x['disease']} ({x['confidence']:.1%})" for x in disease['top3'])
    else:
        top3_text = 'TOP-3:  Not needed (healthy) or not assessed (earlier gate stopped).'
    footer.text(0.01, 0.70, fill(top3_text, width=140),
                va='top', ha='left', fontsize=9.9, color='#33483b')
    footer.text(0.01, 0.27,
                '0A provisional | 0C may accept unknown crops | severity % uses whole image canvas | Model-4 pending',
                va='top', ha='left', fontsize=9.5, color='#5c685f')
    footer.text(0.01, 0.07, f"Image: {image_name}", va='top', ha='left', fontsize=9.0, color='#777d78')

    if save_to is not None:
        fig.savefig(str(save_to), dpi=165, facecolor=fig.get_facecolor(), bbox_inches='tight')
        print('\nDashboard saved:', save_to)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig


def serializable(data):
    """Exclude arrays and avoid NaN/unknown numeric types in the optional report."""
    if isinstance(data, dict):
        return {k: serializable(v) for k, v in data.items()
                if k not in ('binary_mask','probability_mask','input_rgb')}
    if isinstance(data, (list,tuple)):
        return [serializable(x) for x in data]
    if isinstance(data, Path): return str(data)
    if isinstance(data, (str,int,float,bool)) or data is None: return data
    if hasattr(data,'item'): return serializable(data.item())
    return str(data)


def main():
    import torch
    from PIL import Image, ImageOps

    print('='*74)
    print('MAJOR PROJECT - FINAL HUMAN FRIENDLY SINGLE IMAGE PIPELINE')
    print('Model-0A -> 0B -> 0C -> Model-1 -> Model-2 -> Model-3')
    print('No ground truth labels, metadata or external dataset required')
    print('='*74)
    chosen = pick_one_image()
    if chosen is None:
        print('No image selected. Nothing modified.')
        return None
    with Image.open(chosen) as src:
        image = ImageOps.exif_transpose(src).convert('RGB')
    if min(image.size) < 8:
        raise ValueError('Input photograph dimensions are too small')
    print('Selected image:', chosen, '| dimensions:', image.size)

    # Check expected folders early, with actionable errors. No training/download.
    for name, folder in [('0A',A_DIR),('0B',B_DIR),('0C',C_DIR)]:
        if not folder.is_dir():
            raise FileNotFoundError(f'Model-{name} folder not found: {folder}')

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('PyTorch device:', device)
    print('Loading all saved checkpoints... (this may take time on CPU)')
    a, b, c = Model0A(), Model0B(device), Model0C(device)
    downstream = Downstream(device)
    print('All six components are ready.\n')

    result = run_full_pipeline(image, a, b, c, downstream)
    print_readable_report(result, chosen)

    output = REPORT_DIR / (chosen.stem[:65] + '_FINAL_DASHBOARD.png') if SAVE_DASHBOARD else None
    if SAVE_DASHBOARD or SAVE_JSON_REPORT:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dashboard(image, result, chosen.name, save_to=output, show=SHOW_DASHBOARD)
    if SAVE_JSON_REPORT:
        data_file = REPORT_DIR / (chosen.stem[:65] + '_FINAL_REPORT.json')
        data_file.write_text(json.dumps(serializable(result), indent=2, ensure_ascii=False),
                             encoding='utf-8')
        print('JSON report saved:', data_file)
    print('\nDONE. Original models, calibration and input photo were not modified.')
    if not SAVE_DASHBOARD and not SAVE_JSON_REPORT:
        print('Nothing was saved (toggle SAVE_DASHBOARD=True to save a demo PNG).')
    return result


if __name__ == '__main__':
    PIPELINE_RESULT = main()
