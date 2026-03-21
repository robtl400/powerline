# TODOS

## Campaigns / Rep Lookup

### Local Elected Officials (Hyper-local Rep Lookup)

**What:** Extend the rep lookup to resolve local officials (city council, county supervisors, school boards) in addition to federal/state reps.

**Why:** Advocacy orgs running local campaigns (zoning, school policy) need local officials, not just federal/state reps. This is the long-term completeness of the "flexibility vs. New/Mode" value prop.

**Context:** Step 3 (Google Civic / OpenStates) covers federal + state well; local coverage is sparse and inconsistent. Options: Cicero API (paid, best local data), Google Civic's `roles` filter for local, or manual fallback. Evaluate after Step 3 is live and org feedback arrives. Low priority until an org explicitly asks for local targeting.

**Effort:** M
**Priority:** P2
**Depends on:** Rep lookup service (step 3) shipping; org feedback confirming local targeting need

---

### Campaign Health Panel

**What:** Admin panel on the campaign stats tab showing real-time operational metrics: cache hit rate (last hour), rep lookup success rate, call connection rate, and geolocation fallback trigger rate.

**Why:** Organizers launching a campaign have no visibility into whether the rep lookup is working without manually testing it. A health panel lets them verify "rep lookups: 98% success" before going live and makes on-call debugging much faster.

**Context:** Metrics will be available once the rep lookup service (civic_service.py) and geocoding service are built in step 3. The panel reads from structlog aggregates or a lightweight Redis counter set that the services write to. This is a v2 follow-up — build after real traffic generates metrics worth displaying.

**Effort:** S
**Priority:** P2
**Depends on:** Rep lookup service (step 3) shipping and generating real metrics

---

## Infrastructure / Observability

### Post-call SMS Follow-up

**What:** After a supporter completes a call, send them a configurable SMS: "Thanks for calling Rep. Smith! Here's a talking point for your next call: [link]"

**Why:** Turns a one-time action into continued engagement. Advocacy orgs track supporter engagement metrics. Post-call SMS is a standard expectation in digital organizing tools.

**Context:** SMS infrastructure exists: `services/sms.py`. The `embed_config` JSONB on Campaign already stores custom per-campaign settings. Triggered via Twilio status callback when call completes (status = "completed"). Campaign admin configures the SMS body in embed_config. Requires opt-in consent UX in the embed widget (supporter enters phone for callback → opt-in implied). Evaluate consent flow carefully before building.

**Effort:** S/M
**Priority:** P2
**Depends on:** Reliability hardening (step 5); legal review of SMS consent requirements

---

### Real-time Campaign Analytics Dashboard

**What:** Live dashboard showing call volume, connect rate, talk time distribution, and per-target call counts. Visible to campaign admins during a live campaign.

**Why:** Organizers need to know if their campaign is working in real-time. "How many calls have been made today?" is the first question every org asks post-launch.

**Context:** Call data is already written to the `calls` table via Twilio status callbacks. The analytics router (`api/v1/analytics.py`) exists. This is a querying + UI problem, not a data collection problem. Consider a polling endpoint (`GET /api/v1/campaigns/{id}/live-stats`) that aggregates calls in the last N minutes. Upgrade to Server-Sent Events or WebSocket if polling latency (5s) is too slow for organizers.

**Effort:** M
**Priority:** P2
**Depends on:** None — data already available

---

### CRM/Webhook Integration

**What:** When a call is completed, push a webhook to a configurable URL: `{supporter_phone, campaign_id, target_name, call_status, duration, timestamp}`. Enables ActionNetwork, NGP VAN, and custom CRM integrations.

**Why:** Advocacy orgs use CRMs to track constituent engagement. Without this, call data is siloed in Powerline. With it, every call is an action in the org's contact database.

**Context:** Campaign model has `embed_config` JSONB for per-campaign settings. Add `webhook_url` and `webhook_secret` fields (HMAC signing for verification). Fire via Celery task on call completion. This is a standard Zapier/Make-style webhook pattern.

**Effort:** M
**Priority:** P2
**Depends on:** Reliability hardening (step 5); call status webhook pipeline stable

---

### Phone Number Validation Badges

**What:** In the campaign targets list, show a green/yellow/red badge per target indicating Twilio Lookup validation status: valid mobile, valid landline, or invalid/unverifiable.

**Why:** Organizers can identify bad phone numbers in their target list before going live. Avoids the frustration of a call campaign that silently fails for 20% of targets.

**Context:** Twilio Lookup API (`lookup_validate` flag already on Campaign model). Currently lookup is called at call-initiation time. For target validation badges, run Lookup asynchronously on target creation/import via a Celery task and store result in `target_metadata`. Show badge in `SortableTargetRow.tsx`. Consider cost: Twilio Lookup is not free (~$0.005/lookup). Add a campaign-level toggle.

**Effort:** M
**Priority:** P3
**Depends on:** CSV import (step 2) to provide bulk targets worth validating

## Completed

### CSV Import Error Report Download
**What:** After a CSV import with errors, provide a "Download Error Report" button that returns a CSV of the failed rows with an added `error_reason` column.
**Completed:** v2.0.1.0 (2026-03-20)
