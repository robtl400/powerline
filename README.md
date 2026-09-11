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

Starts PostgreSQL, Redis, FastAPI backend, Vite dev server, Celery worker, and Celery beat. A
one-shot `migrate` service runs `alembic upgrade head` first; the backend and Celery containers
wait for it to finish, so `up` leaves the schema current.

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
| App (through Caddy) | http://localhost |
| Vite dev server | http://localhost:3000 |
| API (Swagger docs) | http://localhost/docs |
| Health check | http://localhost/api/v1/health |

Caddy fronts the whole stack on port 80 and proxies `/api/*`, `/webhooks/*`, `/static/*`, `/docs*`, and `/openapi.json` to the backend; everything else goes to the frontend. The backend does not publish a host port of its own — reach it through Caddy, or run commands inside the container with `docker compose exec backend ...`.

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

5. **PUBLIC_BASE_URL** — set to your public-facing backend URL: scheme and host only, no path.
   - Development: use [ngrok](https://ngrok.com) — `ngrok http 8000` then set `PUBLIC_BASE_URL=https://abc.ngrok.io`
   - Production: your actual domain
   - The webhook URLs handed to Twilio are root-absolute, so a path prefix (`https://example.com/powerline`)
     is dropped from the callback and from the URL each signature is reconstructed over. Production startup
     refuses a value that carries one.

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
# Output: embed/dist/powerline-embed.iife.js (the widget) and
#         embed/dist/powerline-embed-webrtc.iife.js (the Twilio Voice SDK,
#         fetched by the widget only when a browser call starts)
```

`Dockerfile.backend` runs this build in a Node stage and copies the result to `/app/embed-dist` in the API image, so production images ship the bundle. In development `docker compose` mounts `embed/dist` over that path for hot reload. Either way the backend serves it at `/static/` (set `EMBED_DIST_DIR` to serve it from elsewhere), and Caddy proxies `/static/*` through to the backend. Because the bundle lives at one fixed URL, `/static/` responses carry `Cache-Control: public, max-age=300, must-revalidate` — embedding sites pick up a new bundle within five minutes.

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

`docker-compose.prod.yml` is a standalone stack: Postgres, Redis, a one-shot database migration, the
API, a Celery worker and beat, a one-shot frontend build, and Caddy terminating TLS. Only Caddy
publishes ports.

### 1. Point a domain at the host

`DOMAIN` must already resolve to the machine — Caddy requests a certificate on first boot and
Let's Encrypt validates over ports 80 and 443, so open both.

### 2. Fill in the environment

```bash
cp .env.example .env
```

Set at minimum:

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `production` |
| `DOMAIN` | the hostname Caddy serves |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `PHONE_HASH_PEPPER` | `openssl rand -hex 32` — set it before the first call |
| `POSTGRES_PASSWORD` | a generated password |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:PASSWORD@postgres:5432/powerline` |
| `REDIS_PASSWORD` | a generated password |
| `REDIS_URL` | `redis://redis:6379/0` |
| `PUBLIC_BASE_URL` | `https://DOMAIN` |
| `ADMIN_CORS_ORIGINS` | `https://DOMAIN` (or empty for same-origin only) |
| `TRUSTED_PROXIES` | the Docker subnet Caddy runs on — see step 3 |
| `TWILIO_*` | real credentials — startup refuses to run without them |

### 3. Set TRUSTED_PROXIES

Every rate limit keys on the client IP, which arrives via `X-Forwarded-For` from Caddy. That header
is ignored unless the peer is listed in `TRUSTED_PROXIES`, and the API refuses to start in
production without it — otherwise the whole internet shares one rate-limit bucket under Caddy's
address. Compose networks come out of Docker's default `172.16.0.0/12` pool, which is a safe value
here; to pin the exact subnet, create the network first and read it back:

```bash
docker compose -f docker-compose.prod.yml up -d postgres
docker network inspect powerline_default -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
# put that CIDR in .env as TRUSTED_PROXIES
```

### 4. Build and start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The one-shot `migrate` service runs `alembic upgrade head` before the API and Celery containers
start, so there is no separate migration step.

### 5. Create the first admin

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.cli create-admin \
  --email admin@example.com \
  --phone +15551234567 \
  --password 'a-strong-password'
```

### 6. Point Twilio at the domain

Set the TwiML App's Voice Request URL to `https://DOMAIN/webhooks/twilio/voice-app` and the Status
Callback to `https://DOMAIN/webhooks/twilio/status-callback`.

### 7. Verify

```bash
curl https://DOMAIN/api/v1/health
```

Then sign in at `https://DOMAIN`. Interactive docs are off in production unless `DOCS_ENABLED=true`.

### Redeploying

`docker compose -f docker-compose.prod.yml up -d --build` rebuilds and restarts. Two one-shot
containers run as part of it: `migrate` applies `alembic upgrade head` before the API and Celery
containers start, and the frontend build republishes `/srv` into the volume Caddy serves, so a
frontend change needs no Caddy restart.

### Migration runbook

`migrate` gates the release: the API and Celery containers do not start until `alembic upgrade
head` exits cleanly, so a failed migration leaves the previous release running. The migration holds
a session-level Postgres advisory lock, so a second runner — a retried deploy, a second host —
blocks until the first finishes instead of racing it.

Two revisions need planning:

- **007** takes `ACCESS EXCLUSIVE` on `audio_recordings`, `campaigns`, `users` and `phone_numbers`
  for the length of a full table scan each. Size the maintenance window to those row counts. Its
  other indexes are built `CONCURRENTLY` and do not block writes.
- **009** drops `call_sessions.from_number` and `campaigns.allow_call_in`. The data is gone and the
  downgrade restores only empty columns. **Take a backup before this release.**

If a run dies half-applied:

```bash
docker compose -f docker-compose.prod.yml run --rm migrate alembic current
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid"
```

`alembic current` names the last revision that committed — each revision runs in its own
transaction, so anything it does not name was not applied. A `CONCURRENTLY` build that was
interrupted leaves an `INVALID` index behind, which the query above lists; the migrations drop such
an index before rebuilding it, so re-running `migrate` is enough:

```bash
docker compose -f docker-compose.prod.yml up -d migrate
```

An index the query lists that no longer belongs to any revision can be dropped by hand with
`DROP INDEX CONCURRENTLY <name>`.

### Rotating PHONE_HASH_PEPPER

Phone numbers are stored only as digests taken under `PHONE_HASH_PEPPER`, so changing the pepper
makes every blocklist entry and call-session hash already written unmatchable. The first start
records `sha256(PHONE_HASH_PEPPER)[:16]` in Redis under `phone_hash_pepper_fp`; a later start whose
pepper does not match that fingerprint fails in production and logs a warning in development. A
Redis that is unreachable or wiped skips the check rather than blocking the boot — the fingerprint
is written again on the next start.

To change the pepper deliberately: rebuild or discard the digests that were written under the old
one (blocklist entries have to be re-added from the phone numbers themselves), then clear the key
and start with the new value.

```bash
docker compose -f docker-compose.prod.yml exec redis \
  sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli del phone_hash_pepper_fp'
```

### Environment variables to set

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Use `postgresql+asyncpg://` scheme |
| `REDIS_URL` | Yes | Used by Celery + call state |
| `REDIS_PASSWORD` | Yes (prod) | The prod Redis container writes it into a config file at start and reads it back with `requirepass`, so it never appears in the process table or in `docker inspect`'s command; the healthcheck passes it to `redis-cli` through `REDISCLI_AUTH`. The app and Celery both append it to `REDIS_URL` unless that URL already carries credentials |
| `REDIS_MAXMEMORY` | Optional | Memory ceiling for the prod Redis container (default `256mb`). Eviction is off, so at the cap Redis rejects writes with an OOM error rather than dropping call state or rate-limit counters |
| `TIMEZONE` | Optional | IANA zone used for dashboard/analytics day boundaries (default `UTC`); an unknown name refuses to start |
| `DOMAIN` | Yes (prod) | Hostname Caddy serves and gets a certificate for |
| `POSTGRES_PASSWORD` | Yes (prod) | Password for the bundled Postgres container |
| `ENVIRONMENT` | Yes | `production` (default) or `development`; `development` relaxes webhook signature checks only when `TWILIO_AUTH_TOKEN` is unset |
| `SECRET_KEY` | Yes | `openssl rand -hex 32` |
| `PHONE_HASH_PEPPER` | Recommended | `openssl rand -hex 32`, mixed into every phone-number digest. Numbers are stored only as digests, so a pepper is what stops a stolen database being walked back to phone numbers by hashing the ten-digit space. Set it before the first production call: changing it later invalidates every digest already stored, so existing blocklist entries stop blocking and existing session hashes stop matching their numbers. Startup records a fingerprint of it in Redis (`phone_hash_pepper_fp`) and refuses to boot in production if the pepper no longer matches — see [Rotating PHONE_HASH_PEPPER](#rotating-phone_hash_pepper). Empty means plain SHA-256 |
| `TRUSTED_PROXIES` | Yes (prod) | Comma-separated IPs/CIDRs of your reverse proxies. `X-Forwarded-For` is ignored unless the peer is listed, so every request would be rate limited under the proxy's IP; production startup fails unless at least one entry parses |
| `RESET_CODE_TTL_SECONDS` | Optional | Lifetime of a password-reset code (default 600) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | Access-token lifetime (default 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Optional | Refresh-token lifetime (default 7) |
| `DEFAULT_RATE_LIMIT` | Optional | Calls per hour per phone/IP when a campaign has no `rate_limit` (default 5) |
| `REPS_RATE_LIMIT` | Optional | Rep lookups per hour per client IP, governing `/campaigns/{id}/reps` only (default 20); the per-campaign ceiling is 25x this |
| `PUBLIC_RATE_LIMIT` | Optional | Embed bootstrap requests per hour per client IP, shared by `/campaigns/{id}/public` and `/campaigns/{id}/count` (default 600). The widget calls both once per page load, so this is one IP's page-view budget — raise it for the shared gateways many supporters sit behind |
| `AUTH_RATE_LIMIT` | Optional | Login / password-reset attempts per hour per identifier (default 10) |
| `TOKEN_RATE_LIMIT` | Optional | WebRTC access tokens per hour per client IP (default 5) |
| `TOKEN_CAMPAIGN_RATE_LIMIT` | Optional | WebRTC access tokens per hour per campaign (default 500) |
| `DOCS_ENABLED` | Optional | Forces `/docs`, `/redoc`, `/openapi.json` on or off; unset means on in development, off in production |
| `PUBLIC_BASE_URL` | Yes | Must be reachable by Twilio, and must carry no path — scheme and host only. Webhook URLs are root-absolute, so a prefix is dropped from both the callback and the signature check; production startup rejects one |
| `TWILIO_ACCOUNT_SID` | Yes | |
| `TWILIO_AUTH_TOKEN` | Yes | |
| `TWILIO_TWIML_APP_SID` | Yes | |
| `TWILIO_FROM_NUMBER` | Yes | |
| `TWILIO_API_KEY_SID` | Yes (WebRTC) | |
| `TWILIO_API_KEY_SECRET` | Yes (WebRTC) | |
| `CORS_ORIGINS` | Recommended | Public embed API only; `*` is expected because the widget runs on third-party sites |
| `ADMIN_CORS_ORIGINS` | Recommended | Admin API only; empty means same-origin, which is right when Caddy serves the dashboard and API on one domain |
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

### Sessions and tokens

`POST /auth/login` returns an access token and a refresh token. Refresh tokens are single-use:
`POST /auth/refresh` consumes the one it is given and returns a **new** access *and* refresh token,
so a client must store both from every refresh response. Replaying a spent refresh token is a 401.

`POST /auth/logout` takes `{"refresh_token": "..."}` and retires that token. It always answers 204,
including for tokens that are expired, malformed, or already gone.

Deactivating a user, changing their role, or completing a password reset ends every session that
user holds — outstanding access tokens stop working immediately rather than lasting out their
expiry.

### CORS

The two surfaces get different policies, split by path:

- **Public embed endpoints** (`/api/v1/campaigns/{id}/public`, `/count`, `/reps`,
  `/api/v1/calls/create`, `/api/v1/tokens/voice`, `/static/*`) use `CORS_ORIGINS`, normally `*` —
  the widget runs on sites you do not control.
- **Everything else** is admin surface and uses `ADMIN_CORS_ORIGINS`. Empty means no CORS headers
  at all, which is the correct setting when Caddy serves the dashboard and the API on one domain.

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

# Trigger the rep-target cleanup manually
docker compose exec celery-worker celery -A app.celery_app call app.tasks.cleanup.cleanup_rep_targets
```

Both tasks take a Redis lock (`lock:voice_insights`, `lock:cleanup_rep_targets`) so a run that
overruns its schedule is skipped rather than doubled. The lock and query logic is covered by
`tests/test_tasks.py`; the task bodies need a live Twilio account and are verified by running the
two commands above and reading `docker compose logs celery-worker`.

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).
