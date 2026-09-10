/**
 * Page tests for CallLog: the session table, the filter query string sent to
 * the API, paging through skip/limit, and the CSV export download.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    useParams: () => ({ id: "campaign-1" }),
  };
});

import CallLog from "@/pages/CallLog";

const ROWS = [
  {
    id: "s1",
    created_at: "2026-02-01T15:04:00Z",
    connection_type: "webrtc",
    status: "completed",
    call_count: 3,
    duration: 128,
  },
  {
    id: "s2",
    created_at: "2026-02-01T16:20:00Z",
    connection_type: "outbound_phone",
    status: "failed",
    call_count: 0,
    duration: null,
  },
];

let total = 2;

/** Query strings of every /calls request, oldest first. */
function callsQueries(): string[] {
  return mockClient.get.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes("/calls?"))
    .map((url) => url.split("?")[1]);
}

function lastCallsQuery(): URLSearchParams {
  const queries = callsQueries();
  return new URLSearchParams(queries[queries.length - 1]);
}

async function renderCallLog() {
  const result = render(
    <MemoryRouter>
      <CallLog />
    </MemoryRouter>
  );
  await screen.findByRole("heading", { name: "Call Log" });
  await waitFor(() => expect(callsQueries().length).toBeGreaterThan(0));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  total = 2;
  mockClient.get.mockImplementation((url: string) => {
    if (url.includes("/calls/export"))
      return Promise.resolve({ data: new Blob(["id\n"]) });
    if (url.includes("/calls?"))
      return Promise.resolve({ data: { total, items: ROWS } });
    return Promise.resolve({ data: { id: "campaign-1", name: "Senate Push" } });
  });
});

describe("CallLog — table", () => {
  it("renders a row per session", async () => {
    await renderCallLog();

    await waitFor(() => expect(screen.getByText("2 sessions")).toBeInTheDocument());
    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("webrtc")).toBeInTheDocument();
    expect(within(rows[0]).getByText("completed")).toBeInTheDocument();
    expect(within(rows[0]).getByText("3")).toBeInTheDocument();
    expect(within(rows[0]).getByText("128s")).toBeInTheDocument();
    expect(within(rows[1]).getByText("—")).toBeInTheDocument();
    expect(screen.getByText("← Senate Push")).toBeInTheDocument();
  });

  it("shows the empty state when nothing matches", async () => {
    mockClient.get.mockImplementation((url: string) =>
      url.includes("/calls?")
        ? Promise.resolve({ data: { total: 0, items: [] } })
        : Promise.resolve({ data: { id: "campaign-1", name: "Senate Push" } })
    );

    await renderCallLog();

    expect(await screen.findByText("No call sessions yet")).toBeInTheDocument();
  });

  it("reports a load failure", async () => {
    mockClient.get.mockImplementation((url: string) =>
      url.includes("/calls?")
        ? Promise.reject(new Error("500"))
        : Promise.resolve({ data: { id: "campaign-1", name: "Senate Push" } })
    );

    await renderCallLog();

    expect(await screen.findByText("Failed to load call log.")).toBeInTheDocument();
  });
});

describe("CallLog — filters", () => {
  it("starts with just the page window", async () => {
    await renderCallLog();

    const params = lastCallsQuery();
    expect(params.get("limit")).toBe("50");
    expect(params.get("skip")).toBe("0");
    expect(params.get("status")).toBeNull();
    expect(params.get("connection_type")).toBeNull();
  });

  it("adds every active filter to the query", async () => {
    await renderCallLog();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "completed" },
    });
    fireEvent.change(screen.getByLabelText("Type"), {
      target: { value: "outbound_phone" },
    });
    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-01-01" },
    });
    fireEvent.change(screen.getByLabelText("To"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const params = lastCallsQuery();
      expect(params.get("status")).toBe("completed");
      expect(params.get("connection_type")).toBe("outbound_phone");
      expect(params.get("start")).toBe("2026-01-01");
      expect(params.get("end")).toBe("2026-02-01");
      expect(params.get("skip")).toBe("0");
      expect(params.get("limit")).toBe("50");
    });
  });

  it("drops the filters again on Clear", async () => {
    await renderCallLog();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "failed" },
    });
    await waitFor(() => expect(lastCallsQuery().get("status")).toBe("failed"));

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() => expect(lastCallsQuery().get("status")).toBeNull());
    expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe("");
  });
});

describe("CallLog — pagination", () => {
  it("advances and rewinds the skip window", async () => {
    total = 120;
    await renderCallLog();

    const next = await screen.findByRole("button", { name: "Next →" });
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "← Previous" })).toBeDisabled();

    fireEvent.click(next);

    await waitFor(() => expect(lastCallsQuery().get("skip")).toBe("50"));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));

    await waitFor(() => expect(lastCallsQuery().get("skip")).toBe("0"));
  });

  it("hides the pager for a single page", async () => {
    await renderCallLog();

    expect(screen.queryByRole("button", { name: "Next →" })).not.toBeInTheDocument();
  });
});

describe("CallLog — CSV export", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let clicked: { href: string | null; download: string } | null;
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    clicked = null;
    createObjectURL = vi.fn(() => "blob:calls");
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
        clicked = { href: this.getAttribute("href"), download: this.download };
      });
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it("downloads a filtered CSV", async () => {
    await renderCallLog();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "completed" },
    });
    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-01-01" },
    });
    await waitFor(() => expect(lastCallsQuery().get("status")).toBe("completed"));

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(clicked).not.toBeNull());

    const exportCall = mockClient.get.mock.calls.find(([url]) =>
      String(url).includes("/calls/export")
    )!;
    const params = new URLSearchParams(String(exportCall[0]).split("?")[1]);
    expect(String(exportCall[0])).toContain("/campaigns/campaign-1/calls/export");
    expect(params.get("status")).toBe("completed");
    expect(params.get("start")).toBe("2026-01-01");
    expect(params.get("limit")).toBeNull();
    expect(exportCall[1]).toEqual({ responseType: "blob" });

    expect(clicked!.href).toBe("blob:calls");
    expect(clicked!.download).toBe("calls-campaign-1.csv");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:calls");
  });

  it("reports an export failure", async () => {
    await renderCallLog();
    mockClient.get.mockImplementation((url: string) =>
      url.includes("/calls/export")
        ? Promise.reject(new Error("timeout"))
        : Promise.resolve({ data: { total, items: ROWS } })
    );

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(await screen.findByText("CSV export failed.")).toBeInTheDocument();
    expect(clicked).toBeNull();
  });
});
