import type { CampaignPublic, RepInfo, TargetPublicInfo } from "../types.js";

function esc(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
    ? `<label
         for="pl-zip-input"
         style="display:block;font-size:12px;color:#6b7280;margin-bottom:4px"
       >Your ZIP code</label>
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
         role="alert"
         aria-live="polite"
         style="font-size:12px;color:#dc2626;min-height:18px;margin-bottom:8px"
       ></div>`
    : "";

  const zipGroup = hasRepLookup
    ? `<p class="pl-subtext" style="margin-bottom:8px">
         We'll find your elected representatives based on your ZIP code.
       </p>
       ${zipInput}`
    : "";

  const phoneLink = campaign.allow_phone_callback
    ? `<div style="text-align:center;margin-top:12px">
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
      📞 Call Now
    </button>
    ${phoneLink}
  </div>`;
}

export function renderLookingUpReps(): string {
  return `<div class="pl-card" style="text-align:center">
    <div class="pl-spinner"></div>
    <p class="pl-status">Finding your representatives…</p>
  </div>`;
}

export function renderRepSelection(reps: RepInfo[], message?: string): string {
  const notice = `<p class="pl-subtext" style="margin-bottom:12px">${esc(message ?? "Select a representative to connect your call.")}</p>`;

  let items: string;

  if (reps.length === 0) {
    items = `<p class="pl-subtext" style="margin:12px 0">
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
        const header = `<p style="font-size:11px;font-weight:600;letter-spacing:0.07em;color:#9ca3af;text-transform:uppercase;margin:8px 0 6px">${esc(levelLabel[level] ?? level)}</p>`;
        const buttons = groups[level]
          .map(
            (r) => `
          <button
            class="pl-btn"
            style="width:100%;text-align:left;margin-bottom:8px;padding:10px 12px;min-height:44px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;display:flex;flex-direction:column;justify-content:center"
            data-pl-action="select-rep"
            data-pl-phone="${esc(r.phone)}"
            data-pl-name="${esc(r.name)}"
            data-pl-title="${esc(r.title)}"
          >
            <strong style="display:block;font-size:14px">📞 Call ${esc(r.name)}</strong>
            <span style="font-size:12px;color:#6b7280">${esc(r.title)}</span>
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
    <div style="max-height:280px;overflow-y:auto;margin-top:4px">${items}</div>
    <div style="text-align:center;margin-top:12px">
      <button class="pl-btn pl-btn-ghost" data-pl-action="back-to-idle">&larr; Back</button>
    </div>
  </div>`;
}

export function renderLoading(message = "Connecting…"): string {
  return `<div class="pl-card" style="text-align:center">
    <div class="pl-spinner"></div>
    <p class="pl-status">${esc(message)}</p>
  </div>`;
}

export function renderMicPermission(): string {
  return `<div class="pl-card" style="text-align:center">
    <p style="font-size:32px;margin:0 0 8px">🎙️</p>
    <p class="pl-heading">Microphone Access</p>
    <p class="pl-subtext">
      Your browser will ask for microphone permission. Please click <strong>Allow</strong>
      so we can connect you.
    </p>
  </div>`;
}

export function renderAudioCheck(campaignId: string, baseUrl: string): string {
  void campaignId; void baseUrl; // reserved for future polling
  return `<div class="pl-card" style="text-align:center">
    <p style="font-size:32px;margin:0 0 8px">🔇</p>
    <p class="pl-heading">Can't hear anything?</p>
    <ul style="text-align:left;font-size:13px;color:#374151;margin:0 0 16px;padding-left:20px;line-height:1.8">
      <li>Make sure your speakers or headphones are not muted</li>
      <li>Check that the correct audio output device is selected</li>
      <li>Try refreshing the page and clicking Call Now again</li>
    </ul>
    <button class="pl-btn pl-btn-primary" data-pl-action="retry-webrtc" style="margin-bottom:10px">
      Try Again
    </button>
    <button class="pl-btn pl-btn-ghost" data-pl-action="show-phone">
      Use phone call instead
    </button>
  </div>`;
}

export function renderConnected(
  target: TargetPublicInfo,
  targetIndex: number,
  totalTargets: number,
  elapsed: number,
  talkingPoints: string | null
): string {
  const mm = Math.floor(elapsed / 60).toString().padStart(2, "0");
  const ss = (elapsed % 60).toString().padStart(2, "0");
  const tpBlock = talkingPoints
    ? `<div class="pl-talking-points">${esc(talkingPoints)}</div>`
    : "";

  return `<div class="pl-card">
    <div class="pl-progress">${progressPips(targetIndex, totalTargets)}</div>
    <p class="pl-target-name">${esc(target.name)}</p>
    <p class="pl-target-meta">${esc(target.title)}${target.location ? ` &middot; ${esc(target.location)}` : ""}</p>
    <p class="pl-status">Call ${targetIndex + 1} of ${totalTargets}</p>
    <p class="pl-timer">⏱ ${mm}:${ss}</p>
    ${tpBlock}
    <div class="pl-actions" style="margin-top:16px">
      <button class="pl-btn pl-btn-secondary" data-pl-action="skip">Skip</button>
      <button class="pl-btn pl-btn-danger" data-pl-action="end">End Call</button>
    </div>
  </div>`;
}

export function renderBetweenTargets(
  nextTarget: TargetPublicInfo,
  nextIndex: number,
  totalTargets: number
): string {
  return `<div class="pl-card" style="text-align:center">
    <div class="pl-spinner"></div>
    <p class="pl-status">Connecting to call ${nextIndex + 1} of ${totalTargets}…</p>
    <p style="font-size:13px;color:#6b7280;margin-top:4px">
      Next: ${esc(nextTarget.name)}
    </p>
  </div>`;
}

export function renderComplete(callCount: number, totalCallers?: number): string {
  const plural = callCount === 1 ? "call" : "calls";

  const callerBadge = totalCallers != null && totalCallers > 0
    ? `<p class="pl-subtext" style="margin-top:4px">
        You're among <strong>${totalCallers.toLocaleString()}</strong> people making calls.
       </p>`
    : "";

  const shareText = encodeURIComponent(
    "I just called my representatives to make my voice heard. You can too!"
  );
  const shareUrl = encodeURIComponent(globalThis.location?.href ?? "");
  const twitterUrl = `https://twitter.com/intent/tweet?text=${shareText}&url=${shareUrl}`;

  return `<div class="pl-card" style="text-align:center">
    <div class="pl-complete-icon">✅</div>
    <p class="pl-heading">Thank you!</p>
    <p class="pl-subtext">
      You made ${callCount} ${plural}. Your voice matters — keep it up!
    </p>
    ${callerBadge}
    <div style="display:flex;gap:8px;justify-content:center;margin-top:16px;flex-wrap:wrap">
      <a
        class="pl-share-btn"
        href="${twitterUrl}"
        target="_blank"
        rel="noopener noreferrer"
      >Share on X</a>
      <button
        class="pl-share-btn"
        data-pl-action="copy-link"
        onclick="navigator.clipboard.writeText(location.href).catch(()=>{});this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Link',2000)"
      >Copy Link</button>
    </div>
  </div>`;
}

export function renderError(message: string, showRetry = true): string {
  const retry = showRetry
    ? `<button class="pl-btn pl-btn-secondary" data-pl-action="retry" style="margin-top:12px">
         Try Again
       </button>`
    : "";
  return `<div class="pl-card">
    <p class="pl-heading" style="color:#dc2626">Something went wrong</p>
    <p class="pl-error">${esc(message)}</p>
    ${retry}
  </div>`;
}

export function renderPhoneInput(campaign: CampaignPublic, message?: string): string {
  const micNotice = message === "mic_denied"
    ? `<div class="pl-callout-warning">
        🚫 Microphone access was denied — no problem! Enter your number below and we'll call you.
       </div>`
    : "";

  return `<div class="pl-card">
    ${micNotice}
    <p class="pl-heading">We'll call you</p>
    <p class="pl-subtext">
      Enter your phone number and we'll connect you to ${esc(campaign.name)}.
    </p>
    <input
      class="pl-input"
      id="pl-phone-input"
      type="tel"
      placeholder="+1 (555) 000-0000"
      autocomplete="tel"
    />
    <button class="pl-btn pl-btn-primary" data-pl-action="submit-phone">
      📞 Call Me
    </button>
    <div style="text-align:center;margin-top:10px">
      <button class="pl-btn pl-btn-ghost" data-pl-action="back-to-idle">
        ← Back
      </button>
    </div>
  </div>`;
}

export function renderPhonePending(): string {
  return `<div class="pl-card" style="text-align:center">
    <p style="font-size:32px;margin:0 0 8px">📲</p>
    <p class="pl-heading">We're calling you!</p>
    <p class="pl-subtext">
      You should receive a call shortly. Stay on the line and we'll walk you through each call.
    </p>
  </div>`;
}
