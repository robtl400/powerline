# Powerline Design System

**Source of truth for all UI decisions.** Every color, spacing value, and component rule
in this file is locked. When in doubt, this file wins over inline code.

---

## Color Tokens

| Token name         | Hex       | Tailwind class        | Role |
|--------------------|-----------|-----------------------|------|
| `brand-orange`     | `#F2542D` | `brand-orange`        | **Action + Live state** — CTAs, active nav, live campaign indicator |
| `brand-gum`        | `#B05357` | `brand-gum`           | **Success state** — completed calls, active version badge, waveform |
| `brand-black`      | `#111111` | `brand-black`         | **Bold accent** — wordmark, headings, strong emphasis |
| `brand-grey-dark`  | `#53565B` | `brand-grey-dark`     | Secondary text, logout link, error text |
| `brand-grey-light` | `#92918F` | `brand-grey-light`    | Muted text at 18px+, borders, decorative fills — never text below 18px |
| `white`            | `#FFFFFF` | `white`               | All surfaces — header, sidebar, cards |
| `page-bg`          | `#F4F5F7` | `page-bg`             | Page background — makes white cards float |
| `brand-border`     | `#E4E6EC` | `brand-border`        | All borders |
| `btn-secondary-bg`     | `#FFFFFF` | —                 | Secondary button background |
| `btn-secondary-border` | `#E4E6EC` | —                | Secondary button border |
| `btn-secondary-text`   | `#53565B` | —                | Secondary button label |

### Color Rules — No Exceptions

- **No green, ever.** Green is not in the Powerline palette.
- **Orange = action OR live status only** — CTAs, active nav item, live campaign chip.
- **Gum = success/active/completed** — completed calls, active audio version badge, active user status.
- **Greyscale = everything else** — paused, draft, pending, neutral, failed.
- **Black = wordmark and bold display text only.**
- **Orange is never used for error states** — use `brand-grey-dark` + icon.
- **Orange is never used for success states** — use `brand-gum`.
- **Badges that describe rather than act are grey** — phone-number capability tags use `CAPABILITY_BADGE_COLOR`, user status uses `USER_STATUS_COLORS` (active = gum, inactive = grey). Nothing wears orange unless it is an action or a live status.
- **`brand-grey-light` is not used for text below 18px** (3.15:1 on white fails WCAG AA) — use `brand-grey-dark` for hints, captions and table meta. `brand-grey-light` stays available for large text, borders and decorative use.

### Status Chip Specs

| State     | Text color         | Background                    | Border                        |
|-----------|--------------------|-------------------------------|-------------------------------|
| Live      | `#F2542D` orange   | `rgba(242,84,45,0.10)`        | `rgba(242,84,45,0.25)`        |
| Completed | `#B05357` gum      | `rgba(176,83,87,0.10)`        | `rgba(176,83,87,0.20)`        |
| Paused    | `#53565B` grey-dark  | `#F4F5F7`                   | `#E4E6EC`                     |
| Draft     | `#53565B` grey-dark  | `#F9FAFB`                   | `#E4E6EC`                     |
| Failed    | `#53565B` grey-dark  | `#F3F4F6`                   | `#D1D3D9` — darker to distinguish from draft |

---

## Typography

Font: **DM Sans** (Google Fonts — already loaded)

The embed widget uses the host page's system font stack so it never issues third-party font requests from embedding sites, and inherits DM Sans only when the host already loads it.

| Role           | Size  | Weight | Notes |
|----------------|-------|--------|-------|
| Wordmark       | 16px  | 900    | Uppercase, letter-spacing -0.04em, color: `brand-black` |
| Page title     | 22px  | 700    | Letter-spacing -0.03em |
| Section title  | 13px  | 700    | Color: `brand-grey-dark` |
| Body / table row | 13px | 400 / 600 | 400 for meta, 600 for primary cell |
| Field label    | 12px  | 600    | Color: `brand-grey-dark` |
| Uppercase label | 11px | 700   | Letter-spacing 0.07em, color: `brand-grey-dark` |
| Hint / meta    | 11px  | 400    | Color: `brand-grey-dark` |

