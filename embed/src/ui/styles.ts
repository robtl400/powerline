/** Inject widget CSS into the document head. Idempotent — safe to call multiple times. */
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
      color: #111827;
      box-sizing: border-box;
    }
    .pl-widget *, .pl-widget *::before, .pl-widget *::after {
      box-sizing: inherit;
    }

    /* ── Card wrapper ─────────────────────────────────────────────────── */
    .pl-card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 24px;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }

    /* ── Buttons ──────────────────────────────────────────────────────── */
    .pl-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 20px;
      border-radius: 8px;
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
      background: #2563eb;
      color: #fff;
      width: 100%;
    }
    .pl-btn-secondary {
      background: #f3f4f6;
      color: #374151;
    }
    .pl-btn-danger {
      background: #dc2626;
      color: #fff;
    }
    .pl-btn-ghost {
      background: transparent;
      color: #6b7280;
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
      background: #e5e7eb;
    }
    .pl-progress-pip.done { background: #16a34a; }
    .pl-progress-pip.active { background: #2563eb; }

    /* ── Target info ──────────────────────────────────────────────────── */
    .pl-target-name { font-size: 18px; font-weight: 700; margin: 0 0 2px; }
    .pl-target-meta { color: #6b7280; font-size: 13px; margin: 0 0 16px; }

    /* ── Timer ────────────────────────────────────────────────────────── */
    .pl-timer {
      font-variant-numeric: tabular-nums;
      color: #6b7280;
      font-size: 13px;
      margin-bottom: 16px;
    }

    /* ── Actions row ──────────────────────────────────────────────────── */
    .pl-actions {
      display: flex;
      gap: 10px;
    }
    .pl-actions .pl-btn { flex: 1; }

    /* ── Status text ──────────────────────────────────────────────────── */
    .pl-status {
      color: #6b7280;
      font-size: 13px;
      margin-top: 12px;
    }

    /* ── Spinner ──────────────────────────────────────────────────────── */
    @keyframes pl-spin { to { transform: rotate(360deg); } }
    .pl-spinner {
      width: 28px; height: 28px;
      border: 3px solid #e5e7eb;
      border-top-color: #2563eb;
      border-radius: 50%;
      animation: pl-spin 0.8s linear infinite;
      margin: 16px auto;
    }

    /* ── Talking points ───────────────────────────────────────────────── */
    .pl-talking-points {
      background: #f8fafc;
      border-left: 3px solid #2563eb;
      border-radius: 0 8px 8px 0;
      padding: 12px 14px;
      font-size: 13px;
      color: #374151;
      margin-top: 12px;
      white-space: pre-line;
      max-height: 120px;
      overflow-y: auto;
    }

    /* ── Phone input ──────────────────────────────────────────────────── */
    .pl-input {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      font-size: 15px;
      margin-bottom: 12px;
      outline: none;
      transition: border-color 0.15s;
    }
    .pl-input:focus { border-color: #2563eb; }

    /* ── Mic-denied / warning callout ─────────────────────────────────── */
    .pl-callout-warning {
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      color: #92400e;
      margin-bottom: 14px;
      line-height: 1.5;
    }

    /* ── Share buttons (complete screen) ──────────────────────────────── */
    .pl-share-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #d1d5db;
      background: #f9fafb;
      color: #374151;
      text-decoration: none;
      transition: background 0.15s;
    }
    .pl-share-btn:hover { background: #f3f4f6; }

    /* ── Error / complete ─────────────────────────────────────────────── */
    .pl-error { color: #dc2626; font-size: 13px; margin-top: 8px; }
    .pl-complete-icon { font-size: 40px; text-align: center; margin-bottom: 12px; }
    .pl-heading { font-size: 18px; font-weight: 700; margin: 0 0 8px; }
    .pl-subtext { color: #6b7280; font-size: 14px; margin: 0 0 16px; }
  `;
  document.head.appendChild(style);
}
