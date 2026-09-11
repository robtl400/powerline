/**
 * CampaignEmbedTab tests: the generated snippets carry a cache-busting version
 * query taken from the backend health endpoint, and degrade to a plain URL when
 * that endpoint is unreachable.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
});
