# Changelog

All notable changes to this project will be documented in this file.

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
