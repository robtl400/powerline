# Changelog

All notable changes to this project will be documented in this file.

## [2.0.4.0] - 2026-09-10

### Security
- **Password reset codes** — 8-digit codes generated with `secrets`, compared with `hmac.compare_digest`, and destroyed after 5 wrong attempts. A pending code is reused until it expires, so repeated requests cannot flood a phone with SMS.
- **Password reset rate limits** — per-email (`AUTH_RATE_LIMIT // 3`, minimum 3) and per-IP limits on `POST /auth/reset-request`, applied before the account lookup so unknown emails cost the same; per-IP limit on `POST /auth/reset-confirm`. Reset failures no longer log the email address, only a truncated hash.
- **Login hardening** — per-IP (`AUTH_RATE_LIMIT * 3`) and per-email (`AUTH_RATE_LIMIT`) rate limits, plus a dummy bcrypt verification for unknown emails so response timing no longer reveals whether an account exists.
- **Refresh re-checks the account** — `POST /auth/refresh` loads the user named by the token and returns 401 when they no longer exist or have been deactivated.
- **Password policy** — new passwords must be 12–128 characters and contain a letter and a digit, enforced on password reset and on admin-supplied passwords at user creation.
- **User role and phone validation** — `role` is restricted to `admin` / `staff`, and `phone` is normalized to E.164 on create and update so invites reach a real number.
- **Last-admin guard** — deactivating or demoting the only remaining active admin returns HTTP 409.
- **Long passwords no longer error** — passwords are truncated to bcrypt's 72-byte limit before hashing and verification, so a login or reset with a longer password returns a normal result instead of a 500.
- **Consistent email handling** — login and password reset match accounts case-insensitively and new accounts are stored lowercased, so a rate-limit key can no longer diverge from the account it protects.
- **SMS off the event loop** — Twilio's blocking client now runs in a thread pool for reset and invite messages.
- **Rep selection handles replace client-supplied dial targets** — `GET /campaigns/{id}/reps` returns `{name, title, level, rep_token}` with no phone number. `rep_token` is an opaque `secrets.token_urlsafe(24)` handle stored in Redis for one hour under `rep_token:{token}`, bound to the campaign it was issued for and exchanged server-side at call time. `target_phone_override`, `target_rep_name` and `target_rep_title` are gone from `CallCreateRequest` and `VoiceTokenRequest`, so a caller can no longer make the platform dial an arbitrary number under the campaign's caller ID.
- **Unknown, expired, or cross-campaign `rep_token`** — HTTP 422 "Invalid or expired representative selection" instead of a fallback to a caller-chosen target.
- **Phone numbers canonicalised before use** — `CallCreateRequest.phone_number` is normalized to E.164 by a field validator, so `+12025550123`, `12025550123` and `(202) 555-0123` yield one hash for storage, rate limiting and blocklist matching. Non-US numbers are rejected with "Only US phone numbers are supported".
- **Blocklist and rate limits applied before Twilio spend** — `POST /calls/create` checks the blocklist on phone hash *or* client IP, then rate limits on the phone hash (`call`) and the IP (`call-ip`), before any Lookup call or session write. `POST /tokens/voice` checks the IP blocklist first, then rate limits per IP (`token`, 5/hour) and per campaign (`token-campaign`, 500/hour).
- **Campaign `call_maximum` enforced** — both public paths return HTTP 429 "This campaign has reached its call limit" once the campaign's session count reaches its ceiling.
- **Rep lookup rate limited** — `GET /campaigns/{id}/reps` is limited per client IP (`REPS_RATE_LIMIT`) and per campaign (`REPS_RATE_LIMIT × 25`), so an unauthenticated caller cannot drain the Google Civic / OpenStates quota.
- **Webhook sessions bound to their Twilio call** — `voice-app` requires a WebRTC session's `From` to be `client:{session_id}`, records the `CallSid` on first hit, and hangs up on a later hit carrying a different `CallSid`; `make-calls`, `dial-target` and `call-complete` hang up on the same mismatch, so a leaked `session_id` cannot be replayed from another call.
- **`voice-app` hangs up when the campaign is missing** and also checks the blocklist against the client IP recorded in the call state.
- **`status-callback` ignores an empty `CallSid`** — an empty value previously matched every session whose `twilio_call_sid` was still blank and marked them all completed.
- **`call-complete` hardened** — a repeated `DialCallSid` returns the same TwiML without writing a second `Call` row or skipping a target, an unparseable `DialCallDuration` counts as 0, and an unrecognised `DialCallStatus` is stored as `failed` rather than `completed`. A malformed `session_id` hangs up instead of raising.
- **`campaigns.rate_limit` defaults to 5** — new campaigns are rate limited without configuration; migration `006` backfills existing NULL rows.
- `client_ip` is recorded in the Redis call state so the webhook chain can apply IP-based blocks.
- `resolve_target_ids(campaign, db, rep=None)` builds the transient rep target from the server-stored record only, truncating name to 200 and title to 100 characters; shuffle ordering is skipped only when a rep was selected.
- Migration `006_rate_limit_default.py` — `campaigns.rate_limit` server default plus `ix_call_sessions_campaign_id` for the call-ceiling count.
- `test_call_security.py` — new suite covering rep-token resolution, phone-variant hashing, IP blocklisting, `X-Forwarded-For` spoofing, campaign ceilings, and the webhook bindings.

