/**
 * CampaignTabs: WAI-ARIA tab semantics for the campaign edit strip and
 * arrow-key movement between tabs.
 */

import { describe, it, expect } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { CampaignTabs, type CampaignTab } from "@/components/campaign/CampaignTabs";

function Harness() {
  const [tab, setTab] = useState<CampaignTab>("settings");
  return <CampaignTabs activeTab={tab} onChange={setTab} />;
}

describe("CampaignTabs", () => {
  it("renders a tablist of five tabs with the active one selected", () => {
    render(<Harness />);

    expect(screen.getByRole("tablist")).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(5);
    expect(tabs.map((t) => t.textContent)).toEqual([
      "settings",
      "targets",
      "audio",
      "embed",
      "stats",
    ]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("aria-controls", "campaign-panel-settings");
  });

  it("keeps the tabs scrollable and reachable on a narrow viewport", () => {
    render(<Harness />);

    const tablist = screen.getByRole("tablist");
    expect(tablist.className).toContain("overflow-x-auto");
    for (const tab of screen.getAllByRole("tab")) {
      expect(tab.className).toContain("min-h-[44px]");
      expect(tab.className).toContain("snap-start");
    }
  });

  it("marks the active tab with the shared orange underline and black label", () => {
    render(<Harness />);

    const [settings, targets] = screen.getAllByRole("tab");
    expect(settings.className).toContain("border-brand-orange");
    expect(settings.className).toContain("text-brand-black");
    expect(targets.className).toContain("border-transparent");
  });

  it("carries no attribute nothing reads", () => {
    render(<Harness />);

    const strip = screen.getByRole("tablist").parentElement as HTMLElement;
    expect(strip).not.toHaveAttribute("data-overflow");
  });

  it("moves selection and focus with ArrowRight", () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });

    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "false");
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[1]);
  });

  it("moves focus to the first and last tab with Home and End", () => {
    render(<Harness />);
    const tablist = screen.getByRole("tablist");

    fireEvent.keyDown(tablist, { key: "End" });
    let tabs = screen.getAllByRole("tab");
    expect(tabs[4]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[4]);

    fireEvent.keyDown(tablist, { key: "Home" });
    tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("wraps backwards with ArrowLeft and takes focus with it", () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowLeft" });

    const tabs = screen.getAllByRole("tab");
    expect(tabs[4]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs[4]);
  });
});
