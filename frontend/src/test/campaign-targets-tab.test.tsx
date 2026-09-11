/**
 * CampaignTargetsTab: the detail response caps how many targets come back, so
 * the tab has to say when the list on screen is only part of the campaign.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { CampaignTargetsTab } from "@/components/campaign/CampaignTargetsTab";
import { emptyTargetForm, type Target } from "@/types/campaign";

function target(id: string, order: number): Target {
  return {
    id,
    name: `Target ${order}`,
    title: "Senator",
    phone_number: "+12025550100",
    location: "WA",
    external_id: null,
    target_metadata: {},
    order,
  };
}

function renderTab(props: { targets: Target[]; targetsTotal: number }) {
  return render(
    <CampaignTargetsTab
      targets={props.targets}
      targetsTotal={props.targetsTotal}
      addingTarget={false}
      setAddingTarget={vi.fn()}
      targetForm={emptyTargetForm()}
      setTargetForm={vi.fn()}
      targetError={null}
      setTargetError={vi.fn()}
      editingTarget={null}
      setEditingTarget={vi.fn()}
      editTargetForm={emptyTargetForm()}
      setEditTargetForm={vi.fn()}
      handleAddTarget={vi.fn()}
      handleDeleteTarget={vi.fn()}
      pendingDeleteTarget={null}
      cancelDeleteTarget={vi.fn()}
      confirmDeleteTarget={vi.fn()}
      startEditTarget={vi.fn()}
      handleSaveTargetEdit={vi.fn()}
      handleDragEnd={vi.fn()}
      sensors={[]}
      importOpen={false}
      setImportOpen={vi.fn()}
      importFile={null}
      importHeaders={[]}
      importColumnMap={{}}
      setImportColumnMap={vi.fn()}
      importLoading={false}
      importResult={null}
      importError={null}
      handleImportFileSelect={vi.fn()}
      handleImportSubmit={vi.fn()}
      handleDownloadErrors={vi.fn()}
      resetImport={vi.fn()}
    />
  );
}

describe("CampaignTargetsTab — truncated target list", () => {
  it("says how many targets are missing from the list", () => {
    renderTab({ targets: [target("t1", 0), target("t2", 1)], targetsTotal: 750 });

    const notice = screen.getByText(/Showing the first 2 of 750 targets/);
    expect(notice).toBeInTheDocument();
    expect(notice.textContent).toContain("748");
  });

  it("stays quiet when the whole campaign is on screen", () => {
    renderTab({ targets: [target("t1", 0), target("t2", 1)], targetsTotal: 2 });

    expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument();
  });
});
