/**
 * Powerline Embed SDK entry point.
 *
 * Usage (script tag auto-init):
 *   <div id="powerline-widget"></div>
 *   <script src="/static/powerline-embed.iife.js"
 *           data-campaign="<uuid>"
 *           data-api-url="https://api.example.com">
 *   </script>
 *
 * The widget renders into #powerline-widget when that element exists, or into
 * the element named by data-container. Otherwise it appends its own div to
 * document.body.
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

import { injectStyles } from "./ui/styles.js";
import { renderError } from "./ui/templates.js";
import { PowerlineWidget } from "./widget.js";

// ── Auto-init from script tag ─────────────────────────────────────────────

/** Element the auto-init widget renders into when the host page provides none. */
const DEFAULT_CONTAINER_ID = "powerline-widget";

// Capture currentScript at module level — it's only valid during initial
// script execution and is null inside any event listener callback.
const _initScript = document.currentScript as HTMLScriptElement | null;

/**
 * Resolve the host element for the widget: the page's own container when it
 * exists, otherwise a fresh div appended to document.body.
 */
export function resolveContainer(script: HTMLScriptElement | null): Element {
  const id = script?.dataset.container || DEFAULT_CONTAINER_ID;
  const existing = document.getElementById(id);
  if (existing) return existing;

  const created = document.createElement("div");
  document.body.appendChild(created);
  return created;
}

export function autoInit(script: HTMLScriptElement | null): void {
  const campaignId = script?.dataset.campaign;
  if (!campaignId) return;

  const container = resolveContainer(script);
  container.setAttribute("data-pl-root", campaignId);

  const apiUrl = script?.dataset.apiUrl ?? "";
  if (!apiUrl) {
    console.error("[Powerline] data-api-url is required");
    injectStyles();
    container.innerHTML = renderError(
      "This call widget is not configured yet — the embed script tag is missing its data-api-url attribute.",
      false
    );
    return;
  }

  new PowerlineWidget({ campaignId, container, apiUrl }).init();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => autoInit(_initScript));
} else {
  autoInit(_initScript);
}
