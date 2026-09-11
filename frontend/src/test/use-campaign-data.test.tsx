/**
 * useCampaignData tests: the campaign editor's data layer.
 *
 * The optimistic writes (target levels, drag reorder) must roll back to the
 * previous value when the PATCH fails, and the CSV import has to refresh the
 * target list from the API rather than trusting its own local state.
 */

import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DragEndEvent } from "@dnd-kit/core";

const mocks = vi.hoisted(() => ({
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  navigate: vi.fn(),
}));

const mockClient = mocks.client;

vi.mock("@/api/client", () => ({ default: mocks.client }));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

import { useCampaignData } from "@/hooks/useCampaignData";
import type { CampaignDetail, Target } from "@/types/campaign";

const ID = "campaign-1";

function target(id: string, name: string, order: number): Target {
  return {
    id,
    name,
    title: "Senator",
    phone_number: "+12025550100",
    location: "WA",
    external_id: null,
    target_metadata: {},
    order,
  };
}

let campaign: CampaignDetail;

function baseCampaign(): CampaignDetail {
  return {
    id: ID,
    name: "Call Your Senator",
    description: "Internal note",
    status: "draft",
    campaign_type: "advocacy",
    language: "en-US",
    target_ordering: "in_order",
    call_maximum: 3,
    rate_limit: null,
    allow_webrtc: true,
    allow_phone_callback: true,
    lookup_validate: true,
    lookup_require_mobile: false,
    talking_points: "Be polite",
    embed_config: { target_levels: ["federal"], theme: "light" },
    targets: [target("t1", "Alpha", 0), target("t2", "Bravo", 1)],
    targets_total: 2,
  };
}

const CHECKLIST = {
  targets_configured: true,
  audio_configured: false,
  phone_number_assigned: true,
  phone_verified: false,
  talking_points_written: true,
};

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

async function mountHook(activeTab = "settings") {
  const view = renderHook(() => useCampaignData(ID, activeTab), { wrapper });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  campaign = baseCampaign();
  mockClient.get.mockImplementation((url: string) => {
    if (url === `/campaigns/${ID}`) return Promise.resolve({ data: campaign });
    if (url === `/campaigns/${ID}/checklist`)
      return Promise.resolve({ data: CHECKLIST });
    if (url === `/campaigns/${ID}/targets/import-errors`)
      return Promise.resolve({ data: new Blob(["row,error\n"]) });
    return Promise.resolve({ data: [] });
  });
  mockClient.patch.mockResolvedValue({ data: {} });
  mockClient.post.mockResolvedValue({ data: {} });
});

describe("useCampaignData — load", () => {
  it("hydrates the form, status, targets, and target levels", async () => {
    const { result } = await mountHook();

    expect(mockClient.get).toHaveBeenCalledWith(`/campaigns/${ID}`);
    expect(result.current.form).toMatchObject({
      name: "Call Your Senator",
      description: "Internal note",
      call_maximum: "3",
      rate_limit: "",
      talking_points: "Be polite",
    });
    expect(result.current.status).toBe("draft");
    expect(result.current.targets.map((t) => t.id)).toEqual(["t1", "t2"]);
    expect(result.current.targetsTotal).toBe(2);
    expect(result.current.targetLevels).toEqual(["federal"]);
    expect(result.current.error).toBeNull();
  });

  it("keeps the full target count when the response is truncated", async () => {
    campaign = { ...campaign, targets_total: 750 };

    const { result } = await mountHook();

    expect(result.current.targets).toHaveLength(2);
    expect(result.current.targetsTotal).toBe(750);
  });

  it("reports a load failure", async () => {
    mockClient.get.mockRejectedValue(new Error("boom"));

    const { result } = await mountHook();

    expect(result.current.error).toBe("Failed to load campaign.");
  });
});

describe("useCampaignData — target levels", () => {
  it("saves the new levels with the rest of the embed config", async () => {
    const { result } = await mountHook();

    await act(async () => {
      await result.current.handleTargetLevelsChange(["federal", "state"]);
    });

    expect(mockClient.patch).toHaveBeenCalledWith(`/campaigns/${ID}`, {
      embed_config: { theme: "light", target_levels: ["federal", "state"] },
    });
    expect(result.current.targetLevels).toEqual(["federal", "state"]);
  });

  it("applies the change optimistically and rolls it back on failure", async () => {
    let rejectPatch: (reason: unknown) => void = () => {};
    mockClient.patch.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectPatch = reject;
      })
    );

    const { result } = await mountHook();

    act(() => {
      void result.current.handleTargetLevelsChange(["state"]);
    });

    expect(result.current.targetLevels).toEqual(["state"]);

    await act(async () => {
      rejectPatch(new Error("Levels rejected"));
    });

    expect(result.current.targetLevels).toEqual(["federal"]);
    expect(result.current.error).toBe("Levels rejected");
  });
});

