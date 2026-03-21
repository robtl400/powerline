# Changelog

All notable changes to this project will be documented in this file.

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
