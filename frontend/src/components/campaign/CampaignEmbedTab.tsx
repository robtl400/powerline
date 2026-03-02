import { INPUT_CLASS } from "@/lib/styles";

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
  const scriptSnippet =
`<div id="powerline-widget"></div>
<script
  src="${embedApiUrl}/static/powerline.js"
  data-campaign="${campaignId}"
  data-api-url="${embedApiUrl}"
></script>`;

  const reactSnippet =
`import { useEffect } from 'react';

export function PowerlineWidget() {
  useEffect(() => {
    const s = document.createElement('script');
    s.src = '${embedApiUrl}/static/powerline.js';
    s.dataset.campaign = '${campaignId}';
    s.dataset.apiUrl = '${embedApiUrl}';
    document.body.appendChild(s);
    return () => { s.remove(); };
  }, []);
  return <div id="powerline-widget" />;
}`;

  const previewSrcDoc = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{margin:0;display:flex;justify-content:center;align-items:flex-start;padding:24px;background:#f9fafb;min-height:100vh}</style>
</head><body>
<div id="powerline-widget"></div>
<script src="${embedApiUrl}/static/powerline.js" data-campaign="${campaignId}" data-api-url="${embedApiUrl}"></script>
</body></html>`;

  return (
    <section className="space-y-8">
      {/* API URL editor */}
      <div>
        <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">
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
            placeholder="https://yoursite.com"
          />
          <p className="text-xs text-muted-foreground mt-1">
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
            className="px-3 py-1 text-xs border border-border rounded hover:bg-muted/50 transition-colors"
          >
            {copiedSnippet === "script" ? "Copied!" : "Copy"}
          </button>
        </div>
        <pre className="bg-muted/40 rounded-md p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap border border-border">
          {scriptSnippet}
        </pre>
        <p className="text-xs text-muted-foreground mt-1">
          Add to any page. Place the script tag where you want the widget to appear.
        </p>
      </div>

      {/* React snippet */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold">React Component</p>
          <button
            onClick={() => onCopy("react", reactSnippet)}
            className="px-3 py-1 text-xs border border-border rounded hover:bg-muted/50 transition-colors"
          >
            {copiedSnippet === "react" ? "Copied!" : "Copy"}
          </button>
        </div>
        <pre className="bg-muted/40 rounded-md p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap border border-border">
          {reactSnippet}
        </pre>
      </div>

      {/* Live preview */}
      <div>
        <p className="text-sm font-semibold mb-2">Live Preview</p>
        <p className="text-xs text-muted-foreground mb-3">
          Renders the actual widget. Requires the campaign to be <strong>live</strong> and the backend URL above to be reachable.
        </p>
        <div className="rounded-md border border-border overflow-hidden bg-muted/10" style={{ height: 480 }}>
          <iframe
            srcDoc={previewSrcDoc}
            title="Widget preview"
            className="w-full h-full"
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        </div>
      </div>
    </section>
  );
}