---

## Spacing & Shape

- **Focus ring:** every interactive element carries `FOCUS_RING` from `styles.ts` — `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-black focus-visible:ring-offset-2`
- **Minimum touch target:** `44px` on every interactive element — tabs, drawer controls, filter selects and inputs, row buttons and standalone text links. Text-style actions use `LINK_BUTTON`, which carries the hit area at the 14px action size
- **Border radius:** use the tokens, never a bracket literal — `rounded-field` (`8px`) for inputs and small elements, `rounded-control` (`7px`) for buttons and nav items, `rounded-card` (`10px`) for cards and modals
- **Card shadow:** `shadow-card` — `0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)`
- **Transitions:** name the property — `transition-colors`, `transition-opacity`, `transition-[height]`. Never `transition-all`
- **Numeric columns and stat tiles** carry `tabular-nums` — targets, call counts, durations, dates and phone numbers
- **Sidebar width:** `220px` (both desktop sidebar and mobile drawer)
- **Page padding:** `28px` desktop, `16px` mobile
- **Stat cards:** 4-column grid on desktop, 2-column on mobile

---

## Layout — Desktop Shell

### Header (`top-bar`)
- Background: `#FFFFFF`
- Height: `52px`
- Left zone (`220px`): `POWERLINE` wordmark — `brand-black`, weight 900, uppercase, tracking `-0.04em`; `border-right: 1px solid #E4E6EC`; links to `/dashboard`
- Right zone: avatar chip (`brand-gum` initial circle + user name); logout on click/hover
- No `border-bottom` — the Powerlines SVG is the separator

### Powerlines Decoration
The three bezier curves **are** the visual separator. There is **no `border-bottom`** on the container.

```html
<svg viewBox="0 0 1440 30" height="24" preserveAspectRatio="none" width="100%" fill="none">
  <path d="M 0,22 Q 720,2 1440,18"  stroke="#6b7280" stroke-width="1.5"/>
  <path d="M 0,8 Q 720,28 1440,12"  stroke="#6b7280" stroke-width="1.5"/>
  <path d="M 0,15 Q 600,6 1440,24"  stroke="#6b7280" stroke-width="1.5"/>
</svg>
```

Do not modify stroke color, stroke-width, or path data.

### Sidebar
- Background: `#FFFFFF`
- `border-right: 1px solid #E4E6EC`
- Width: `220px`
- Active nav item: `background: #F2542D`, `color: #fff`, `font-weight: 600`, `border-radius: 7px`
- Inactive: `color: brand-grey-dark`; hover: `background: #F4F5F7`
- Footer (pinned bottom): user email (`brand-grey-dark`) + logout link (`brand-grey-dark`)
- On mobile: hidden by default, replaced by full-height drawer

### Main Content Area
- Background: `#F4F5F7` (`page-bg`)
- Padding: `28px` desktop, `16px` mobile
- White cards with box-shadow float on this tint

### Secondary Button Spec
```css
background: #FFFFFF;
border: 1px solid #E4E6EC;
color: #53565B;
border-radius: 7px;
/* hover */
background: #F4F5F7;
```

---

## Layout — Mobile (< 768px)

### Mobile Header
- Height: `48px`, background `#FFFFFF`
- Left: hamburger (3 lines, `brand-grey-dark`)
- Center: `POWERLINE` wordmark — `brand-black`, weight 900, uppercase
- Right: avatar circle (`brand-gum`)
- No `border-bottom` — Powerlines SVG immediately below is the separator

### Powerlines on Mobile
Use the **exact same SVG** as desktop — `preserveAspectRatio="none"` handles scaling. Do not change the viewBox on mobile.