describe("useCampaignData — drag reorder", () => {
  const drag = { active: { id: "t2" }, over: { id: "t1" } } as DragEndEvent;

  it("persists the new order", async () => {
    const { result } = await mountHook();

    await act(async () => {
      await result.current.handleDragEnd(drag);
    });

    expect(mockClient.patch).toHaveBeenCalledWith(
      `/campaigns/${ID}/targets/reorder`,
      { target_ids: ["t2", "t1"] }
    );
    expect(result.current.targets.map((t) => t.id)).toEqual(["t2", "t1"]);
    expect(result.current.targets.map((t) => t.order)).toEqual([0, 1]);
  });

  it("reorders optimistically and restores the old order on failure", async () => {
    let rejectPatch: (reason: unknown) => void = () => {};
    mockClient.patch.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectPatch = reject;
      })
    );

    const { result } = await mountHook();

    act(() => {
      void result.current.handleDragEnd(drag);
    });

    expect(result.current.targets.map((t) => t.id)).toEqual(["t2", "t1"]);

    await act(async () => {
      rejectPatch(new Error("reorder failed"));
    });

    expect(result.current.targets.map((t) => t.id)).toEqual(["t1", "t2"]);
  });

  it("refuses to reorder a truncated target list", async () => {
    campaign = { ...campaign, targets_total: 750 };
    const { result } = await mountHook();

    await act(async () => {
      await result.current.handleDragEnd(drag);
    });

    expect(mockClient.patch).not.toHaveBeenCalled();
    expect(result.current.targets.map((t) => t.id)).toEqual(["t1", "t2"]);
    expect(result.current.targetError).toMatch(/whole target list/);
  });

  it("ignores a drop back onto the same row", async () => {
    const { result } = await mountHook();

    await act(async () => {
      await result.current.handleDragEnd({
        active: { id: "t1" },
        over: { id: "t1" },
      } as DragEndEvent);
    });

    expect(mockClient.patch).not.toHaveBeenCalled();
  });
});

describe("useCampaignData — CSV import", () => {
  /** Select a CSV file and wait for its header row to be parsed. */
  async function selectFile(
    result: { current: ReturnType<typeof useCampaignData> },
    text = "name,title,phone_number\nAlpha,Senator,+12025550100\n"
  ) {
    const file = new File([text], "targets.csv", { type: "text/csv" });
    act(() => {
      result.current.handleImportFileSelect(file);
    });
    await waitFor(() =>
      expect(result.current.importHeaders.length).toBeGreaterThan(0)
    );
  }

  it("uploads the file and refreshes targets when rows were imported", async () => {
    const { result } = await mountHook();
    await selectFile(result);

    expect(result.current.importColumnMap).toMatchObject({
      name: "name",
      title: "title",
      phone_number: "phone_number",
    });

    mockClient.post.mockResolvedValue({
      data: { imported: 2, updated: 0, errors: [] },
    });
    campaign = {
      ...campaign,
      targets: [...campaign.targets, target("t3", "Charlie", 2)],
      targets_total: 3,
    };

    await act(async () => {
      await result.current.handleImportSubmit();
    });

    const [url, body] = mockClient.post.mock.calls[0];
    expect(url).toBe(`/campaigns/${ID}/targets/import`);
    expect(body).toBeInstanceOf(FormData);
    const uploaded = (body as FormData).get("file");
    expect(uploaded).toBeInstanceOf(Blob);
    expect((uploaded as File).name).toBe("targets.csv");

    expect(result.current.importResult).toEqual({
      imported: 2,
      updated: 0,
      errors: [],
    });
    expect(result.current.targets.map((t) => t.id)).toEqual(["t1", "t2", "t3"]);
    expect(result.current.targetsTotal).toBe(3);
  });

  it("leaves the target list alone when nothing was imported", async () => {
    const { result } = await mountHook();
    await selectFile(result);

    mockClient.get.mockClear();
    mockClient.post.mockResolvedValue({
      data: { imported: 0, updated: 0, errors: [{ row: 2, error: "bad phone" }] },
    });

    await act(async () => {
      await result.current.handleImportSubmit();
    });

    expect(mockClient.get).not.toHaveBeenCalledWith(`/campaigns/${ID}`);
    expect(result.current.importResult?.errors).toHaveLength(1);
  });

  it("surfaces an import failure", async () => {
    const { result } = await mountHook();
    await selectFile(result);

    mockClient.post.mockRejectedValue(new Error("File too large"));

    await act(async () => {
      await result.current.handleImportSubmit();
    });

    expect(result.current.importError).toBe("File too large");
    expect(result.current.importLoading).toBe(false);
  });
});

