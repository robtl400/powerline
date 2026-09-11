/**
 * CampaignStatsTab: every control in the volume filter bar carries a visible
 * label, the same shape the call log uses.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CampaignStatsTab } from "@/components/campaign/CampaignStatsTab";
import type { CampaignStats } from "@/types/campaign";

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const STATS: CampaignStats = {
  total_sessions: 12,
  completed_sessions: 6,
  completion_rate: 0.5,
  avg_calls_per_session: 2.5,
  connection_type_breakdown: { webrtc: 8, outbound_phone: 4 },
  per_target: [],
};

type Props = Parameters<typeof CampaignStatsTab>[0];

function renderTab(overrides: Partial<Props> = {}) {
  const props: Props = {
    campaignStats: STATS,
    qualityData: null,
    chartData: [{ date: "2026-01-01", count: 3 }],
    statsLoading: false,
    statsError: null,
    statsStartDate: "2026-01-01",
    setStatsStartDate: vi.fn(),
    statsEndDate: "2026-01-31",
    setStatsEndDate: vi.fn(),
    statsGranularity: "day",
    setStatsGranularity: vi.fn(),
    onViewCallLog: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<CampaignStatsTab {...props} />) };
}

describe("CampaignStatsTab — filter bar", () => {
  it("labels the date range and interval controls", () => {
    renderTab();

    expect(screen.getByLabelText("From")).toHaveValue("2026-01-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-01-31");
    expect(screen.getByLabelText("Interval")).toHaveValue("day");
  });

  it("reports a new range through the callbacks", () => {
    const { props } = renderTab();

    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-02-01" } });
    fireEvent.change(screen.getByLabelText("Interval"), { target: { value: "week" } });

    expect(props.setStatsStartDate).toHaveBeenCalledWith("2026-02-01");
    expect(props.setStatsGranularity).toHaveBeenCalledWith("week");
  });

  it("titles the tab with the shared section heading", () => {
    renderTab();

    const heading = screen.getByRole("heading", { level: 2, name: "Campaign Analytics" });
    expect(heading.className).toContain("text-[13px]");
    expect(heading.className).toContain("text-brand-grey-dark");
  });
});
