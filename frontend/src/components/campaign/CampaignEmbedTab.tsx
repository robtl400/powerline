import { useEffect, useState } from "react";

import client from "@/api/client";
import { BUTTON_SECONDARY, INPUT_CLASS, SECTION_HEADING } from "@/lib/styles";

/**
 * Each preview mount boots a real widget against the backend, spending from the
 * same per-IP budget as visitors, so typing a URL settles before it remounts.
 */
const PREVIEW_DEBOUNCE_MS = 800;

export function CampaignEmbedTab({
  campaignId,
  embedApiUrl,
  setEmbedApiUrl,
  copiedSnippet,
  onCopy,
}: {
  campaignId: string;
  embedApiUrl: string;
  setEmbedApiUrl: (url: string) => void;
  copiedSnippet: string | null;
  onCopy: (key: string, text: string) => void;
}) {
  // The bundle is served with a long cache lifetime, so the snippet pins it to
  // the backend release it was generated for.
  const [version, setVersion] = useState<string | null>(null);
  const [previewApiUrl, setPreviewApiUrl] = useState(embedApiUrl);

  useEffect(() => {
    const timer = setTimeout(
      () => setPreviewApiUrl(embedApiUrl),
      PREVIEW_DEBOUNCE_MS
    );
    return () => clearTimeout(timer);
  }, [embedApiUrl]);

  useEffect(() => {
    let cancelled = false;
    client
      .get<{ status: string; version: string }>("/health")
      .then(({ data }) => {
        if (!cancelled && data?.version) setVersion(data.version);
      })
      .catch(() => {
        // An unreachable health check just means an unversioned snippet.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const scriptSrc =
    `${embedApiUrl}/static/powerline-embed.iife.js` +
    (version ? `?v=${encodeURIComponent(version)}` : "");

  const scriptSnippet =
`<div id="powerline-widget"></div>
<script
  src="${scriptSrc}"
  data-campaign="${campaignId}"
  data-api-url="${embedApiUrl}"
></script>`;

  const reactSnippet =
`import { useEffect } from 'react';

export function PowerlineWidget() {
  useEffect(() => {
    const s = document.createElement('script');
    s.src = '${scriptSrc}';
    s.dataset.campaign = '${campaignId}';
    s.dataset.apiUrl = '${embedApiUrl}';
    document.body.appendChild(s);
    return () => { s.remove(); };
  }, []);
  return <div id="powerline-widget" />;
}`;

  const previewScriptSrc =
    `${previewApiUrl}/static/powerline-embed.iife.js` +
    (version ? `?v=${encodeURIComponent(version)}` : "");

  const previewSrcDoc = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{margin:0;display:flex;justify-content:center;align-items:flex-start;padding:24px;background:#F4F5F7;min-height:100vh}</style>
</head><body>
<div id="powerline-widget"></div>
<script src="${previewScriptSrc}" data-campaign="${campaignId}" data-api-url="${previewApiUrl}"></script>
</body></html>`;

  return (
    <section className="space-y-8">
      {/* API URL editor */}
      <div>
        <h2 className={`${SECTION_HEADING} mb-4 pb-2 border-b border-brand-border`}>
          Embed Code Generator
        </h2>
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1">
            Backend URL
          </label>
          <input
            className={INPUT_CLASS}
            value={embedApiUrl}
            onChange={(e) => setEmbedApiUrl(e.target.value.replace(/\/$/, ""))}
            onBlur={() => setPreviewApiUrl(embedApiUrl)}
            placeholder="https://yoursite.com"
          />
          <p className="text-xs text-brand-grey-dark mt-1">
            The public URL of your Powerline backend. Used as the script source and API base.
          </p>
        </div>
      </div>

      {/* Script tag snippet */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold">Script Tag (recommended)</p>
          <button
            onClick={() => onCopy("script", scriptSnippet)}
            className={BUTTON_SECONDARY}
          >
            {copiedSnippet === "script" ? "Copied!" : "Copy"}
          </button>
        </div>
        <pre className="bg-page-bg rounded-card p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap border border-brand-border">
          {scriptSnippet}
        </pre>
        <p className="text-xs text-brand-grey-dark mt-1">
          Add to any page. Place the script tag where you want the widget to appear.
        </p>
      </div>

      {/* React snippet */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold">React Component</p>
          <button
            onClick={() => onCopy("react", reactSnippet)}
            className={BUTTON_SECONDARY}
          >
            {copiedSnippet === "react" ? "Copied!" : "Copy"}
          </button>
        </div>
        <pre className="bg-page-bg rounded-card p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap border border-brand-border">
          {reactSnippet}
        </pre>
      </div>

      <p className="text-xs text-brand-grey-dark">
        When a browser call starts, the widget loads a second script,{" "}
        <code className="font-mono">powerline-embed-webrtc.iife.js</code>, from
        the same <code className="font-mono">/static/</code> directory — a host
        page with a strict <code className="font-mono">script-src</code> must
        allow that origin.
      </p>

      {/* Live preview */}
      <div>
        <p className="text-sm font-semibold mb-2">Live Preview</p>
        <p className="text-xs text-brand-grey-dark mb-3">
          Renders the actual widget. Requires the campaign to be <strong>live</strong> and the backend URL above to be reachable.
        </p>
        <div className="h-[480px] rounded-card border border-brand-border overflow-hidden bg-page-bg">
          <iframe
            srcDoc={previewSrcDoc}
            title="Widget preview"
            className="w-full h-full"
            allow="microphone"
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        </div>
      </div>
    </section>
  );
}
