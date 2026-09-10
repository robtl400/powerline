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

### Security (sessions and edge)
- **Refresh tokens rotate and are single-use** — every refresh token carries a `jti` registered in Redis and is consumed on use; `POST /auth/refresh` returns a new access *and* refresh token, and replaying a spent one is a 401.
- **`POST /auth/logout` retires a refresh token** — always answers 204, including for expired, malformed, or already-revoked tokens.
- **Deactivation, role changes, and password resets end sessions immediately** — all of a user's refresh tokens are dropped and a per-user session floor retires outstanding access tokens instead of letting them run to expiry.
- **CORS is split by path** — public embed endpoints answer any origin; everything else uses `ADMIN_CORS_ORIGINS`, which emits no CORS headers when empty. Admin routes sharing the `/api/v1/campaigns/` prefix are no longer treated as public.
- **Interactive docs are off in production** — `/docs`, `/redoc`, and `/openapi.json` require `DOCS_ENABLED=true` outside development.
- **Redis authentication is honored** — `REDIS_PASSWORD` is applied unless `REDIS_URL` already carries credentials; the production stack starts Redis with `--requirepass` and `--maxmemory-policy noeviction`.
- **Security headers at the edge** — HSTS, `X-Content-Type-Options`, `Referrer-Policy` on all responses, plus `X-Frame-Options: DENY` and a CSP on the admin SPA.
- **Raw phone numbers are out of the logs** — the lookup, blocklist, rate-limit and SMS paths log a hash prefix or nothing at all.
- **Audio uploads are verified by their bytes** — the declared MIME type is no longer trusted; MP3, WAV, WebM and MP4/M4A headers must match. CSV and audio uploads are read in 64 KiB chunks and rejected the moment they pass the limit.
- **The CSV import lock can no longer be stolen** — each import holds a token and releases only the lock it still owns.

### Fixed (data integrity and UI)
- **Enum inputs return 422, not 500** — campaign type, ordering, language and status, plus the analytics status and connection-type filters, are validated as literals instead of reaching the database as bad enum values.
- **Mobile-only campaigns reject every non-mobile line** — VoIP, non-fixed VoIP, toll-free and unknown line types are refused alongside landlines, matching the setting's own description.
- **The "target unavailable" message actually plays** — a busy, unanswered, failed or cancelled target hands off with `msg_target_busy` before dialing the next one.
- **Removing a target no longer erases call history** — the target row is deleted only when no other campaign lists it and no logged call points at it.
- **Failed callbacks stop leaving dangling sessions** — when Twilio refuses the outbound call the session is marked failed instead of sitting at "initiated" forever.
- **Representative lookups cache per level set** — the configured target levels are part of the cache key, so changing them no longer serves the previous set's representatives for a day.
- **One active recording per audio slot, guaranteed** — a unique constraint on version and a partial unique index on the active row, with activation serialized by a row lock and version collisions retried.
- **Dashboards and date filters follow `TIMEZONE`** — day boundaries, the seven-day series and bare start/end dates are local days rather than UTC days.
- **Refresh-token rotation handled in the admin client** — the rotated token is stored, queued requests are marked retried before replay so a second 401 cannot loop, and both tokens are cleared once before redirecting to login. Logout posts the refresh token to `/auth/logout`.
- **Clearing a phone field yields an empty value** — `toE164` returns an empty string when the input has no digits instead of a bare `+1`.
- **Quote-aware CSV header remapping** — target import parses the header row per RFC 4180 and rewrites only the header line, so quoted newlines and CRLF endings in the body reach the backend byte-for-byte.
- **Phone-number trust badges show real statuses** — keyed on `twilio-approved`, `pending-review`, `in-review` and displayed as Verified / Pending / Unknown.
- **Audio upload shows real progress** — driven by axios upload progress instead of an indeterminate half-width pulse; the recording waveform is capped at ~15 fps.
- **Embed call timer stops re-rendering the whole card** — a single timer node updates each second; the card re-renders only on state changes.