### Nav Drawer
- Full-height slide-in from left, `220px` wide
- Background: `#FFFFFF`
- Backdrop: `rgba(0,0,0,0.20)` — tap outside to close
- Same nav items and active state as desktop sidebar
- Pinned footer: user email (`brand-grey-dark`) + logout link
- **Modal semantics:** `role="dialog" aria-modal="true" aria-label="Navigation"`, focus moves to the first nav link on open, Tab is trapped inside, Escape / backdrop tap / nav activation close it, and focus returns to the hamburger — which carries `aria-expanded`. Shares `useDialogBehaviour` with `Modal`; the drawer is `inert` while closed
- **Animation:** drawer uses `transform: translateX(-100%)` → `translateX(0)`, `transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1)` (Material standard easing). Backdrop fades in `opacity: 0 → 1` over `200ms ease`. Close reverses both.

### Mobile Campaign Cards (Dashboard/Campaigns)
- One card per campaign, stacked vertically
- Layout: `[name] [status chip]` / progress bar / `[call count] [completion %]`
- Tap navigates to `/campaigns/:id/edit`, the same target as the table's name link
- Progress bar: orange fill for live, `#D1D3D9` for paused/draft
- Empty state: show `0` calls, `0%` completion — do not hide

### Campaign Tab Strip (`/campaigns/:id`)
- `role="tablist"` with five `role="tab"` buttons (`aria-selected`, `aria-controls`), roving `tabIndex`, arrow / `Home` / `End` key navigation
- Strip scrolls horizontally: `overflow-x: auto`, `-webkit-overflow-scrolling: touch`, `scroll-snap-type: x proximity`, `snap-start` per tab, scrollbar hidden (`scrollbar-width: none` + `::-webkit-scrollbar`)
- Right-edge fade gradient renders only while the strip is scrollable — tracked by a scroll listener and `ResizeObserver` on a `data-overflow` attribute
- Tab minimum touch target: `min-height: 44px`

### Mobile User Cards (/users)
Below `sm` the users table is replaced by one card per user — name, email, phone, then the role select, status chip and Deactivate/Activate control, all bound to the same handlers as the table row. Both layouts render and Tailwind switches between them (`sm:hidden` on the card list, `hidden sm:block` on the table), so the swap needs no JavaScript.

### Back Links on Mobile
`CampaignEdit` and `CallLog` headers stack `flex-col sm:flex-row`: below `sm` the back link sits on its own line above the page title, and the status chip stays beside the title.

### Mobile Defaults (all other pages)
- Tables: full-width with `overflow-x: auto`
- Modals: `max-width: min(480px, 90vw)`
- Filter bars and tab rows wrap or stack vertically
- Full-width buttons in modals

---

## Component: Search Field

**Used on:** `/campaigns`, beside the status filter tabs (right-aligned, wraps below them on mobile).

- `INPUT_CLASS` + `min-h-[44px]`, `sm:w-[240px]`, `type="search"`, placeholder `"Search campaigns…"`
- `aria-label="Search campaigns"` — the tab strip is the only visible label context
- Debounced **250 ms** before the request fires; the term goes out as the `q` query param
- **Escape clears the field** (and therefore the filter)
- Backend: `GET /campaigns?q=` matches `Campaign.name` case-insensitively (`ilike`), `max_length=100`, with `%` and `_` escaped so a typed wildcard stays literal
- Zero matches use the empty state `"No campaigns match your search"` — never the "No campaigns yet" copy, which would read as data loss

---

## Component: PhoneInput

**File:** `frontend/src/components/PhoneInput.tsx`

US-only. `+1` is never typed by the user.

### Visual
- Prefix box: `🇺🇸 +1` — `background: #F4F5F7`, `border-right: 1px solid #E4E6EC`
- Input: accepts 10 digits, auto-formats to `(XXX) XXX-XXXX` as user types

### Behavior
- `type="tel"`, `inputmode="tel"`, `maxLength={14}` (formatted), `autoComplete="tel"`
- On submit: strip all non-digits, prepend `+1`, validate exactly 10 digits remain
- Stores and submits in **E.164 format: `+1XXXXXXXXXX`**