### Fixed
- **OpenStates v3 phone parsing** — state legislator numbers are read from the `offices` list (capitol first, then district), so state-level rep lookups stop returning empty.
- **Rep lookup adds to the call list** — a looked-up representative is dialed first and the campaign's configured targets follow in order, instead of replacing them.
- **Skip a target with the star key** — dialed legs are placed with `hangupOnStar`, so the widget's `*` control actually ends the current call and moves on.
- **Silent callers no longer strand the call** — the intro gather uses `actionOnEmptyResult`; a caller who presses nothing is re-asked once and then hears the goodbye message.
- **Abandoned sessions marked failed** — a parent call that completes without a single dialed target is recorded as failed, keeping completion counts honest.
- **CSV rows with extra columns** — a ragged row is reported as a row error instead of failing the whole import.
- **Blocklist by phone number** — admins can block a number directly; it is normalized to E.164 and hashed the same way the call paths hash callers, and phone hashes and IPs are now validated.
- **Embed snippet script path** — the campaign embed tab now points at `/static/powerline-embed.iife.js` in the script tag, React snippet, and live preview, so copied snippets actually load the widget.
- **Embed container placement** — auto-init renders into `#powerline-widget` (or the id in `data-container`) instead of always appending a div to the end of `<body>`.
- **Missing `data-api-url`** — the widget logs `[Powerline] data-api-url is required` and renders a configuration error rather than silently issuing relative API calls against the host site.
- **Connected screen on rep calls** — shows the selected representative's name and title and counts them as call 1 of `1 + campaign targets`, matching the server's dial order.
- **Stuck Microphone Access screen** — a connected call always paints a card now, falling back to a generic "Connected" card with timer and End Call when no target detail is known.
- **Swagger and the embed bundle behind Caddy** — `/static/*`, `/docs*` and `/openapi.json` proxy to the backend instead of falling through to the frontend.
- **Invite modal accessibility** — the Users invite modal is a labelled `role="dialog"` with `aria-modal`, closes on Escape, and moves focus to the first field on open.
- **Blocklist empty-state copy** — reads "No blocked numbers or IP addresses" instead of referring to emails the blocklist never stored.

