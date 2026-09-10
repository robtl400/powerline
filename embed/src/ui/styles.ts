/**
 * Inject widget CSS into the document head. Idempotent — safe to call multiple times.
 *
 * Typography: system font stack — the widget must not load third-party fonts
 * on host sites (DESIGN.md calls for DM Sans, but that's a Google Fonts
 * request we can't make from an embed running on someone else's page).
 */
export function injectStyles(): void {
  const STYLE_ID = "pl-widget-styles";
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .pl-widget {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 15px;
      line-height: 1.5;
      color: #111111;
      box-sizing: border-box;
    }
    .pl-widget *, .pl-widget *::before, .pl-widget *::after {
      box-sizing: inherit;
    }

    /* ── Layout utilities ─────────────────────────────────────────────── */
    .pl-center { text-align: center; }
    .pl-actions-row { text-align: center; margin-top: 12px; }
    .pl-mt-4 { margin-top: 4px; }
    .pl-mt-10 { margin-top: 10px; }
    .pl-mt-12 { margin-top: 12px; }
    .pl-mt-16 { margin-top: 16px; }
    .pl-mb-12 { margin-bottom: 12px; }
    .pl-my-12 { margin: 12px 0; }

    .pl-icon { vertical-align: -3px; flex-shrink: 0; }
    .pl-icon-lg { margin: 0 0 8px; }
    .pl-icon-lg .pl-icon { vertical-align: middle; }

    /* ── Card wrapper ─────────────────────────────────────────────────── */
    .pl-card {
      background: #ffffff;
      border: 1px solid #E4E6EC;
      border-radius: 10px;
      padding: 24px;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }

    .pl-card ::selection { background: rgba(242,84,45,0.18); }
    .pl-card input { caret-color: #F2542D; }
    .pl-card a:visited { color: inherit; }

    /* ── Buttons ──────────────────────────────────────────────────────── */
    .pl-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 20px;
      border-radius: 7px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: opacity 0.15s, transform 0.1s;
      text-decoration: none;
    }
    .pl-btn:hover { opacity: 0.88; }
    .pl-btn:active { transform: scale(0.97); }
    .pl-btn:disabled { opacity: 0.45; cursor: not-allowed; transform: none; }

    .pl-btn-primary {
      background: #F2542D;
      color: #fff;
      width: 100%;
    }
    .pl-btn-secondary {
      background: #ffffff;
      border: 1px solid #E4E6EC;
      color: #53565B;
    }
    .pl-btn-danger {
      background: #ffffff;
      border: 1px solid #F2542D;
      color: #F2542D;
      min-height: 44px;
    }
    .pl-btn-danger:hover { background: rgba(242,84,45,0.08); opacity: 1; }
    .pl-btn-danger:focus-visible { outline: 2px solid #111111; outline-offset: 2px; }
    .pl-btn-ghost {
      background: transparent;
      color: #53565B;
      font-weight: 400;
      font-size: 13px;
      padding: 6px 0;
    }

    /* ── Progress pill ────────────────────────────────────────────────── */
    .pl-progress {
      display: flex;
      gap: 6px;
      margin-bottom: 16px;
    }
    .pl-progress-pip {
      height: 4px;
      flex: 1;
      border-radius: 2px;
      background: #E4E6EC;
    }
    .pl-progress-pip.done { background: #B05357; }
    .pl-progress-pip.active { background: #F2542D; }

    /* ── Target info ──────────────────────────────────────────────────── */
    .pl-target-name { font-size: 18px; font-weight: 700; margin: 0 0 2px; }
    .pl-target-meta { color: #53565B; font-size: 13px; margin: 0 0 16px; }

    /* ── Timer ────────────────────────────────────────────────────────── */
    .pl-timer {
      color: #53565B;
      font-size: 13px;
      margin-bottom: 16px;
    }
    .pl-timer, .pl-status {
      font-variant-numeric: tabular-nums;
    }

    /* ── Actions row ──────────────────────────────────────────────────── */
    .pl-actions {
      display: flex;
      gap: 10px;
    }
    .pl-actions .pl-btn { flex: 1; }

    /* ── Status text ──────────────────────────────────────────────────── */
    .pl-status {
      color: #53565B;
      font-size: 13px;
      margin-top: 12px;
    }

    /* ── Spinner ──────────────────────────────────────────────────────── */
    @keyframes pl-spin { to { transform: rotate(360deg); } }
    .pl-spinner {
      width: 28px; height: 28px;
      border: 3px solid #E4E6EC;
      border-top-color: #F2542D;
      border-radius: 50%;
      animation: pl-spin 0.8s linear infinite;
      margin: 16px auto;
    }

    /* ── Talking points ───────────────────────────────────────────────── */
    .pl-talking-points {
      background: #F4F5F7;
      border-left: 3px solid #F2542D;
      border-radius: 0 8px 8px 0;
      padding: 12px 14px;
      font-size: 13px;
      color: #53565B;
      margin-top: 12px;
      white-space: pre-line;
      max-height: 120px;
      overflow-y: auto;
    }

    /* ── Phone input ──────────────────────────────────────────────────── */
    .pl-input {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid #E4E6EC;
      border-radius: 8px;
      font-size: 15px;
      margin-bottom: 12px;
      outline: none;
      transition: border-color 0.15s;
    }
    .pl-input:focus { border-color: #F2542D; }

    /* ── Field label / help text ─────────────────────────────────────── */
    .pl-label {
      display: block;
      font-size: 12px;
      color: #53565B;
      margin-bottom: 4px;
    }
    .pl-help {
      color: #53565B;
      font-size: 13px;
      margin: 0 0 8px;
    }
    .pl-error-text {
      font-size: 12px;
      color: #53565B;
      min-height: 18px;
      margin-bottom: 8px;
    }
    .pl-error-heading { color: #53565B; }

    /* ── Mic-denied / warning callout ─────────────────────────────────── */
    .pl-callout-warning {
      background: #F4F5F7;
      border: 1px solid #E4E6EC;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      color: #53565B;
      margin-bottom: 14px;
      line-height: 1.5;
    }

    /* ── Rep selection list ───────────────────────────────────────────── */
    .pl-rep-list {
      max-height: 280px;
      overflow-y: auto;
      margin-top: 4px;
    }
    .pl-rep-level {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.07em;
      color: #53565B;
      text-transform: uppercase;
      margin: 8px 0 6px;
    }
    .pl-rep-btn {
      width: 100%;
      text-align: left;
      margin-bottom: 8px;
      padding: 10px 12px;
      min-height: 44px;
      border: 1px solid #E4E6EC;
      border-radius: 7px;
      background: #fff;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .pl-rep-name {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      font-weight: 700;
    }
    .pl-rep-title { font-size: 12px; color: #53565B; }

    /* ── Plain list (troubleshooting steps, etc.) ─────────────────────── */
    .pl-list {
      text-align: left;
      font-size: 13px;
      color: #53565B;
      margin: 0 0 16px;
      padding-left: 20px;
      line-height: 1.8;
    }

    /* ── Share buttons (complete screen) ──────────────────────────────── */
    .pl-share-row {
      display: flex;
      gap: 8px;
      justify-content: center;
      margin-top: 16px;
      flex-wrap: wrap;
    }
    .pl-share-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 7px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #E4E6EC;
      background: #ffffff;
      color: #53565B;
      text-decoration: none;
      transition: background 0.15s;
    }
    .pl-share-btn:hover { background: #F4F5F7; }

    /* ── Error / complete ─────────────────────────────────────────────── */
    .pl-error { color: #53565B; font-size: 13px; margin-top: 8px; }
    .pl-complete-icon { text-align: center; margin-bottom: 12px; }
    .pl-heading { font-size: 18px; font-weight: 700; margin: 0 0 8px; }
    .pl-subtext { color: #53565B; font-size: 14px; margin: 0 0 16px; }
  `;
  document.head.appendChild(style);
}
