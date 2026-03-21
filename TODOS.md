# TODOS

## AudioSlotCard: TTS preview playback

**What:** Implement `POST /audio/tts-preview` backend endpoint and an inline `<audio>` element in the TTS tab of `AudioSlotCard` so users can hear a preview before saving.

**Why:** The "Generate preview" button was designed in the spec but removed from this PR because the backend endpoint didn't exist and there was no audio element to play the result. Users currently must save-then-listen to evaluate TTS output.

**Pros:** Reduces wasted audio versions (save, listen, hate it, create another). Improves TTS UX significantly for non-technical users.

**Cons:** Requires a new backend endpoint that calls the TTS service, streams back audio, and doesn't persist a new recording.

**Context:** The design doc (robertlord-main-design-20260321-102951.md) specifies: "Generate preview" button (secondary style) — calls existing TTS endpoint; plays inline via `<audio>` element. Removed from AudioSlotCard.tsx during the branding update PR. To add: (1) register `POST /audio/tts-preview` in `audio.py` returning audio bytes, (2) add an `<audio ref>` element to the TTS tab, (3) restore the button with `handleGeneratePreview`.

**Depends on / blocked by:** Nothing. Can be built independently.

---

## AudioSlotCard: Real upload progress tracking

**What:** Replace the fake `animate-pulse` progress bar in the Upload tab with real XHR upload progress via `onUploadProgress`.

**Why:** The current progress bar is always at 50% — it's a pulsing animation, not real progress. For larger files (up to 10 MB), users have no feedback on how far along the upload is.

**Pros:** Better UX for large file uploads. Clear sense of progress vs. "did it hang?"

**Cons:** Requires switching from Axios `client.post` to a raw XHR call with `onUploadProgress`, or using Axios's progress callback. Modest complexity increase.

**Context:** `handleFileUpload` in `AudioSlotCard.tsx` uses `client.post` (Axios). Axios supports `onUploadProgress` config option — no need to switch to raw XHR. The `uploading` state already exists to show/hide the progress bar; just replace `w-1/2 animate-pulse` with a dynamically computed width from upload progress percentage.

**Depends on / blocked by:** Nothing.

---

## Admin UI: AudioSlotCard a11y audit

**What:** Screen-reader walkthrough (VoiceOver + keyboard navigation) for the AudioSlotCard 3-tab media picker — specifically the Record/Upload/TTS tabs, waveform live region, mic button state changes, and "Make active" disabled state.

**Why:** The component introduces meaningful interactive complexity (ARIA tabs, live region announcements, keyboard nav) that is specified in DESIGN.md but not yet verified against actual assistive technology behavior.

**Pros:** Catches ARIA misuse and focus-management issues that are invisible to sighted users. Particularly important for advocacy orgs whose staff may rely on screen readers.

**Cons:** Requires a manual VoiceOver/NVDA environment; can't be fully automated.

**Context:** DESIGN.md specifies `role="tab"` + arrow key navigation, `role="status" aria-live="polite"` on the waveform container, `aria-disabled` on the "Make active" button, and `aria-label` on the mic button state transitions. This TODO covers verification against that spec after the component ships. Pairs with the existing embed widget a11y TODO.

**Depends on / blocked by:** AudioSlotCard implementation merged and on staging.

---

## Widget: full state machine unit test coverage

**What:** Write Vitest unit tests for all existing embed widget states — `connected`, `between_targets`, `audio_check`, `complete`, `error`, `phone_input`, `phone_pending` — beyond the new rep-lookup states added in the elected official API PR.

**Why:** The widget is the most complex client-side component. Without unit tests, regressions during future changes (new states, refactors) are caught only by manual QA. The framework (Vitest + jsdom) is already set up.

**Pros:** Catches regressions cheaply. Documents expected widget behavior as executable specs.

**Cons:** Takes time to mock Twilio Voice SDK; the `connected` state in particular requires a live Twilio Device mock.

**Context:** State machine tests for the new rep-lookup paths (lookingUpReps, repSelection, select-rep, fallback) were added in the elected official API PR. This TODO covers the existing states that remain untested. Start with `widget.test.ts` and mock `WebRTCClient` at the class boundary.

**Depends on / blocked by:** Nothing. Can be done independently.

---

## OpenStates: benchmark p95 latency and add pre-warming if needed

**What:** After the first live campaign, measure p95 latency for OpenStates `GET /api/v3/people.geo` from app logs. If p95 consistently exceeds 2 seconds, implement async cache pre-warming for expected ZIP codes.

**Why:** The design doc flagged this: "if p95 >2s, add async pre-warming or accept the slower path." Cold cache lookups on election-day traffic spikes could frustrate supporters waiting for rep results.

**Pros:** Reduces call-initiation latency for high-traffic campaigns. Pre-warming is especially valuable for orgs with known constituent geography.

**Cons:** Adds operational complexity (background task, ZIP prediction logic). May be unnecessary if OpenStates p95 is comfortably under 2s.

**Context:** The Redis cache (24h TTL) already handles repeated lookups within a session. Pre-warming is only needed for first-hit cold misses at scale. Benchmark using Twilio/app logs from the first live campaign before building anything.

**Depends on / blocked by:** Requires a live campaign with real traffic data.

---

## Local government level lookup

**What:** Implement `"local"` as a selectable government level in the campaign admin UI and the LevelRouter, using Google Civic's local office data.

