# Powerline

A modern successor to [CallPower](https://github.com/spacedogXYZ/call-power).

Civic activism call campaign platform. Supporters click "Call Now" on an organization's website and get connected to their representatives through their browser via WebRTC. Phone callback and dial-in are secondary paths.

Licensed under AGPL-3.0.

## Architecture

```
Browser (WebRTC)  ──┐
                    ├──→ FastAPI Backend ──→ Twilio TwiML ──→ Target phones
Supporter phone ────┘        │
                             ├──→ PostgreSQL (campaigns, calls, sessions)
                             ├──→ Redis (call state, rate limiting, cache)
                             └──→ Celery (background tasks: Voice Insights)

Admin Frontend (React) ──→ API
Embed SDK (IIFE bundle) ──→ API (runs on org websites)
```

## Key Features

- **Campaigns** — create and manage call campaigns with custom audio, script prompts, and target lists
- **In-browser audio recording** — campaign audio slots support in-browser microphone recording (MediaRecorder + waveform visualizer), drag-and-drop file upload (MP3, WAV, WebM, M4A), and TTS; live campaign lock prevents audio changes without pausing
- **CSV bulk target import** — drag-and-drop CSV upload with column mapping, upsert semantics, partial success, and a downloadable error report for failed rows
- **Elected official rep lookup** — supporters enter their ZIP code to be connected to their federal or state representative; results cached via Redis with Google Civic + OpenStates APIs. `GET /api/v1/campaigns/{id}/reps` returns `{name, title, level, rep_token}` — the representative's phone number stays on the server and is dialed by exchanging `rep_token` at call time, so the browser can never choose the number
- **WebRTC calling** — supporters call from their browser; no phone app required
- **Embed widget** — drop a "Call Now" button on any website with a single `<script>` tag
- **Voice Insights** — Celery background task syncs Twilio call quality scores every 15 minutes

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Celery + Redis
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, shadcn/ui
- **Database:** PostgreSQL 16
- **Telephony:** Twilio (REST API, TwiML, Voice JS SDK 2.x, Lookup API, Voice Insights)
- **Audio:** Cloudinary (file storage), TTS fallback via Twilio

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A Twilio account (see [Twilio Setup Checklist](#twilio-setup-checklist) below)

### 1. Clone and configure

```bash
git clone <repo-url>
cd powerline-app
cp .env.example .env
# Edit .env with your credentials
```

### 2. Build the embed bundle

```bash
cd embed && npm ci && npm run build && cd ..
```

The dev stack bind-mounts `embed/dist` into the backend so edits to the widget only need a rebuild, not a container restart. The production image builds the bundle itself — this step is for local development only.

### 3. Start services

```bash
docker compose up --build
```

Starts PostgreSQL, Redis, FastAPI backend, Vite dev server, Celery worker, and Celery beat.

### 4. Run migrations

```bash
docker compose exec backend alembic upgrade head
```

### 5. Create an admin user

```bash
docker compose exec backend python -m app.cli create-admin \
  --email admin@example.com \
  --phone +15551234567 \
  --password yourpassword
```

### 6. Open the app

| Service | URL |
|---------|-----|
| Admin frontend | http://localhost:3000 |
| API (Swagger docs) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |

Caddy fronts the whole stack on port 80 and proxies `/api/*`, `/webhooks/*`, `/static/*`, `/docs*`, and `/openapi.json` to the backend; everything else goes to the frontend.

---

## Twilio Setup Checklist

Complete these steps in the [Twilio Console](https://console.twilio.com) before going live:

### Required

1. **Account credentials** — copy `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` from the Console dashboard.

2. **Phone number** — purchase a Twilio phone number. Set it as `TWILIO_FROM_NUMBER`. For STIR/SHAKEN trust, complete the Business Profile and Authorized Representative steps at **Phone Numbers → Manage → Trust Hub**.

3. **TwiML App** — create a TwiML App at **Voice → TwiML Apps → Create**.
   - Voice Request URL: `https://YOUR_DOMAIN/webhooks/twilio/voice-app` (HTTP POST)
   - Status Callback URL: `https://YOUR_DOMAIN/webhooks/twilio/status-callback` (HTTP POST)
   - Copy the App SID (starts with `AP`) → `TWILIO_TWIML_APP_SID`

4. **API Key** — create an API Key at **Account → API Keys & Tokens → Create API Key** (Standard type).
   - Copy the SID (starts with `SK`) → `TWILIO_API_KEY_SID`
   - Copy the Secret (shown once) → `TWILIO_API_KEY_SECRET`
   - This is separate from your Auth Token and is used only for WebRTC AccessToken generation.

5. **PUBLIC_BASE_URL** — set to your public-facing backend URL.
   - Development: use [ngrok](https://ngrok.com) — `ngrok http 8000` then set `PUBLIC_BASE_URL=https://abc.ngrok.io`
   - Production: your actual domain

### Optional

6. **Lookup API** — enable the Lookup add-on in **Marketplace** if you want line-type validation (`lookup_validate` + `lookup_require_mobile` campaign settings). Without it, phone validation still works but landline detection is disabled.

7. **Voice Insights** — automatically enabled on paid Twilio accounts. The Celery background task fetches call quality scores every 15 minutes for completed calls. No setup needed beyond having an active account.

8. **Cloudinary** (audio uploads) — if you want supporters to hear custom audio files instead of TTS, sign up at [cloudinary.com](https://cloudinary.com), copy the credentials to `.env`. If left empty, the system falls back to TTS for all audio slots.

---

## Embed Widget

Add a "Call Now" button to any webpage with a single script tag:

```html
<!-- Place this where you want the widget to appear -->
<div id="powerline-widget"></div>
<script
  src="https://YOUR_BACKEND_URL/static/powerline-embed.iife.js"
  data-campaign="YOUR_CAMPAIGN_ID"
  data-api-url="https://YOUR_BACKEND_URL"
></script>
```

### Script tag attributes

| Attribute | Required | Notes |
|-----------|----------|-------|
| `data-campaign` | Yes | Campaign UUID. Without it the widget does nothing. |
| `data-api-url` | Yes | Base URL of the Powerline backend. Missing it logs `[Powerline] data-api-url is required` and renders a configuration error instead of calling relative URLs. |
| `data-container` | Optional | `id` of the element to render into. Defaults to `powerline-widget`. |

The widget renders into `#powerline-widget` (or the element named by `data-container`) when that element is on the page, so you control where it appears. If no such element exists it appends its own `<div>` to the end of `<body>`.

### Build the embed bundle

```bash
cd embed && npm ci && npm run build
# Output: embed/dist/powerline-embed.iife.js
```

`Dockerfile.backend` runs this build in a Node stage and copies the result to `/app/embed-dist` in the API image, so production images ship the bundle. In development `docker compose` mounts `embed/dist` over that path for hot reload. Either way the backend serves it at `/static/` (set `EMBED_DIST_DIR` to serve it from elsewhere), and Caddy proxies `/static/*` through to the backend.

### React integration

```tsx
import { useEffect } from 'react';

export function PowerlineWidget({ campaignId }: { campaignId: string }) {
  useEffect(() => {
    const s = document.createElement('script');
    s.src = 'https://YOUR_BACKEND_URL/static/powerline-embed.iife.js';
    s.dataset.campaign = campaignId;
    s.dataset.apiUrl = 'https://YOUR_BACKEND_URL';
    document.body.appendChild(s);
    return () => { s.remove(); };
  }, [campaignId]);
  return <div id="powerline-widget" />;
}
```

---

## Production Deployment

### Environment variables to set

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Use `postgresql+asyncpg://` scheme |
| `REDIS_URL` | Yes | Used by Celery + call state |
| `ENVIRONMENT` | Yes | `production` (default) or `development`; `development` relaxes webhook signature checks only when `TWILIO_AUTH_TOKEN` is unset |
| `SECRET_KEY` | Yes | `openssl rand -hex 32` |
| `TRUSTED_PROXIES` | Recommended | Comma-separated IPs/CIDRs of your reverse proxies. `X-Forwarded-For` is ignored unless the peer is listed, so set it when running behind Caddy/ALB — otherwise every request is rate limited under the proxy's IP |
| `DEFAULT_RATE_LIMIT` | Optional | Calls per hour per phone/IP when a campaign has no `rate_limit` (default 5) |
| `REPS_RATE_LIMIT` | Optional | Rep lookups per hour per client IP (default 20); the per-campaign ceiling is 25× this |
| `AUTH_RATE_LIMIT` | Optional | Login / password-reset attempts per hour per identifier (default 10) |
| `PUBLIC_BASE_URL` | Yes | Must be reachable by Twilio |
| `TWILIO_ACCOUNT_SID` | Yes | |
| `TWILIO_AUTH_TOKEN` | Yes | |
| `TWILIO_TWIML_APP_SID` | Yes | |
| `TWILIO_FROM_NUMBER` | Yes | |
| `TWILIO_API_KEY_SID` | Yes (WebRTC) | |
| `TWILIO_API_KEY_SECRET` | Yes (WebRTC) | |
| `CORS_ORIGINS` | Recommended | Set to your frontend domain in prod |
| `CLOUDINARY_*` | Optional | For audio file uploads |
| `GOOGLE_CIVIC_API_KEY` | Optional | Federal rep lookup (Senate & House); leave empty to disable |
| `OPENSTATES_API_KEY` | Optional | State legislator lookup; leave empty to disable |
| `EMBED_DIST_DIR` | Optional | Directory served at `/static/` (default `/app/embed-dist`) |

### Public call endpoints

`POST /api/v1/calls/create` and `POST /api/v1/tokens/voice` are unauthenticated. Both accept only
`campaign_id`, an optional `rep_token`, and (for the callback path) `phone_number` and
`referral_code`; the number to dial is always resolved server-side. Before any Twilio spend they
apply, in order: the blocklist (phone hash and client IP), the per-caller and per-IP hourly rate
limits, and the campaign's `call_maximum` ceiling. Set `TRUSTED_PROXIES` so those limits key on the
real client IP.

### CORS

For the admin frontend, restrict CORS to your domain:
```
CORS_ORIGINS=https://admin.example.com
```

For the embed widget, the API must accept requests from any origin (`*`). If you run separate API instances (one for admin, one for the public embed API), you can set stricter CORS on the admin instance.

---

## Development

```bash
# Backend hot reload
docker compose up backend

# Frontend dev server (outside Docker)
cd frontend && npm install && npm run dev

# Run backend tests
docker compose exec backend python -m pytest tests/ -v

# Run a specific test file
docker compose exec backend python -m pytest tests/test_campaigns.py -v

# Run frontend tests
cd frontend && npm test

# Frontend tests in watch mode
cd frontend && npm run test:watch

# Lint / format Python
docker compose exec backend ruff check app/
docker compose exec backend ruff format app/

# Build embed widget
cd embed && npm ci && npm run build

# Run embed widget tests
cd embed && npm test
```

See [frontend/TESTING.md](frontend/TESTING.md) for the frontend test philosophy and conventions.

### Celery

```bash
# Check worker is running
docker compose logs celery-worker

# Check beat scheduler
docker compose logs celery-beat

# Trigger Voice Insights task manually (for testing)
docker compose exec celery-worker celery -A app.celery_app call app.tasks.insights.fetch_voice_insights
```

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).
