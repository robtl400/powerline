# TODOS

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

## Completed

### CSV Import Error Report Download
**What:** After a CSV import with errors, provide a "Download Error Report" button that returns a CSV of the failed rows with an added `error_reason` column.
**Completed:** v2.0.1.0 (2026-03-20)

### Elected Official Rep Lookup (federal + state)
**What:** Implement ZIP → representative lookup via Google Civic and OpenStates APIs, with rep selection flow in the embed widget and admin UI for configuring government levels.
**Completed:** v2.0.2.0 (2026-03-21)
