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

### 2. Start services

```bash
docker compose up --build
```

Starts PostgreSQL, Redis, FastAPI backend, Vite dev server, Celery worker, and Celery beat.

### 3. Run migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Create an admin user

```bash
docker compose exec backend python -m app.cli create-admin \
  --email admin@example.com \
  --phone +15551234567 \
  --password yourpassword
```

### 5. Open the app

| Service | URL |
|---------|-----|
| Admin frontend | http://localhost:3000 |
| API (Swagger docs) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |

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

### Build the embed bundle

```bash
cd embed && npm install && npm run build
# Output: embed/dist/powerline-embed.iife.js
```

The backend volume-mounts `embed/dist` at `/app/embed-dist` and serves it at `/static/`.

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
| `SECRET_KEY` | Yes | `openssl rand -hex 32` |
| `PUBLIC_BASE_URL` | Yes | Must be reachable by Twilio |
| `TWILIO_ACCOUNT_SID` | Yes | |
| `TWILIO_AUTH_TOKEN` | Yes | |
| `TWILIO_TWIML_APP_SID` | Yes | |
| `TWILIO_FROM_NUMBER` | Yes | |
| `TWILIO_API_KEY_SID` | Yes (WebRTC) | |
| `TWILIO_API_KEY_SECRET` | Yes (WebRTC) | |
| `CORS_ORIGINS` | Recommended | Set to your frontend domain in prod |
| `CLOUDINARY_*` | Optional | For audio file uploads |

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

# Lint / format Python
docker compose exec backend ruff check app/
docker compose exec backend ruff format app/

# Build embed widget
cd embed && npm install && npm run build
```

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