### Changed
- **Staff read access** — staff accounts can open campaigns, analytics, the dashboard, blocklist, phone numbers, and audio lists; every write stays admin-only, and the admin UI hides write controls for non-admins.
- **User activation and role management** — admins can switch a user between admin/staff and activate/deactivate from the Users table via `PATCH /users/{id}`, with the last-active-admin 409 surfaced inline.
- **Blocklist takes phone numbers directly** — the add form uses the standard US phone input and submits E.164 `phone_number` for server-side hashing, with the raw sha256 field kept behind an Advanced disclosure.
- **Embed bundle built into the API image** — `Dockerfile.backend` builds the widget in a `node:20-alpine` stage and copies it to `/app/embed-dist`, so production images ship it; compose keeps the `embed/dist` bind mount for dev hot reload.
- **Slimmer, non-root backend image** — the default target installs base deps only and runs as an unprivileged `app` user; a separate `dev` target adds `.[dev]` and is what docker-compose builds.
- **Configurable embed static dir** — `EMBED_DIST_DIR` overrides `/app/embed-dist`; a missing directory logs a warning in development and an error in production.
- **Dead between-targets screen removed** — the backend advances targets server-side without notifying the browser, so `renderBetweenTargets` and the `between_targets` state are gone.
- **Trimmed Docker build context** — a new `.dockerignore` keeps host `node_modules`, build output, and `.env` out of image builds.

## [2.0.3.0] - 2026-03-21

### Added
- **Audio recording tab** — `AudioSlotCard` now supports in-browser microphone recording (MediaRecorder API) with a live waveform visualizer. iOS < 16 automatically falls back to upload tab.
- **Audio upload via drag-and-drop** — upload tab accepts MP3, WAV, WebM, and M4A files via drag-and-drop or file picker.
- **PhoneInput component** — reusable `+1 (XXX) XXX-XXXX` formatted phone input with E.164 output, blur-based validation, and paste normalization. Used in `TestCallModal`.
- **`CAMPAIGN_STATUS_CHIP` constants** — inline-style color tokens for status chips (rgba-based, covering live, paused, draft, completed, failed, archived).
- **`audio/webm` and `audio/mp4` upload support** — backend now accepts WebM and MP4 audio in addition to MP3 and WAV.
- **Live campaign audio guard** — activating audio on a live campaign now returns HTTP 409; users must pause the campaign first.
- **DESIGN.md** — project design system document (typography, color palette, spacing, component patterns).
- Unit tests: `phone-input.test.ts`, `phone-input-component.test.tsx` (39 total assertions), `import-logic.test.ts` extended with `normalizePhone` tests.
- Backend tests: `test_audio.py` covering MIME validation, file-size guard, and live-campaign guard.

### Changed
- **Dashboard** — redesigned with new typography scale, status chips, and layout using DESIGN.md tokens.
- **CallLog, Campaigns, Users, PhoneNumbers, Blocklist pages** — updated badge colors, table spacing, and status chip styles to match design system.
- **DashboardShell** — sidebar and nav updated with new brand colors and font treatment.
- **AudioSlotCard** — replaced single-mode UI with tabbed Record / Upload / TTS interface; all tabs respect `campaignStatus` live-lock.
- **CampaignAudioTab** — passes `campaignStatus` prop through to `AudioSlotCard`.
- **CampaignWizard** — passes `campaignStatus` through to audio and targets tabs.
- **TestCallModal** — phone number field replaced with `PhoneInput` component.
- **`CAMPAIGN_STATUS_COLORS`** — extended with `completed` and `failed` values; border tokens added to all statuses.
- `tailwind.config.js` — added brand color tokens from DESIGN.md.
- `index.css` — added Inter font import and base typography reset.
- Backend error message updated: "Only MP3 and WAV files are accepted" → "Accepted formats: MP3, WAV, WebM, MP4 (max 10 MB)".

## [2.0.2.0] - 2026-03-21

