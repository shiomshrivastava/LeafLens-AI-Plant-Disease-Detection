# LeafLens 🌿
### AI-Powered Multi-Crop Plant Leaf Disease Detection, Segmentation & IoT Monitoring

**LeafLens** is a major-project application for analyzing plant leaf images, identifying possible diseases, visualizing affected areas, estimating disease severity, and providing practical plant-care guidance. It combines a React web app, a multi-stage local AI pipeline, Supabase authentication and storage, a FastAPI backend, and live ESP32 + DHT11 environmental monitoring.

**Official academic project title:** Real-Time Multi-Crop Plant Leaf Disease Segmentation and Severity Estimation.

> **Live project:** This is a working web application, not a UI-only prototype. AI inference currently uses a **private worker running on a laptop**, while the deployed website, cloud API, authentication, saved history, and cloud IoT ingestion are hosted services.

## 🔗 Project Links

| Resource | Link |
| --- | --- |
| 🌐 **Live LeafLens Web App** | **[Open LeafLens](https://leaf-lens-ai-plant-disease-detectio.vercel.app/)** |
| 🩺 Cloud API health check | [Render FastAPI — /api/health](https://leaflens-cloud-api.onrender.com/api/health) |
| 💻 GitHub repository | [LeafLens source code](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection) |
| ☁️ Integrated local + hybrid cloud source | [`main` branch](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/tree/main) |
| 🔀 Hybrid deployment changes | [Pull request #2](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/pull/2) |
| 🌡️ IoT cloud ingest implementation | [Supabase Edge Function source](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/blob/main/supabase/functions/leaflens-iot-ingest/index.ts) |
| 🗄️ IoT database migration | [Supabase SQL migration](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/blob/main/supabase/migrations/20261011_leaflens_iot_latest.sql) |

**Access:** A Supabase account/sign-in is required to use the authenticated dashboard. On a sleeping Render free instance, the first API request may take longer than subsequent requests.

## ✨ Main Features

- **Secure accounts and profiles:** Supabase email/password signup and login, password recovery, display-name editing, and private profile photos.
- **Real image input:** Upload or drag-and-drop a JPEG, PNG, or WebP leaf photo (up to 10 MB), or capture one with the browser camera.
- **Image and leaf validation:** Quality checks, usable-leaf detection, and supported-crop screening before disease analysis.
- **Plant health and disease analysis:** Healthy/diseased classification followed, when appropriate, by crop/disease identification for **15 supported crops** and **54 Model-2 output classes**; show prediction confidence and warnings where uncertain.
- **Disease segmentation and severity:** Predicted lesion mask, colored overlay, image-area coverage estimate, and mild/moderate/severe severity bands.
- **Interactive visual comparison:** Drag the before/after image divider and adjust overlay opacity.
- **Plant-care recommendations:** Rule-based, disease- and severity-aware guidance in English and Hindi; uncertain predictions receive precautionary advice.
- **Personal analysis history:** Supabase-backed, user-private latest **10** saved analyses, including individual deletion, clear-all, and automatic removal of older records.
- **PDF reports:** Download A4 analysis reports with interpretation, recommendations, and available image evidence.
- **Supported crop library:** Search the **15 supported crops** in English/Hindi and see leaf-photo tips.
- **Weather + IoT dashboard:** ESP32/DHT11 temperature and humidity in local or cloud mode, sensor online/offline status, and location-based Open-Meteo forecasts and advisories.
- **English / Hindi interface:** Language switching across the main web workspace and admin pages.
- **Admin workspace:** Server-verified role-based dashboard with aggregate statistics, account restrictions, moderation cases, action logs, and privacy-conscious user listing.

## 🧠 AI Analysis Pipeline

The inference workflow runs in stages and may stop early when an image does not pass validation.

| Stage | Purpose |
| --- | --- |
| **Model 0A** | Image quality gate (documented, threshold-based checks) |
| **Model 0B** | Leaf usability / input validation |
| **Model 0C** | Crop identification and out-of-distribution checks |
| **Model 1** | Healthy vs. diseased classification |
| **Model 2** | Disease identification |
| **Model 3** | Pixel-level disease-region segmentation and severity estimation |
| **Recommendation layer (Model 4)** | Rule-based plant-care guidance; **not** an additional trained model |

**Important interpretation notes:** The displayed severity is derived from the segmentation mask and its image-area coverage; it is **not** a lab-confirmed diagnosis or a guaranteed percentage of leaf tissue damaged. The quality-gate reproduction has documented limitations, and an accepted crop prediction is not a guarantee that the crop is supported. Predictions and care tips should be reviewed for real agricultural decisions.

Trained checkpoints and large datasets are **not stored in this public Git repository**. Actual AI inference requires the matching private model assets and a correctly configured Python environment.

## 🏗️ Deployment Architecture

```text
                    USER / BROWSER
                          |
                 React + Vite website
                         Vercel
                          |
                    FastAPI cloud API
                         Render
                    /             \
                   /               \
       Auth, history, admin        AI analysis
                 |                     |
              Supabase          Private HTTPS tunnel
                                     |
                                Laptop AI worker
                              (trained checkpoints)

       ESP32 + DHT11 sensor
               |
       HTTPS + device-specific key
               |
       Supabase Edge Function
               |
       Supabase latest IoT reading
               |
       Render GET /api/iot/current
               |
       LeafLens live dashboard
```

- **Frontend:** React 18, TypeScript, Vite, Lucide icons, jsPDF.
- **Backend:** Python, FastAPI, Uvicorn, Pillow, HTTPX.
- **Inference:** Local trained deep-learning pipeline (with model-specific ML frameworks).
- **Authentication and data:** Supabase Auth, Postgres, private Storage, Row Level Security where applicable.
- **Cloud hosting:** Vercel (frontend) + Render (API).
- **Private AI inference:** Authenticated laptop worker, connected through an HTTPS Tailscale Funnel.
- **IoT:** NodeMCU-32S ESP32, DHT11, Arduino firmware, Supabase Edge Functions.
- **Weather:** Open-Meteo API.

### Availability and privacy notes

- **AI analysis requires the laptop AI worker to be online and reachable.** A running Render API alone does not mean the trained models are available.
- **Live cloud IoT does not require the laptop.** The ESP32 needs power, Wi-Fi, and internet access; readings pass through Supabase to the website. The dashboard marks stale readings offline.
- The **sensor dashboard displays one shared demonstration device**, not a multi-user private device fleet.
- Production credentials, worker tokens, ESP32 device secrets, model weights, and private data must **never** be committed to GitHub or placed in browser `VITE_` environment variables.

## 🚀 Run the Web App Locally

### Requirements

- Node.js and npm
- Python 3.11 (recommended for the backend)
- Supabase project configured for authentication and saved analyses
- The correct local trained AI assets, for real inference
- Optional: ESP32 + DHT11 hardware for local IoT monitoring

### 1. Clone and configure the frontend

```powershell
git clone https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection.git
cd LeafLens-AI-Plant-Disease-Detection
Copy-Item .env.example .env.local
```

In `.env.local`, configure your Supabase URL and **publishable** key:

```dotenv
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_SUPABASE_PUBLISHABLE_KEY
VITE_AI_API_URL=http://127.0.0.1:8000
```

Then start the frontend:

```powershell
npm ci
npm run dev
```

Open **http://127.0.0.1:5173/**.

### 2. Configure the local FastAPI backend

```powershell
cd backend
Copy-Item .env.example .env
python -m pip install -r requirements-api.txt
```

Set the backend-only values in `backend/.env`: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Keep the service-role/secret key **server-side only**.

The API requirements cover the lightweight web/API components. **Full local inference also needs the ML framework dependencies and compatible trained checkpoints** under `backend/model_assets/`; these are intentionally excluded from the repository.

After configuring the environment and model assets, start the local API **with LAN discovery** (recommended for ESP32 local mode):

```powershell
python run_with_discovery.py
```

This runs FastAPI on port `8000` and starts UDP discovery on port `42177` so a same-LAN ESP32 can find the laptop. For **local IoT mode**, configure `LEAFLENS_IOT_KEY` in `backend/.env` to match the private ESP32 device key; use `LEAFLENS_MODE 1` in the private firmware and keep the laptop and ESP32 on the same LAN. The sensor does not need internet in this mode. Do not commit Wi-Fi credentials or device keys.

If LAN discovery is not needed, the original API-only command remains valid:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Check the local API at **http://127.0.0.1:8000/api/health**. The health endpoint exposes configuration and model readiness details; simply receiving HTTP 200 does not prove that weights have loaded successfully.

### 3. Cloud / hybrid deployment

The **[`main` branch](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/tree/main)** contains the integrated local FastAPI backend, hybrid cloud API, secure laptop AI worker, and ESP32 cloud IoT implementation. These changes were merged through [Pull Request #2](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/pull/2) on **11 October 2026**. No feature-branch switch is required.

Cloud mode sets `LEAFLENS_BACKEND_MODE=cloud` on Render. Render securely proxies analysis to a private AI worker, which can be started on the laptop with:

```powershell
cd backend
python -m uvicorn ai_worker:app --host 127.0.0.1 --port 8001
```

The cloud backend and laptop worker use the same private `LEAFLENS_AI_WORKER_TOKEN`. The HTTPS tunnel and its access configuration must be set up separately; **do not publicly expose the original admin/backend service on port 8000**. See [`backend/.env.example` on main](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/blob/main/backend/.env.example).

For cloud IoT ingestion, use the [Edge Function source](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/blob/main/supabase/functions/leaflens-iot-ingest/index.ts) and [database migration](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/blob/main/supabase/migrations/20261011_leaflens_iot_latest.sql). The Edge Function authenticates the ESP32 using `X-Device-Key`; keep this token private. The firmware supports **local laptop discovery** and **cloud HTTPS sending** as separate modes.

## 🧪 Testing

The repository includes a GitHub Actions workflow with a frontend TypeScript/Vite build and offline backend tests:

```powershell
npm run build

cd backend
python -m pip install -r requirements-api.txt pytest
python -m pytest -q tests
```

These checks do **not** replace real-model accuracy evaluation, a running laptop-worker test, or an on-device ESP32 test.

## 📌 Project Status

**Current implementation:** The React web application, multi-stage AI analysis, private Supabase history/admin features, hybrid inference, and ESP32/DHT11 **local and cloud modes** have been implemented and tested in previous demonstrations. [GitHub Actions CI](https://github.com/shiomshrivastava/LeafLens-AI-Plant-Disease-Detection/actions) builds the frontend and runs offline backend tests; the **11 October 2026 `main` merge commit passed CI**. These observations are not a guarantee that the laptop worker, live sensor, or all hosted services are online at any given moment.

**Scope:** This is a web application, **not** a separately packaged native Android/iOS app. The public repository excludes private model weights, device firmware secrets, and trained datasets.

Built as an academic **Major Project** focused on multi-crop plant health analysis, explainable visual results, and practical environmental monitoring.

---

**LeafLens — Healthier plants, brighter tomorrows. 🌱**
