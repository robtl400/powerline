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

  it("moves selection with ArrowRight", () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });

    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "false");
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
  });
});