### Error State
- `border: 1.5px solid #53565B` (`brand-grey-dark`) + inline error text below
- Validation message: `"Enter a 10-digit US phone number"` (11px, `brand-grey-dark`)
- **Never orange, never red**

### Usage
Apply to: `CampaignTargetsTab` (add/edit phone fields), `Users` invite modal, `TestCallModal`.

### CSV Import Normalization
- Accept bare 10-digit (`2025550142`) OR E.164 (`+12025550142`)
- Strip all non-digit chars before normalizing
- Reject and flag rows where digit count ≠ 10 (after stripping country code)

---

## Component: AudioSlotCard (3-Tab Media Picker)

**File:** `frontend/src/components/campaign/AudioSlotCard.tsx`

Replaces upload-only UI with a 3-tab picker. Tab 4 (Voice Note) is post-MVP.

### Props
Must include `campaignStatus: string`. Used to gate "Make active" on live campaigns.

### First-Time Experience

When no active version exists (new campaign): render the full tab picker with a hint line above it: `"No audio yet — record, upload, or generate a script below"` (11px, `brand-grey-dark`). This orients the user immediately; do not show a separate empty state that hides the tabs.

When an active version exists (returning): hide the hint, show the Active Version Row first, then the tab picker below it for updates.

### Tab 1: Record

State machine:
```
idle ──[click mic]──► recording ──[click stop]──► stopped
                          │                          │
                    [pulse anim]              [Save / Discard]
                    [waveform: 8 bars,
                     4px wide, 4px gap,
                     20-60px height,
                     brand-gum color]
```

- **Idle:** orange mic circle, `50px`, `box-shadow: 0 3px 12px rgba(242,84,45,0.4)` + "Tap to start recording"
- **Recording:** mic button pulses (CSS animation) + live `AudioContext.createAnalyser()` waveform
- **Stopped:** waveform freezes; "Save recording" (primary) + "Discard" (secondary) appear. On "Save recording" click: button shows spinner + `"Saving…"` (disabled). On success, `onRefresh()` and reset to idle — no separate toast. On error, inline `"Save failed — try again"` in `brand-grey-dark`.
- **Waveform fallback:** if `AudioContext` unavailable → 3-bar CSS pulse animation
- **MIME output:** `audio/webm` (Chrome/Android) or `audio/mp4` (Safari/iOS 16+)
- **iOS < 16:** Record tab disabled — `"Recording requires iOS 16+ or Chrome. Use Upload instead."` Auto-select the Upload tab as default on iOS < 16 (do not land the user on a disabled tab).
- **Mic denied:** inline message `"Microphone access required — check browser settings"` (not a toast)
- **Mid-recording error** (`mediaRecorder.onerror`): reset to idle + inline `"Recording stopped — check microphone access"`
- **Cleanup:** `useEffect` cleanup must stop mic stream + close `AudioContext` on unmount
- **`AudioContext` reuse:** create lazily via `useRef<AudioContext | null>` — reuse across takes, close on unmount

### Tab 2: Upload
- Drag-and-drop zone: `border: 2px dashed #E4E6EC`, `border-radius: 8px`
- Hover: `border-color: #F2542D`, `background: rgba(242,84,45,0.04)`
- Accepted: `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/webm`, `audio/mp4`
- Max file size: **10 MB** — if exceeded, show inline error: `"File too large — max 10 MB"` in `brand-grey-dark` (no upload attempt)
- Progress bar (orange) during upload
- Error: filename + `"Upload failed — try again"` in `brand-grey-dark`
- **Upload success:** no explicit confirmation toast — `onRefresh()` triggers, which updates the Active Version Row with the new file; the row update is the confirmation