### Changed (schema, tasks, deployment)
- **Campaign names are unique among active campaigns** — archived campaigns release their name via a partial unique index.
- **Foreign keys carry indexes** — calls, campaign targets and campaign phone numbers are indexed on the columns they join by; `Campaign.status` matches its existing index.
- **Listings paginate** — `GET /campaigns`, `GET /users` and `GET /phone-numbers` accept `skip`/`limit` (default 200, max 500); responses are still lists. The public call-count endpoint answers in one query instead of three.
- **Migrations compare server defaults** — schema drift in column defaults now shows up in `alembic check`, and database URLs containing `%` no longer break Alembic's config parsing. Migration `007_audio_integrity_indexes`.
- **Token lifetimes come from configuration** — `ACCESS_TOKEN_EXPIRE_MINUTES` and `REFRESH_TOKEN_EXPIRE_DAYS`.
- **Voice Insights no longer overlaps or leaks connections** — the run holds a Redis lock, reuses one engine per worker, fetches summaries through a bounded 4-thread pool, and selects on `quality_details IS NULL` so a fetched-but-unscored call is not refetched every cycle.
- **New daily `cleanup_rep_targets` task** — deletes rep-lookup targets older than 30 days that no campaign references; call history survives via the `SET NULL` FK.
- **Production deployment stack** — standalone `docker-compose.prod.yml` and `Caddyfile.prod` with automatic TLS, unpublished datastores, and a documented walkthrough in the README. The dev stack no longer publishes the backend port; reach it through Caddy on port 80.
- **Version is read from the `VERSION` file** — API, health endpoint, pyproject and both package.json files report 2.0.4.0.
- **Error styling moved onto brand tokens** — blocklist, campaign edit, and campaign targets errors use brand-grey-dark on page-bg in place of the destructive red tokens; the embed palette uses brand orange and gum instead of blue and green.
- **Dev-server hostnames are configurable** — `VITE_ALLOWED_HOSTS` replaces the hardcoded tunnel hostname.
- **Embed bundle is minified with source maps**, Copy Link works without inline script, and HTML escaping covers single quotes.

### Fixed (found by the new tests)
- **Duplicate campaign names return 409** — creating or renaming a campaign onto a name that an active campaign already uses returns "A campaign with that name already exists" instead of an unhandled integrity error.
- **Embed rep-lookup errors keep their message** — `fetchReps` parsed a non-OK body twice, so the backend's `detail` was lost on every 503 that was not a manual-entry fallback; the body is now read once. The phone-entry screen also shows the lookup fallback message instead of only the microphone-denied notice.
- **Call log filters have accessible names** — the Status, Type, From and To controls are associated with their labels.

### Tests
- **Backend** — 155 → 227 test functions (300 collected): Twilio webhook signature validation (real `RequestValidator` signatures, dev-mode skip, tampered form and query), users CRUD, phone number sync/list/assign with a mocked provider, analytics happy paths over seeded sessions and calls, dashboard aggregates with zero-filled series, campaign PATCH/archive/checklist/count-cache/shuffle, and every webhook handler's not-found and malformed-session paths.
- **Frontend** — 66 → 117: auth context, protected route, the campaign data hook (optimistic updates and rollbacks, import, downloads, test call), campaign settings tab (read-only mode, checklist, test-call gating), and the call log page (filters, pagination, export).
- **Embed** — 28 → 61: full WebRTC call lifecycle under fake timers, phone fallback, every `api.ts` error branch, and the widget's ZIP validation, rep selection, expired-selection recovery, completion count and copy-link flows.

### Removed
- **Dead telephony code** — `LookupService`, the provider's `generate_access_token`/`generate_voice_grant`, the unused TwiML builders, the unused `CAMPAIGN_STATUS_CHIP` export, and import-logic tests for a `normalizePhone` that never existed in production code.
- **Single-implementation abstractions** — the `RepLookupProvider` Protocol (no implementations, no consumers) and the `TelephonyProvider` Protocol (`TwilioProvider` was its only implementation and callers already used the concrete class); the shared dataclasses stay.
- **`_to_response` wrappers in the audio, admin and phone-number routers** — every route declares `response_model=` and every response model sets `from_attributes=True`, so the routes return ORM objects and FastAPI does the conversion. Response bodies are unchanged.
- **`PhoneFallbackClient` class in the embed** — replaced by a plain `submitPhoneFallback()` function with the same state transitions; `renderAudioCheck` no longer takes the two arguments it never read.

### Fixed (live design review, high impact)
- **Campaign tabs reachable at 375px** — the five-tab strip scrolls horizontally with proximity snapping, a hidden scrollbar and a right-edge fade that appears only while the strip overflows; the tabs are a real `role="tablist"` with `aria-selected`, roving `tabIndex`, arrow/Home/End navigation and 44px touch targets.
- **Password reset reachable from the UI** — a "Forgot password?" link under Sign in opens a public `/reset-password` page: email, then 8-digit code plus a new password, with the 400 detail, the 422 policy messages and the rate-limit message rendered in `brand-grey-dark` and a Sign in link on success.
- **Visible focus ring on the audio picker** — the shared `FOCUS_RING` token covers the media tabs, mic start/stop, upload drop zone, Save/Discard, "Make active" and the TTS variable chips.
- **Page titles back on one scale** — the Login and Call Log headings use `PAGE_HEADING` (22px/700) like every other page.
- **Mobile nav drawer is a modal dialog** — it shares `Modal`'s focus trap through a new `useDialogBehaviour` hook: `role="dialog" aria-modal="true"`, focus lands on the first nav link, Escape/scrim/nav activation close it, focus returns to the hamburger, and the hamburger reports `aria-expanded`.
- **Embed End Call button on palette** — the Tailwind-red fill is replaced by a brand-orange outline treatment with an orange-tint hover, black focus ring and a phone-off icon; no red hex remains in the embed.

