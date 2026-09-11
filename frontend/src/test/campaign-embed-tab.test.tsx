/**
 * CampaignEmbedTab tests: the generated snippets carry a cache-busting version
 * query taken from the backend health endpoint and degrade to a plain URL when
 * that endpoint is unreachable, and the live preview — a real widget mount that
 * spends from the visitor rate-limit budget — waits for typing to settle.
 */

import { useState } from "react";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import client from "@/api/client";
import { CampaignEmbedTab } from "@/components/campaign/CampaignEmbedTab";

vi.mock("@/api/client", () => ({
  default: { get: vi.fn() },
}));

const mockGet = vi.mocked(client.get);

const CAMPAIGN_ID = "11111111-2222-3333-4444-555555555555";
const API_URL = "https://calls.example.org";

type Props = Parameters<typeof CampaignEmbedTab>[0];

function renderTab(overrides: Partial<Props> = {}) {
  const props: Props = {
    campaignId: CAMPAIGN_ID,
    embedApiUrl: API_URL,
    setEmbedApiUrl: vi.fn(),
    copiedSnippet: null,
    onCopy: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<CampaignEmbedTab {...props} />) };
}

/** The tab as the campaign page uses it, owning the Backend URL value. */
function ControlledTab() {
  const [url, setUrl] = useState(API_URL);
  return (
    <CampaignEmbedTab
      campaignId={CAMPAIGN_ID}
      embedApiUrl={url}
      setEmbedApiUrl={setUrl}
      copiedSnippet={null}
      onCopy={vi.fn()}
    />
  );
}

function previewSrcDoc(): string {
  const iframe = document.querySelector("iframe") as HTMLIFrameElement;
  return iframe.getAttribute("srcdoc") ?? "";
}

function backendUrlInput(): HTMLElement {
  return screen.getByPlaceholderText("https://yoursite.com");
}

/** The three places the bundle URL appears: script tag, React snippet, preview. */
function bundleUrls(): string[] {
  const snippets = screen
    .getAllByText(/powerline-embed\.iife\.js/)
    .map((el) => el.textContent ?? "");
  const iframe = document.querySelector("iframe") as HTMLIFrameElement;
  const all = [...snippets, iframe.getAttribute("srcdoc") ?? ""];
  return all.flatMap((text) =>
    Array.from(text.matchAll(/[^"'\s]*powerline-embed\.iife\.js[^"'\s]*/g)).map(
      (m) => m[0]
    )
  );
}

describe("CampaignEmbedTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("pins every snippet to the backend version", async () => {
    mockGet.mockResolvedValue({ data: { status: "ok", version: "2.0.4.0" } });

    renderTab();

    await waitFor(() => {
      const urls = bundleUrls();
      expect(urls).toHaveLength(3);
      expect(
        urls.every(
          (u) => u === `${API_URL}/static/powerline-embed.iife.js?v=2.0.4.0`
        )
      ).toBe(true);
    });
    expect(mockGet).toHaveBeenCalledWith("/health");
  });

  it("asks the health endpoint once", async () => {
    mockGet.mockResolvedValue({ data: { status: "ok", version: "2.0.4.0" } });

    renderTab();

    await waitFor(() => expect(bundleUrls()[0]).toContain("?v="));
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it("escapes a version that is not URL-safe", async () => {
    mockGet.mockResolvedValue({ data: { status: "ok", version: "1.0 beta+1" } });

    renderTab();

    await waitFor(() =>
      expect(bundleUrls()[0]).toBe(
        `${API_URL}/static/powerline-embed.iife.js?v=1.0%20beta%2B1`
      )
    );
  });

  it("falls back to an unversioned URL when health fails", async () => {
    mockGet.mockRejectedValue(new Error("offline"));

    renderTab();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    const urls = bundleUrls();
    expect(urls).toHaveLength(3);
    expect(
      urls.every((u) => u === `${API_URL}/static/powerline-embed.iife.js`)
    ).toBe(true);
  });

  it("names the companion bundle a strict script-src has to allow", () => {
    mockGet.mockReturnValue(new Promise<never>(() => {}));

    renderTab();

    expect(
      screen.getByText("powerline-embed-webrtc.iife.js")
    ).toBeInTheDocument();
  });
});

describe("CampaignEmbedTab live preview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReturnValue(new Promise<never>(() => {}));
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("holds the preview while the backend URL is being typed", () => {
    render(<ControlledTab />);
    const input = backendUrlInput();

    fireEvent.change(input, { target: { value: "https://a.example.org" } });
    fireEvent.change(input, { target: { value: "https://ab.example.org" } });
    act(() => void vi.advanceTimersByTime(799));

    expect(previewSrcDoc()).toContain(API_URL);
    expect(previewSrcDoc()).not.toContain("ab.example.org");
    expect((input as HTMLInputElement).value).toBe("https://ab.example.org");
  });

  it("remounts the preview once after typing settles", () => {
    render(<ControlledTab />);
    const input = backendUrlInput();

    fireEvent.change(input, { target: { value: "https://a.example.org" } });
    fireEvent.change(input, { target: { value: "https://ab.example.org" } });
    act(() => void vi.advanceTimersByTime(800));

    const settled = previewSrcDoc();
    expect(settled).toContain("https://ab.example.org");
    expect(settled).not.toContain(API_URL);
    expect(settled).not.toContain("https://a.example.org/");
  });

  it("updates the preview as soon as the field loses focus", () => {
    render(<ControlledTab />);
    const input = backendUrlInput();

    fireEvent.change(input, { target: { value: "https://b.example.org" } });
    fireEvent.blur(input);

    expect(previewSrcDoc()).toContain("https://b.example.org");
  });
});

describe("CampaignEmbedTab — preview permissions", () => {
  it("grants the preview iframe the microphone a browser call needs", () => {
    renderTab();

    const iframe = document.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe).toHaveAttribute("allow", "microphone");
  });
});