### Added
- **Elected official rep lookup** — embed widget can now look up a supporter's federal and state representatives by ZIP code before initiating a call. Configured via `target_levels` in campaign `embed_config`.
- **`GET /api/v1/campaigns/{id}/reps`** — public endpoint that accepts a 5-digit ZIP, queries Google Civic (federal) and OpenStates (state) APIs, and returns matching representatives. Results cached in Redis for 24 hours.
- **Rep selection flow in embed widget** — when `target_levels` is configured, the "Call Now" button triggers a ZIP input → representative selection → call flow instead of dialing directly.
- **Transient rep target creation** — `resolve_target_ids()` helper creates a one-time `Target` row (marked `external_id="rep_lookup"`) when `target_phone_override` is provided, preserving call history without requiring pre-configured targets.
- **`target_levels` in public campaign response** — `GET /campaigns/{id}/public` now returns `target_levels` from `embed_config` so the embed widget knows which government levels are active.
- **Target levels UI in campaign admin** — `CampaignTargetsTab` now renders a "Who to call" panel with Federal and State checkboxes (Local is shown as "coming soon"). Changes save immediately via PATCH.
- `GOOGLE_CIVIC_API_KEY` and `OPENSTATES_API_KEY` config fields added; startup warnings logged when either is absent.
- `target_phone_override`, `target_rep_name`, `target_rep_title` fields added to `CallCreateRequest` and `VoiceTokenRequest` schemas for the rep-lookup call path.
- `test_reps.py` — integration test suite covering rep lookup happy path, cache hit, 503 error paths, 429 rate limiting, invalid ZIP, and missing API key.

### Changed
- `resolve_target_ids()` extracted to `helpers.py` — shared by both `calls.py` and `tokens.py`, eliminating duplicated target-loading logic.
- Shuffle ordering in `create_call` and `create_voice_token` is now skipped when `target_phone_override` is set (single-rep path doesn't need shuffling).
- `useCampaignData` hook loads `embed_config` and `target_levels` from campaign on mount; `handleTargetLevelsChange` saves changes with optimistic rollback on error.
- `CampaignDetail` type now includes `embed_config: Record<string, unknown>`.

## [2.0.1.0] - 2026-03-20

### Added
- **CSV bulk target import** — admin users can now import targets into a campaign from a CSV file via the campaign targets tab. Supports drag-and-drop or file picker upload.
- **Column mapping UI** — after file selection, users map CSV headers to canonical fields (name, title, phone_number, location, external_id) with auto-detection of common header aliases.
- **Upsert semantics** — rows with a matching `external_id` update the existing target record instead of creating a duplicate.
- **Partial success** — valid rows are committed even if some rows fail validation (invalid phone, missing fields). Errors are reported per-row.
- **Import error report download** — after a partial import, users can download a CSV of failed rows with an `error_reason` column for easy correction and re-upload.
- **Per-campaign import lock** — Redis-backed distributed lock prevents concurrent imports from creating duplicate targets.
- `normalize_phone` exported from `app/schemas/target.py` for use in import logic.
- `ImportResult` and `ImportRowError` Pydantic schemas for the import API response.
- `GET /api/v1/campaigns/{id}/targets/import-errors` endpoint — downloads the last import's error rows as a CSV (cached in Redis for 1 hour).
- Frontend test suite (`frontend/src/test/`) with 11 unit tests covering CSV header auto-mapping and header remapping logic.
- Backend integration tests (`backend/tests/test_target_import.py`) covering happy path, partial failures, upsert, auth, file validation, and concurrent import lock.
- `TESTING.md` — documents test philosophy, setup, and conventions.

### Changed
- `CampaignTargetsTab` now accepts import-related props for the CSV import panel (file drop zone, column mapper, result summary, error download).
- `useCampaignData` hook extended with all import state and handlers.
- `CampaignEdit` and `Campaigns` pages wired to the new import props.
- `App.tsx` and routing updated to support `CampaignWizard` component.
- Vite config updated with test environment settings (`jsdom`, `globals`, `setupFiles`).