### Tab 3: TTS
- Textarea: max 500 characters, character count shown (`XXX / 500`, `brand-grey-dark`)
- Template variable chips: `{{title}}`, `{{name}}`, `{{calls_left}}` — outlined pills (`border: 1px solid #E4E6EC`, `border-radius: 4px`, `background: #F4F5F7`, `font-size: 11px`, `color: brand-grey-dark`). Clicking a chip inserts the variable text at the current cursor position in the textarea.
- **"Generate preview":** while generating, button shows spinner + `"Generating…"` (disabled). On success, auto-plays via `<audio>` element. On error, inline `"Preview failed — try again"` below button in `brand-grey-dark`.
- **"Save as audio":** while saving, button shows spinner + `"Saving…"` (disabled). On success, `onRefresh()` — no separate toast. On error, inline `"Save failed — try again"` in `brand-grey-dark`.

### Active Version Row (below tabs, always visible)
- Play button + filename + duration + date
- "Active" badge: `background: rgba(176,83,87,0.10)`, `color: #B05357` (gum)
- "Version history" expand → last 3 versions, each with play + "Make active"
- **"Make active" is disabled when `campaignStatus === 'live'`** — tooltip: `"Pause the campaign to change audio"`

### Mobile Layout (< 768px)
- Tab row: `overflow-x: auto`, `white-space: nowrap` — tabs scroll horizontally rather than wrapping
- Tab minimum touch target: `min-height: 44px`
- Mic circle button: remains `50px` (already sufficient touch target)
- Upload drag-and-drop: on mobile, tap to open file picker (drag is desktop-only; the zone still renders but shows "Tap to choose a file")

### Accessibility
- Tab buttons: use `role="tab"` with `aria-selected`, `aria-controls` pointing to panel `id`. **Keyboard nav:** left/right arrow keys move focus between tabs (WAI-ARIA tabs pattern). Tab key moves focus INTO the active panel content. `Home`/`End` jump to first/last tab.
- Waveform container: `role="status" aria-label="Recording in progress"` while in `recording` state; `aria-label="Recording stopped"` in `stopped` state; no ARIA in idle
- Record state region: `aria-live="polite"` on the error message container (`recordError`)
- Mic button: `aria-label="Start recording"` (idle) / `"Stop recording"` (recording)
- Upload zone: hidden `<input type="file" aria-label="Upload audio file" />`; zone itself `role="button" tabIndex={0}` for keyboard activation
- All interactive elements: visible focus ring, `focus:ring-2 focus:ring-brand-black`
- "Make active" disabled state: `aria-disabled="true"` + tooltip available on focus

---

## Backend: Audio MIME Types

**File:** `backend/app/api/v1/audio.py`

```python
_ALLOWED_CONTENT_TYPES = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/webm", "audio/mp4"}
```

Also add extension mapping for new types:
```python
# In upload_audio():
ext_map = {"mpeg": "mp3", "wav": "wav", "x-wav": "wav", "webm": "webm", "mp4": "m4a"}
subtype = (file.content_type or "").split("/")[-1]
ext = ext_map.get(subtype, "mp3")
```

### Live Campaign Guard on activate_audio()

```python
# After fetching the recording, before activating:
if recording.campaign_id:
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == recording.campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if campaign and campaign.status == "live":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pause the campaign before changing audio"
        )
```

---

## Toast Notifications

**Implementation:** Use `sonner` (`npm install sonner`). Mount `<Toaster />` once in `App.tsx`. All pages call `import { toast } from "sonner"` and invoke `toast("message")`. No shadcn/ui required.

For table-level mutations (invite sent, item deleted, etc.), use a non-blocking toast:
- Position: **bottom-right**, `16px` from edge
- Style: `background: #111111` (`brand-black`), `color: #FFFFFF`, `border-radius: 8px`, `padding: 10px 14px`, `font-size: 13px`
- Auto-dismiss: **2 seconds**
- No close button needed for success toasts
- **Invite modal:** on submit success, close modal immediately + show `"Invite sent to {email}"` toast

---

## Page Inventory

All pages must conform to this design system:

| Route | Key requirements |
|---|---|
| `/login` | Centred white card; `PAGE_HEADING` h1; "Forgot password?" text link (`brand-grey-dark`, underline on hover, 44px tap area) below the Sign in button |
| `/reset-password` | Public. Same card as `/login`. Step 1 email → code sent; step 2 8-digit code (`inputMode="numeric"`, `autoComplete="one-time-code"`) + new password with the policy as helper text; errors in `brand-grey-dark`; success shows a "Sign in" link |
| `/dashboard` | Stat cards 4-col desktop / 2-col mobile; campaign table with correct status chips; no green |
| `/campaigns` | Status filter tabs + search field; campaign name links to `/campaigns/:id/edit`; Resume wizard on draft rows, Edit on all others; correct status chips |
| `/campaigns/:id` | 5-tab edit view; PhoneInput in Targets; AudioSlotCard in Audio; "Make active" gated |
| `/phone-numbers` | Table + assign panel; horizontal scroll on mobile |
| `/users` | PhoneInput in invite modal; table header = `bg-page-bg`; status chip from `USER_STATUS_COLORS` (active = gum, inactive = grey); one card per user below `sm` |
| `/blocklist` | Table; horizontal scroll on mobile |
| `/call-log` | Table + filter; horizontal scroll on mobile; filter bar stacks on mobile |

---

## Empty States

All empty states must have: (1) brief explanation of why it's empty, (2) a primary action where applicable, (3) muted tone — use `brand-grey-dark` text, no large illustrations.

**Component:** `frontend/src/components/EmptyState.tsx` — one shape for all of them.

```tsx
<EmptyState title="No targets yet" description="…" icon={UserPlus} action={<button>Add Target</button>} />
<EmptyTableRow colSpan={5} title="No call sessions yet" description="…" />
```

`EmptyState` renders a centred stack: optional lucide icon (`brand-grey-light`), 13px `brand-grey-dark` title, 11px description, then the action node. `EmptyTableRow` wraps it in a `<tr>/<td colSpan>` so tables keep their header. Do not hand-roll a fourth shape.

| Page / Context | Empty message | Primary action |
|---|---|---|
| `/campaigns` — zero campaigns | `"No campaigns yet"` | `"Create campaign"` button (orange) |
| `/campaigns` — zero search matches | `"No campaigns match your search"` | None — clear the search field |
| `/campaigns/:id` targets tab — zero targets | `"No targets yet"` | `"Add Target"` (orange) + `"Import CSV"` (secondary) |
| `/dashboard` — call volume chart, no calls | `"No calls recorded yet"` | None |
| `/dashboard` — Live Campaigns table empty | `"No live campaigns"` | `"View all campaigns"` link to `/campaigns` |
| `/users` — zero users | `"No users yet"` | None — the Invite button in the header is the action |
| `/phone-numbers` — zero numbers | `"No phone numbers configured"` | `"Sync from Twilio"` button (orange) |
| `/blocklist` — zero entries | `"No blocked numbers or IP addresses"` | `"Add Entry"` button (orange, admin only) |
| `/call-log` — zero results (filtered) | `"No sessions match your filters"` | `"Clear filters"` inline link in `brand-orange` |
| `/call-log` — zero results (no filter) | `"No call sessions yet"` | None |
| AudioSlotCard — no active version | Show tab picker immediately with hint above: `"No audio yet — record, upload, or generate a script"` (11px, `brand-grey-dark`) | (tabs themselves are the action) |

---

## Tailwind Token Setup

Add to `tailwind.config.js` `theme.extend.colors`:

```js
colors: {
  'brand-orange':     '#F2542D',
  'brand-gum':        '#B05357',
  'brand-black':      '#111111',
  'brand-grey-dark':  '#53565B',
  'brand-grey-light': '#92918F',
  'page-bg':          '#F4F5F7',
  'brand-border':     '#E4E6EC',
}
```

Shape tokens live beside them, so no shape value is ever written as a bracket literal:

```js
borderRadius: { card: '10px', control: '7px', field: '8px' },
boxShadow:    { card: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)' },
```

---

## CSS Token Corrections (index.css)