### Fixed (live design review, medium impact)
- **Touch targets below 44px** — sidebar Logout, dashboard Manage/View all, campaign Resume wizard/Edit, phone-number Assign, both back links, the Users role select and activation button, the call-log filter controls and the campaign status tabs all carry a 44px hit area via `LINK_BUTTON`, with text sizes unchanged.
- **Users table unusable on mobile** — below `sm` each user renders as a card with name, email, phone, role select, status chip and the activation button, bound to the same handlers.
- **Back link wrapping into the title** — the campaign and call-log headers stack on mobile, putting the back link on its own line while the status chip stays with the title.
- **Weak action on campaign rows** — the campaign name links to its edit page, Resume wizard shows only on drafts, and every other row gets an explicit Edit action.
- **Campaign search** — `/campaigns` gains a debounced search field backed by a `q` filter on `GET /campaigns` that matches names case-insensitively with wildcards escaped.
- **One empty-state shape** — `EmptyState` / `EmptyTableRow` serve the dashboard chart and live-campaigns table, call log, users, phone numbers, blocklist, campaigns list and the targets tab.
- **Orange only for actions** — phone-number capability tags use a neutral chip and the user status chip comes from a shared `USER_STATUS_COLORS` map.

### Changed (design polish)
- **Card styling is a token** — `CARD_CLASS` plus `rounded-card` / `rounded-control` / `rounded-field` and `shadow-card` Tailwind tokens replace every hand-written radius and shadow; the embed card and controls use the same 10px / 7px / 8px radii.
- **Transitions name their property** — `transition-all` is gone; animated elements declare `transition-colors`, `transition-opacity` or `transition-[height]`.
- **Numeric columns align** — `tabular-nums` on counts, durations, dates, phone numbers, stat tiles and the embed timer.
- **Browser surfaces follow the palette** — themed selection highlight, orange caret, brand scrollbar colours and visited links that inherit their colour; scoped to `.pl-card` in the embed so host pages are untouched.
- **Headings balance their line breaks** — `text-wrap: balance` on `h1` and `h2`.
- **Roving tab focus follows selection** — arrow / Home / End keys on the campaign and audio tab strips move DOM focus to the selected tab.
- **DESIGN.md documents the new primitives** — `CARD_CLASS`, `LINK_BUTTON`, `EmptyState`, the radius/shadow tokens, the search field, the mobile user cards and the browser-surface CSS; the blocklist empty-state copy is corrected.

### Changed (design system)
- **Accessible modal dialogs** — a reusable `Modal` component with `role="dialog"`, `aria-modal`, Escape and backdrop dismissal, focus move-in/restore, and a Tab focus trap; adopted by the Test Call modal, the Users invite modal, and both delete confirmations.
- **Native `confirm()` replaced** — removing a campaign target or a blocklist entry opens an in-app confirmation dialog with Cancel and Remove instead of the browser prompt.
- **Emoji swapped for icons** — the admin uses lucide `Phone`, `Check`, `AlertTriangle`, `Mic`, `Play` and `GripVertical` (icons `aria-hidden`, checklist rows carry visually-hidden state text); the embed widget ships hand-written inline SVG icons so it never depends on emoji font rendering on a host page.
- **Success state uses brand-gum** — passing checklist rows and the test-call success message are gum, never orange.
- **WCAG AA text contrast** — `brand-grey-light` (#92918F, 3.15:1 on white) is no longer used for text below 18px; hints, captions, table meta and status-badge labels use `brand-grey-dark`. DESIGN.md records the rule.
- **Responsive form grids** — two-column forms in campaign settings, campaign targets, the blocklist add form and the call-quality panel stack to one column below `sm`.
- **Brand tokens replace shadcn defaults** — `bg-primary`, `text-muted-foreground`, `border-border`, `bg-background`, `bg-card`, `bg-muted` and `text-destructive` migrated to brand-* equivalents across the authenticated UI and the login page, removing the last literal red.
- **Embed palette and styles aligned to DESIGN.md** — brand orange, gum, text and border tokens; error text off red; recurring inline styles consolidated into named classes; the system font stack is kept deliberately so the widget never loads third-party fonts on host sites.

### Changed (simplification)
- **Live-campaign lookup consolidated** — `get_live_campaign_or_404` replaces four copies of the same fetch-and-404 block in the call, token, rep-lookup and public-campaign endpoints. Same 404 and detail message.
- **Twilio status maps lifted to module constants** — `DIAL_STATUS_TO_CALL_STATUS` and `CALL_STATUS_TO_SESSION_STATUS` in the webhook router instead of dict literals rebuilt per request.
- **Call-session timestamps typed as datetimes** — `CallSessionRow.created_at` is a `datetime`, so `GET /campaigns/{id}/calls` serializes it as `…T12:00:00Z` instead of `…T12:00:00+00:00`, matching every other timestamp the API returns. The CSV export is unchanged.

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
