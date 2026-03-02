/**
 * Powerline Embed SDK entry point.
 *
 * Usage (script tag auto-init):
 *   <script src="/static/powerline-embed.iife.js"
 *           data-campaign="<uuid>"
 *           data-api-url="https://api.example.com">
 *   </script>
 *
 * Usage (programmatic):
 *   const widget = new Powerline.PowerlineWidget({
 *     campaignId: "<uuid>",
 *     container: document.getElementById("call-widget"),
 *     apiUrl: "https://api.example.com",
 *   });
 *   widget.init();
 */
export { PowerlineWidget } from "./widget.js";
export type { WidgetOptions } from "./widget.js";
export type { CampaignPublic, TargetPublicInfo, WidgetState } from "./types.js";

import { PowerlineWidget } from "./widget.js";

// ── Auto-init from script tag ─────────────────────────────────────────────

// Capture currentScript at module level — it's only valid during initial
// script execution and is null inside any event listener callback.
const _initScript = document.currentScript as HTMLScriptElement | null;

function autoInit(): void {
  const campaignId = _initScript?.dataset.campaign;
  const apiUrl = _initScript?.dataset.apiUrl ?? "";

  if (!campaignId) return;

  const container = document.createElement("div");
  container.setAttribute("data-pl-root", campaignId);
  document.body.appendChild(container);

  new PowerlineWidget({ campaignId, container, apiUrl }).init();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoInit);
} else {
  autoInit();
}
