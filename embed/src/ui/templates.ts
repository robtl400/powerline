import type { CampaignPublic, RepInfo, TargetPublicInfo } from "../types.js";
import {
  iconBan,
  iconCheck,
  iconMic,
  iconPhone,
  iconPhoneIncoming,
  iconPhoneOff,
  iconVolumeOff,
} from "./icons.js";

function esc(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function progressPips(current: number, total: number): string {
  return Array.from({ length: total }, (_, i) => {
    const cls =
      i < current ? "done" : i === current ? "active" : "";
    return `<div class="pl-progress-pip ${cls}"></div>`;
  }).join("");
}

export function renderIdle(campaign: CampaignPublic): string {
  const hasRepLookup = (campaign.target_levels?.length ?? 0) > 0;
  const zipInput = hasRepLookup
    ? `<label for="pl-zip-input" class="pl-label">Your ZIP code</label>
       <input
         class="pl-input"
         id="pl-zip-input"
         type="text"
         inputmode="numeric"
         maxlength="5"
         placeholder="e.g. 94103"
         autocomplete="postal-code"
         aria-label="Your ZIP code"
         aria-describedby="pl-zip-error"
       />
       <div
         id="pl-zip-error"
         class="pl-error-text"
         role="alert"
         aria-live="polite"
       ></div>`
    : "";

  const zipGroup = hasRepLookup
    ? `<p class="pl-help">
         We'll find your elected representatives based on your ZIP code.
       </p>
       ${zipInput}`
    : "";

  const phoneLink = campaign.allow_phone_callback
    ? `<div class="pl-actions-row">
         <button class="pl-btn pl-btn-ghost" data-pl-action="show-phone">
           Prefer a phone call?
         </button>
       </div>`
    : "";

  return `<div class="pl-card">
    <p class="pl-heading">${esc(campaign.name)}</p>
    ${campaign.description ? `<p class="pl-subtext">${esc(campaign.description)}</p>` : ""}
    ${zipGroup}
    <button class="pl-btn pl-btn-primary" data-pl-action="call-now">
      ${iconPhone(18)}<span>Call Now</span>
    </button>
    ${phoneLink}
  </div>`;
}

export function renderLookingUpReps(): string {
  return `<div class="pl-card pl-center">
    <div class="pl-spinner"></div>
    <p class="pl-status">Finding your representatives…</p>
  </div>`;
}

export function renderRepSelection(
  reps: RepInfo[],
  message?: string | null
): string {
  const notice = `<p class="pl-subtext pl-mb-12">${esc(message ?? "Select a representative to connect your call.")}</p>`;

  let items: string;

  if (reps.length === 0) {
    items = `<p class="pl-subtext pl-my-12">
      We couldn't match your ZIP to any representatives.
      Try the Back button to re-enter your ZIP, or use the phone option below.
    </p>`;
  } else {
    // Group reps by level: federal first, then state, then others
    const order = ["federal", "state"];
    const groups: Record<string, RepInfo[]> = {};
    for (const r of reps) {
      (groups[r.level] ??= []).push(r);
    }

    const levelLabel: Record<string, string> = {
      federal: "Federal",
      state: "State",
    };

    const sections = [...order, ...Object.keys(groups).filter((l) => !order.includes(l))]
      .filter((l) => groups[l]?.length)
      .map((level) => {
        const header = `<p class="pl-rep-level">${esc(levelLabel[level] ?? level)}</p>`;
        const buttons = groups[level]
          .map(
            (r) => `
          <button
            class="pl-btn pl-rep-btn"
            data-pl-action="select-rep"
            data-pl-rep-token="${esc(r.rep_token)}"
            data-pl-name="${esc(r.name)}"
            data-pl-title="${esc(r.title)}"
          >
            <strong class="pl-rep-name">${iconPhone(16)}Call ${esc(r.name)}</strong>
            <span class="pl-rep-title">${esc(r.title)}</span>
          </button>`
          )
          .join("");
        return header + buttons;
      })
      .join("");

    items = sections;
  }

  return `<div class="pl-card">
    <p class="pl-heading">Choose who to call</p>
    ${notice}
    <div class="pl-rep-list">${items}</div>
    <div class="pl-actions-row">
      <button class="pl-btn pl-btn-ghost" data-pl-action="back-to-idle">&larr; Back</button>
    </div>
  </div>`;
}

export function renderLoading(message = "Connecting…"): string {
  return `<div class="pl-card pl-center">
    <div class="pl-spinner"></div>
    <p class="pl-status">${esc(message)}</p>
  </div>`;
}

export function renderMicPermission(): string {
  return `<div class="pl-card pl-center">
    <p class="pl-icon-lg">${iconMic(32)}</p>
    <p class="pl-heading">Microphone Access</p>
    <p class="pl-subtext">
      Your browser will ask for microphone permission. Please click <strong>Allow</strong>
      so we can connect you.
    </p>
  </div>`;
}

export function renderAudioCheck(): string {
  return `<div class="pl-card pl-center">
    <p class="pl-icon-lg">${iconVolumeOff(32)}</p>
    <p class="pl-heading">Can't hear anything?</p>
    <ul class="pl-list">
      <li>Make sure your speakers or headphones are not muted</li>
      <li>Check that the correct audio output device is selected</li>
      <li>Try refreshing the page and clicking Call Now again</li>
    </ul>
    <div class="pl-actions-stack">
      <button class="pl-btn pl-btn-primary" data-pl-action="dismiss-audio-check">
        I can hear it — go back
      </button>
      <button class="pl-btn pl-btn-secondary" data-pl-action="retry-webrtc">
        Try Again
      </button>
      <button class="pl-btn pl-btn-ghost" data-pl-action="show-phone">
        Use phone call instead
      </button>
    </div>
  </div>`;
}

export function formatElapsed(elapsed: number): string {
  const mm = Math.floor(elapsed / 60).toString().padStart(2, "0");
  const ss = (elapsed % 60).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

export function renderConnected(
  target: TargetPublicInfo,
  targetIndex: number,
  totalTargets: number,
  elapsed: number,
  talkingPoints: string | null
): string {
  const tpBlock = talkingPoints
    ? `<div class="pl-talking-points">${esc(talkingPoints)}</div>`
    : "";

  return `<div class="pl-card">
    <div class="pl-progress">${progressPips(targetIndex, totalTargets)}</div>
    <p class="pl-target-name">${esc(target.name)}</p>
    <p class="pl-target-meta">${esc(target.title)}${target.location ? ` &middot; ${esc(target.location)}` : ""}</p>
    <p class="pl-status">Call ${targetIndex + 1} of ${totalTargets}</p>
    <p class="pl-timer"><span data-pl-timer>${formatElapsed(elapsed)}</span></p>
    ${tpBlock}
    <div class="pl-actions pl-mt-16">
      <button class="pl-btn pl-btn-secondary" data-pl-action="skip">Skip</button>
      <button class="pl-btn pl-btn-danger" data-pl-action="end">${iconPhoneOff(18)}<span>End Call</span></button>
    </div>
  </div>`;
}

export function renderConnectedGeneric(elapsed: number): string {
  return `<div class="pl-card pl-center">
    <p class="pl-heading">Connected</p>
    <p class="pl-timer"><span data-pl-timer>${formatElapsed(elapsed)}</span></p>
    <div class="pl-actions pl-mt-16">
      <button class="pl-btn pl-btn-danger" data-pl-action="end">${iconPhoneOff(18)}<span>End Call</span></button>
    </div>
  </div>`;
}

export function renderComplete(callCount: number, totalCallers?: number): string {
  const plural = callCount === 1 ? "call" : "calls";

  const callerBadge = totalCallers != null && totalCallers > 0
    ? `<p class="pl-subtext pl-mt-4">
        You're among <strong>${totalCallers.toLocaleString()}</strong> people making calls.
       </p>`
    : "";

  const shareText = encodeURIComponent(
    "I just called my representatives to make my voice heard. You can too!"
  );
  const shareUrl = encodeURIComponent(globalThis.location?.href ?? "");
  const twitterUrl = `https://twitter.com/intent/tweet?text=${shareText}&url=${shareUrl}`;

  return `<div class="pl-card pl-center">
    <div class="pl-complete-icon">${iconCheck(40)}</div>
    <p class="pl-heading">Thank you!</p>
    <p class="pl-subtext">
      You made ${callCount} ${plural}. Your voice matters — keep it up!
    </p>
    ${callerBadge}
    <div class="pl-share-row">
      <a
        class="pl-share-btn"
        href="${twitterUrl}"
        target="_blank"
        rel="noopener noreferrer"
      >Share on X</a>
      <button
        class="pl-share-btn"
        data-pl-action="copy-link"
      >Copy Link</button>
    </div>
  </div>`;
}

export function renderError(message: string, showRetry = true): string {
  const retry = showRetry
    ? `<button class="pl-btn pl-btn-secondary pl-mt-12" data-pl-action="retry">
         Try Again
       </button>`
    : "";
  return `<div class="pl-card">
    <p class="pl-heading pl-error-heading">Something went wrong</p>
    <p class="pl-error">${esc(message)}</p>
    ${retry}
  </div>`;
}

export function renderPhoneInput(campaign: CampaignPublic, message?: string): string {
  let notice = "";
  if (message === "mic_denied") {
    notice = `<div class="pl-callout-warning">
        ${iconBan(16)} Microphone access was denied — no problem! Enter your number below and we'll call you.
       </div>`;
  } else if (message) {
    notice = `<div class="pl-callout-warning">${esc(message)}</div>`;
  }

  return `<div class="pl-card">
    ${notice}
    <p class="pl-heading">We'll call you</p>
    <p class="pl-subtext">
      Enter your phone number and we'll connect you to ${esc(campaign.name)}.
    </p>
    <label for="pl-phone-input" class="pl-label">Your phone number</label>
    <input
      class="pl-input"
      id="pl-phone-input"
      type="tel"
      placeholder="+1 (555) 000-0000"
      autocomplete="tel"
      aria-describedby="pl-phone-error"
    />
    <div
      id="pl-phone-error"
      class="pl-error-text"
      role="alert"
      aria-live="polite"
    ></div>
    <button class="pl-btn pl-btn-primary" data-pl-action="submit-phone">
      ${iconPhone(18)}<span>Call Me</span>
    </button>
    <div class="pl-actions-row">
      <button class="pl-btn pl-btn-ghost" data-pl-action="back-to-idle">
        ← Back
      </button>
    </div>
  </div>`;
}

export function renderPhonePending(): string {
  return `<div class="pl-card pl-center">
    <p class="pl-icon-lg">${iconPhoneIncoming(32)}</p>
    <p class="pl-heading">We're calling you!</p>
    <p class="pl-subtext">
      You should receive a call shortly. Stay on the line and we'll walk you through each call.
    </p>
  </div>`;
}