```css
:root {
  --background:   0 0% 100%;       /* #FFFFFF */
  --foreground:   0 0% 7%;         /* #111111 brand-black */
  --primary:      14 89% 56%;      /* #F2542D brand-orange */
  --primary-foreground: 0 0% 100%; /* white */
  --muted:        220 14% 96%;     /* #F4F5F7 page-bg */
  --muted-foreground: 217 5% 34%;  /* #53565B brand-grey-dark */
  --border:       220 23% 92%;     /* #E4E6EC brand-border */
  --input:        220 23% 92%;     /* #E4E6EC brand-border */
  --radius:       0.5rem;          /* 8px */
}
```

### Browser-Surface Theming (index.css)

The chrome the browser draws for us is themed too, so nothing falls back to a system default that is off-palette:

```css
html      { scrollbar-color: #92918f #f4f5f7; }
::selection { background: rgba(242, 84, 45, 0.18); }
h1, h2    { text-wrap: balance; }
a:visited, nav a:visited { color: inherit; }   /* visited links never turn purple */
input, textarea, [contenteditable] { caret-color: #f2542d; }
```

---

## Token Migration — Deprecated Patterns

These shadcn/Tailwind defaults were used before this design system was locked. **Do not use them in new code.** Use the brand-token equivalent.

| ❌ Deprecated | ✅ Use instead |
|---|---|
| `bg-card` | `bg-white` |
| `bg-background` | `bg-white` (surfaces) or `bg-page-bg` (page) |
| `text-muted-foreground` | `text-brand-grey-dark` (any text below 18px) or `text-brand-grey-light` (18px+ only) |
| `border-border` | `border-brand-border` |
| `rounded-lg border bg-card shadow-sm` | `CARD_CLASS` from `styles.ts` |
| `rounded-[10px]` / `rounded-[7px]` / `rounded-[8px]` | `rounded-card` / `rounded-control` / `rounded-field` |
| `transition-all` | the property that actually animates — `transition-colors`, `transition-opacity` |
| `text-destructive` | `text-brand-grey-dark` + error icon (never orange, never red) |
| `bg-[#53565B] text-white` (table headers) | `bg-page-bg text-brand-grey-dark` |
| `text-amber-600` | `text-brand-grey-dark` |

---

## Shared class strings (styles.ts)

```ts
export const INPUT_CLASS =
  "w-full px-3 py-2 rounded-field border border-brand-border bg-white text-sm " +
  "focus:outline-none focus:ring-2 focus:ring-brand-black focus:ring-offset-0";

export const CARD_CLASS = "rounded-card bg-white border border-brand-border shadow-card";

export const LINK_BUTTON =
  "inline-flex min-h-[44px] items-center gap-1 rounded-control text-sm hover:underline " +
  FOCUS_RING;
```

- **`CARD_CLASS`** is the only way to build a white surface. Add padding and overflow at the call site (`` `${CARD_CLASS} p-5` ``); never re-type the radius, border and shadow.
- **`LINK_BUTTON`** is every text-style action in tables, table headers, filter bars and back links — Resume wizard, Edit, Manage, Assign, Remove, View all, Clear filters, `← Campaigns`. It carries the 44px hit area and the hover underline; the caller adds the colour (`text-brand-orange` for actions, `text-brand-grey-dark` for neutral ones).

---

## Success Criteria

- All 7 pages render correctly at 360px, 768px, 1024px, 1440px
- No green appears anywhere in the UI
- Phone inputs across the app accept 10-digit entry only — `+1` never typed
- Audio picker supports Record, Upload, and TTS (3 tabs, MVP)
- "Make active" is disabled on live campaigns with clear tooltip
- Backend rejects audio activation on live campaigns with HTTP 409
- A non-technical digital director can set up a campaign without a tutorial
- **Empty states implemented** for all 7 pages per the Empty States spec above — no page silently renders nothing
- **Toast system** (`shadcn useToast` + `<Toaster />`) wired up; invite success shows toast
- **iOS < 16:** AudioSlotCard auto-selects Upload tab on load