describe("useCampaignData — error report download", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let clicked: { href: string | null; download: string } | null;
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    clicked = null;
    createObjectURL = vi.fn(() => "blob:report");
    revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
      writable: true,
    });
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked = {
          href: this.getAttribute("href"),
          download: this.download,
        };
      });
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it("downloads the error CSV through a blob URL", async () => {
    const { result } = await mountHook();

    act(() => {
      result.current.handleDownloadErrors();
    });

    await waitFor(() => expect(clicked).not.toBeNull());

    expect(mockClient.get).toHaveBeenCalledWith(
      `/campaigns/${ID}/targets/import-errors`,
      { responseType: "blob" }
    );
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(clicked!.href).toBe("blob:report");
    expect(clicked!.download).toBe(`import-errors-${ID}.csv`);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
  });

  it("explains an expired error report", async () => {
    const { result } = await mountHook();
    mockClient.get.mockRejectedValue(new Error("404"));

    act(() => {
      result.current.handleDownloadErrors();
    });

    await waitFor(() =>
      expect(result.current.importError).toBe(
        "Failed to download error report. The report may have expired."
      )
    );
    expect(clicked).toBeNull();
  });
});

describe("useCampaignData — test call", () => {
  it("reports the session id on success", async () => {
    const { result } = await mountHook();
    act(() => result.current.setTestPhone(" +12025550123 "));

    mockClient.post.mockResolvedValue({
      data: { session_id: "sess-9", status: "queued" },
    });

    await act(async () => {
      await result.current.handleTestCall();
    });

    expect(mockClient.post).toHaveBeenCalledWith("/calls/create", {
      campaign_id: ID,
      phone_number: "+12025550123",
    });
    expect(result.current.testCallState).toBe("success");
    expect(result.current.testCallMsg).toBe("Call initiated — session sess-9");
  });

  it("reports the failure message", async () => {
    const { result } = await mountHook();
    act(() => result.current.setTestPhone("+12025550123"));

    mockClient.post.mockRejectedValue(new Error("Number is blocklisted"));

    await act(async () => {
      await result.current.handleTestCall();
    });

    expect(result.current.testCallState).toBe("error");
    expect(result.current.testCallMsg).toBe("Number is blocklisted");
  });

  it("does nothing without a phone number", async () => {
    const { result } = await mountHook();

    await act(async () => {
      await result.current.handleTestCall();
    });

    expect(mockClient.post).not.toHaveBeenCalled();
    expect(result.current.testCallState).toBe("idle");
  });
});

describe("useCampaignData — status change", () => {
  it("applies the pending status and closes the menu", async () => {
    const { result } = await mountHook();

    act(() => {
      result.current.openStatusMenu();
      result.current.setPendingStatus("live");
    });
    expect(result.current.statusMenuOpen).toBe(true);

    await act(async () => {
      await result.current.confirmStatusChange();
    });

    expect(mockClient.patch).toHaveBeenCalledWith(`/campaigns/${ID}`, {
      status: "live",
    });
    expect(result.current.status).toBe("live");
    expect(result.current.statusMenuOpen).toBe(false);
    expect(result.current.pendingStatus).toBeNull();
  });

  it("keeps the old status and reports the error when the change is refused", async () => {
    const { result } = await mountHook();
    mockClient.patch.mockRejectedValue(new Error("Campaign has no targets"));

    act(() => {
      result.current.openStatusMenu();
      result.current.setPendingStatus("live");
    });

    await act(async () => {
      await result.current.confirmStatusChange();
    });

    expect(result.current.status).toBe("draft");
    expect(result.current.error).toBe("Campaign has no targets");
    expect(result.current.statusMenuOpen).toBe(false);
  });
});