**Why:** Some advocacy campaigns target city council, county commissioners, or school boards. The "coming soon" badge in the admin UI is a placeholder for this.

**Pros:** Expands the types of campaigns Powerline can support. Differentiates from New/Mode, which has limited local support.

**Cons:** Google Civic's local data coverage is sparse and inconsistent by geography. Quality needs to be confirmed before shipping — an org could get zero local reps for large portions of their supporter base. May require a secondary data source (e.g., Cicero API) for reliable local coverage.

**Context:** The admin UI already has a disabled "Local" checkbox with a "coming soon" badge (`CampaignTargetsTab.tsx`). The `LevelRouter` has a `_PROVIDER_MAP` dict — adding `"local"` is a matter of implementing `fetch_local_reps()` and registering it. Start by confirming which orgs need local targets and what coverage they'd require.

**Depends on / blocked by:** Org feedback on whether local government is needed. Google Civic API key already in place.

---

## Embed widget: full a11y audit for rep-lookup flow

**What:** Screen-reader walkthrough (VoiceOver + NVDA), color contrast check (WCAG AA), and keyboard navigation test for the ZIP input, rep selection list, and error states in the embed widget.

**Why:** The embed widget runs on advocacy org websites where a11y failures are visible to all supporters. The rep-lookup flow introduces new interactive elements (ZIP input, rep buttons) that were not part of the original widget and have not been audited.

**Pros:** Catches failures invisible to sighted keyboard users. A civic engagement tool failing screen-reader users is particularly damaging to org credibility.

**Cons:** Requires VoiceOver/NVDA testing environment and some manual effort.

**Context:** Basic a11y attributes have been specified in the design review (label on ZIP input, aria-live error region, aria-invalid on validation failure, 44px min touch targets on rep buttons). This TODO covers a full hands-on walkthrough after those are implemented to catch anything missed. Start with the ZIP → lookup → rep selection → call path.

**Depends on / blocked by:** Rep-lookup feature on staging.

---

## Admin UI: embed widget preview panel

**What:** A live preview panel in the Campaign admin (Targets or Embed tab) showing what the embed widget will look like to supporters based on current campaign settings — specifically when government levels are configured.

**Why:** Admins setting government levels (Federal/State) have no feedback on what the ZIP input and rep selection flow will look like to supporters without embedding the widget on a test page. This creates a confidence gap during campaign setup.

**Pros:** Reduces setup errors. Helps admins understand the supporter experience without a separate test deployment. Analogous to Mailchimp's email preview.

**Cons:** Requires rendering a widget preview inside a React iframe or shadow DOM sandbox, which adds complexity.

**Context:** The embed widget is a self-contained IIFE bundle. The simplest implementation is a read-only iframe preview in the Embed tab that renders the widget in idle state with current campaign settings. The `target_levels` field is the main variable — preview should show the ZIP input when levels are configured, and the plain "Call Now" button when they're not.

**Depends on / blocked by:** Rep-lookup feature stable and merged.

---

## Voice Note tab (Tab 4) in AudioSlotCard — post-MVP

**What:** Add a Voice Note tab (Tab 4) to AudioSlotCard using the Web Share API or Cloudinary mobile upload integration.

**Why:** De-scoped from the design system MVP because the Cloudinary mobile share integration path was unclear as of 2026-03-21. Capturing here so it doesn't fall off the backlog.

**Pros:** Reduces friction for non-technical users who want to record a voice note on mobile and upload directly without using the Record tab's full waveform UI.

**Cons:** Web Share API for receiving audio input is experimental and inconsistent across browsers. Cloudinary's mobile SDK path needs investigation.

**Context:** The design doc (robertlord-main-design-20260321-102951.md) explicitly de-scoped this: "Tab 4 (Voice Note / web share API) is post-MVP — ship only when the web share API question is resolved." Re-evaluate once Cloudinary's mobile upload integration is confirmed. Start at `frontend/src/components/campaign/AudioSlotCard.tsx` — Tab 4 would be the 4th entry in the tab array alongside Record, Upload, and TTS.

**Depends on / blocked by:** Cloudinary mobile SDK evaluation.

---

## PhoneInput: international phone support

**What:** Extend `PhoneInput.tsx` to support non-US country codes when the product expands internationally.

**Why:** The component is locked to US (+1) in the MVP. The component interface and validation logic will need to change when expanding — better to document the constraint now than discover it as a hidden assumption later.

**Pros:** When international expansion happens, the migration path is clear and scoped to one component.

**Cons:** N/A — this is purely documentation of a known constraint.

**Context:** MVP is US-only per design doc. Two hardcoded US assumptions in `PhoneInput.tsx`: (1) the `🇺🇸 +1` prefix is rendered unconditionally, (2) validation requires exactly 10 digits. For international support, these become a country selector (dropdown or auto-detect) and per-country digit count validation. Also check `normalizePhone()` in `useCampaignData.ts` — CSV import normalization has the same 10-digit assumption.

**Depends on / blocked by:** Product decision to expand internationally.

---

## Completed

### CSV Import Error Report Download
**What:** After a CSV import with errors, provide a "Download Error Report" button that returns a CSV of the failed rows with an added `error_reason` column.
**Completed:** v2.0.1.0 (2026-03-20)

### Elected Official Rep Lookup (federal + state)
**What:** Implement ZIP → representative lookup via Google Civic and OpenStates APIs, with rep selection flow in the embed widget and admin UI for configuring government levels.
**Completed:** v2.0.2.0 (2026-03-21)
