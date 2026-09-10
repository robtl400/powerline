/**
 * CampaignSettingsTab tests: the read-only (staff) rendering, the launch
 * checklist, and the live-only Test Call section.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { CampaignSettingsTab } from "@/components/campaign/CampaignSettingsTab";
import { emptyForm, type CampaignChecklist } from "@/types/campaign";

type Props = Parameters<typeof CampaignSettingsTab>[0];

function renderTab(overrides: Partial<Props> = {}) {
  const props: Props = {
    form: { ...emptyForm(), name: "Call Your Senator" },
    setForm: vi.fn(),
    status: "draft",
    isNew: false,
    saving: false,
    handleSave: vi.fn(),
    statusMenuOpen: false,
    setStatusMenuOpen: vi.fn(),
    pendingStatus: null,
    setPendingStatus: vi.fn(),
    openStatusMenu: vi.fn(),
    confirmStatusChange: vi.fn(),
    nextStatuses: ["paused", "live"],
    checklist: null,
    checklistLoading: false,
    onTabChange: vi.fn(),
    onOpenTestCall: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<CampaignSettingsTab {...props} />) };
}

const CHECKLIST: CampaignChecklist = {
  targets_configured: true,
  audio_configured: false,
  phone_number_assigned: false,
  phone_verified: true,
  talking_points_written: false,
};

describe("CampaignSettingsTab — editable", () => {
  it("offers Save and Change Status", () => {
    renderTab();

    expect(
      screen.getByRole("button", { name: "Save Campaign" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Change Status" })
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("e.g. Call Your Senator")
    ).not.toBeDisabled();
  });

  it("hides Change Status for a brand-new campaign", () => {
    renderTab({ isNew: true });

    expect(
      screen.queryByRole("button", { name: "Change Status" })
    ).not.toBeInTheDocument();
  });
});

describe("CampaignSettingsTab — read only", () => {
  it("hides the write actions", () => {
    renderTab({ readOnly: true });

    expect(
      screen.queryByRole("button", { name: "Save Campaign" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Change Status" })
    ).not.toBeInTheDocument();
  });

  it("disables every field", () => {
    renderTab({ readOnly: true });

    expect(screen.getByPlaceholderText("e.g. Call Your Senator")).toBeDisabled();
    expect(
      screen.getByPlaceholderText("Optional description shown internally")
    ).toBeDisabled();
    for (const box of screen.getAllByRole("checkbox")) {
      expect(box).toBeDisabled();
    }
    for (const select of screen.getAllByRole("combobox")) {
      expect(select).toBeDisabled();
    }
  });

  it("keeps the status confirmation panel closed even when it is flagged open", () => {
    renderTab({ readOnly: true, statusMenuOpen: true });

    expect(screen.queryByText(/Choose new/)).not.toBeInTheDocument();
  });
});

describe("CampaignSettingsTab — launch checklist", () => {
  it("is hidden while the campaign is not live", () => {
    renderTab({ checklist: CHECKLIST });

    expect(screen.queryByText("Launch Checklist")).not.toBeInTheDocument();
  });

  it("marks each item and offers Fix it only for fixable failures", () => {
    renderTab({ status: "live", checklist: CHECKLIST });

    expect(screen.getByText("Launch Checklist")).toBeInTheDocument();

    const row = (label: string) => screen.getByText(label).closest("li")!;

    expect(within(row("Targets configured")).getByText("Done")).toBeInTheDocument();
    expect(within(row("Audio set")).getByText("Not ready")).toBeInTheDocument();
    expect(within(row("STIR/SHAKEN verified")).getByText("Done")).toBeInTheDocument();

    // Failed and tab-linked → fixable.
    expect(
      within(row("Audio set")).getByRole("button", { name: "Fix it" })
    ).toBeInTheDocument();
    expect(
      within(row("Talking points written")).getByRole("button", {
        name: "Fix it",
      })
    ).toBeInTheDocument();

    // Failed but no tab to send the user to → no button.
    expect(
      within(row("Phone number assigned")).queryByRole("button")
    ).toBeNull();
    // Passing → no button.
    expect(within(row("Targets configured")).queryByRole("button")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Fix it" })).toHaveLength(2);
  });

  it("sends the user to the failing tab", () => {
    const { props } = renderTab({ status: "live", checklist: CHECKLIST });

    fireEvent.click(
      within(screen.getByText("Audio set").closest("li")!).getByRole("button", {
        name: "Fix it",
      })
    );

    expect(props.onTabChange).toHaveBeenCalledWith("audio");
  });

  it("shows a placeholder while the checklist loads", () => {
    renderTab({ status: "live", checklist: null, checklistLoading: true });

    expect(screen.getByText("Checking…")).toBeInTheDocument();
  });
});

describe("CampaignSettingsTab — test call", () => {
  it("appears for a live campaign that allows phone callback", () => {
    const { props } = renderTab({
      status: "live",
      form: { ...emptyForm(), name: "C", allow_phone_callback: true },
    });

    fireEvent.click(screen.getByRole("button", { name: "Open Test Call" }));

    expect(props.onOpenTestCall).toHaveBeenCalledTimes(1);
  });

  it("is hidden when phone callback is off", () => {
    renderTab({
      status: "live",
      form: { ...emptyForm(), name: "C", allow_phone_callback: false },
    });

    expect(screen.queryByText("Test Call")).not.toBeInTheDocument();
  });

  it("is hidden while the campaign is a draft", () => {
    renderTab({
      status: "draft",
      form: { ...emptyForm(), name: "C", allow_phone_callback: true },
    });

    expect(screen.queryByText("Test Call")).not.toBeInTheDocument();
  });
});
