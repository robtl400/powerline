/**
 * AudioSlotCard: keyboard focus affordances on the media picker, and the
 * live-campaign lock that keeps a new take from being uploaded at all.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/api/client", () => ({ default: mocks.client }));

import { AudioSlotCard } from "@/components/campaign/AudioSlotCard";
import type { AudioRecording } from "@/types/campaign";

const mockClient = mocks.client;

const VERSIONS: AudioRecording[] = [
  {
    id: "rec-2",
    campaign_id: "campaign-1",
    key: "intro",
    version: 2,
    tts_text: "Hello there",
    file_url: null,
    description: null,
    is_active: true,
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    id: "rec-1",
    campaign_id: "campaign-1",
    key: "intro",
    version: 1,
    tts_text: "First take",
    file_url: null,
    description: null,
    is_active: false,
    created_at: "2026-01-01T00:00:00Z",
  },
];

function renderCard(
  props: { campaignStatus?: string; versions?: AudioRecording[] } = {}
) {
  return render(
    <AudioSlotCard
      slotKey="intro"
      label="Intro"
      hint="Played when the call connects"
      versions={props.versions ?? []}
      campaignId="campaign-1"
      campaignStatus={props.campaignStatus ?? "draft"}
      onRefresh={vi.fn()}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AudioSlotCard", () => {
  it("gives the record tab a visible focus ring", () => {
    renderCard();

    const recordTab = screen.getByRole("tab", { name: "Record" });
    expect(recordTab.className).toContain("focus-visible:ring-2");
  });

  it("gives the mic button and the upload drop zone a visible focus ring", () => {
    renderCard();

    expect(
      screen.getByRole("button", { name: "Start recording" }).className
    ).toContain("focus-visible:ring-2");

    fireEvent.click(screen.getByRole("tab", { name: "Upload" }));

    expect(
      screen.getByRole("button", { name: /Upload audio file/ }).className
    ).toContain("focus-visible:ring-2");
  });

  it("names the tab strip", () => {
    renderCard();
    expect(screen.getByRole("tablist")).toHaveAccessibleName("Audio source");
  });

  it("moves selection and focus with the arrow keys", () => {
    renderCard();
    const tablist = screen.getByRole("tablist");

    fireEvent.keyDown(tablist, { key: "ArrowRight" });

    let tabs = screen.getAllByRole("tab");
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[1]);

    fireEvent.keyDown(tablist, { key: "End" });
    tabs = screen.getAllByRole("tab");
    expect(tabs[2]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[2]);

    fireEvent.keyDown(tablist, { key: "Home" });
    tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[0]);
  });
});

describe("AudioSlotCard — live campaign", () => {
  it("hides the record, upload and text-to-speech picker", () => {
    renderCard({ campaignStatus: "live", versions: VERSIONS });

    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Upload" })).not.toBeInTheDocument();
    expect(screen.getByText("Pause the campaign to change audio")).toBeInTheDocument();
  });

  it("still shows the active version and the version history", () => {
    renderCard({ campaignStatus: "live", versions: VERSIONS });

    expect(screen.getByText("Active v2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Version history/ })).toBeInTheDocument();
  });

  it("disables Make active with the pause tooltip", () => {
    renderCard({ campaignStatus: "live", versions: VERSIONS });
    fireEvent.click(screen.getByRole("button", { name: /Version history/ }));

    const makeActive = screen.getByRole("button", { name: "Make active" });
    expect(makeActive).toBeDisabled();
    expect(makeActive).toHaveAttribute("title", "Pause the campaign to change audio");
  });

  it("reports the server's own reason when activation is refused", async () => {
    mockClient.patch.mockRejectedValue(
      Object.assign(new Error("Request failed"), {
        isAxiosError: true,
        response: { status: 409, data: { detail: "Pause the campaign before changing audio" } },
      })
    );
    renderCard({ campaignStatus: "paused", versions: VERSIONS });
    fireEvent.click(screen.getByRole("button", { name: /Version history/ }));

    fireEvent.click(screen.getByRole("button", { name: "Make active" }));

    await waitFor(() =>
      expect(screen.getByText("Pause the campaign before changing audio")).toBeInTheDocument()
    );
  });

  it("reports the server's own reason when a text-to-speech save is refused", async () => {
    mockClient.post.mockRejectedValue(
      Object.assign(new Error("Request failed"), {
        isAxiosError: true,
        response: { status: 409, data: { detail: "Pause the campaign before changing audio" } },
      })
    );
    renderCard({ campaignStatus: "paused" });
    fireEvent.click(screen.getByRole("tab", { name: "Text-to-Speech" }));
    fireEvent.change(screen.getByPlaceholderText("Enter text to convert to speech…"), {
      target: { value: "A new script" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save as audio" }));

    await waitFor(() =>
      expect(screen.getByText("Pause the campaign before changing audio")).toBeInTheDocument()
    );
  });
});
