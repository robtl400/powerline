import type { CampaignPublic, TargetPublicInfo } from "../types.js";

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
    <button class="pl-btn pl-btn-primary" data-pl-action="call-now">
      📞 Call Now
    </button>
    ${phoneLink}
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
