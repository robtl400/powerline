/**
 * AudioSlotCard: visible keyboard focus affordances on the media picker controls.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/api/client", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { AudioSlotCard } from "@/components/campaign/AudioSlotCard";

function renderCard() {
  return render(
    <AudioSlotCard
      slotKey="intro"
      label="Intro"
      hint="Played when the call connects"
      versions={[]}
      campaignId="campaign-1"
      campaignStatus="draft"
      onRefresh={vi.fn()}
    />
  );
}

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
});
