/**
 * Unit tests for the request bodies the embed sends to the backend.
 *
 * The widget never sees a representative's phone number — it only ever forwards
 * the opaque rep_token it was handed by the reps lookup, and omits the field
 * entirely when no representative was selected.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  ApiError,
  createCall,
  fetchCallCount,
  fetchCampaign,
  fetchReps,
  isRepsError,
  requestToken,
} from "./api.js";

const originalFetch = globalThis.fetch;

function mockJsonResponse(body: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  });
}

/** Parsed JSON body of the Nth fetch call. */
function bodyOf(fetchMock: ReturnType<typeof vi.fn>, n = 0): unknown {
  const init = fetchMock.mock.calls[n][1] as RequestInit;
  return JSON.parse(init.body as string);
}

describe("requestToken", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = mockJsonResponse({ token: "t", session_id: "s" });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends rep_token when a representative was selected", async () => {
    await requestToken("http://localhost", "campaign-1", "rep-token-abc");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost/api/v1/tokens/voice"
    );
    expect(bodyOf(fetchMock)).toEqual({
      campaign_id: "campaign-1",
      rep_token: "rep-token-abc",
    });
  });

  it("omits rep_token when no representative was selected", async () => {
    await requestToken("http://localhost", "campaign-1");

    const body = bodyOf(fetchMock) as Record<string, unknown>;
    expect(body).toEqual({ campaign_id: "campaign-1" });
    expect("rep_token" in body).toBe(false);
  });
});

describe("createCall", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = mockJsonResponse({ session_id: "s", status: "queued" });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends rep_token alongside the phone number when set", async () => {
    await createCall(
      "http://localhost",
      "campaign-1",
      "+15555550123",
      "rep-token-abc"
    );

    expect(bodyOf(fetchMock)).toEqual({
      campaign_id: "campaign-1",
      phone_number: "+15555550123",
      rep_token: "rep-token-abc",
    });
  });

  it("omits rep_token when no representative was selected", async () => {
    await createCall("http://localhost", "campaign-1", "+15555550123");

    const body = bodyOf(fetchMock) as Record<string, unknown>;
    expect(body).toEqual({
      campaign_id: "campaign-1",
      phone_number: "+15555550123",
    });
    expect("rep_token" in body).toBe(false);
  });
});

describe("read endpoints", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = mockJsonResponse({ total: 12, last_24h: 3, last_7d: 9 });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("fetches the public campaign record", async () => {
    await fetchCampaign("http://localhost", "campaign-1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost/api/v1/campaigns/campaign-1/public"
    );
  });

  it("fetches the campaign call count", async () => {
    const counts = await fetchCallCount("http://localhost", "campaign-1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost/api/v1/campaigns/campaign-1/count"
    );
    expect(counts.total).toBe(12);
  });
});

describe("error handling", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  /** Non-OK response whose body parses (or not, when json throws). */
  function mockErrorResponse(
    status: number,
    statusText: string,
    json: () => Promise<unknown>
  ): void {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status,
      statusText,
      json,
    }) as unknown as typeof fetch;
  }

  it("raises the FastAPI detail from a failed request", async () => {
    mockErrorResponse(403, "Forbidden", async () => ({
      detail: "Campaign is not accepting calls",
    }));

    await expect(
      fetchCampaign("http://localhost", "campaign-1")
    ).rejects.toThrow("Campaign is not accepting calls");
  });

  it("keeps the code and the message of a structured detail", async () => {
    mockErrorResponse(422, "Unprocessable Entity", async () => ({
      detail: {
        message: "Invalid or expired representative selection",
        code: "rep_token_invalid",
      },
    }));

    const err = await requestToken("http://localhost", "campaign-1", "tok").catch(
      (e: unknown) => e
    );

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe(
      "Invalid or expired representative selection"
    );
    expect((err as ApiError).code).toBe("rep_token_invalid");
    expect((err as ApiError).status).toBe(422);
  });

  it("leaves the code unset for a plain string detail", async () => {
    mockErrorResponse(403, "Forbidden", async () => ({
      detail: "Campaign is not accepting calls",
    }));

    const err = await fetchCampaign("http://localhost", "campaign-1").catch(
      (e: unknown) => e
    );

    expect((err as ApiError).code).toBeUndefined();
  });

  it("falls back to the status text when the body is not JSON", async () => {
    mockErrorResponse(502, "Bad Gateway", async () => {
      throw new SyntaxError("Unexpected token < in JSON");
    });

    await expect(
      fetchCampaign("http://localhost", "campaign-1")
    ).rejects.toThrow("Bad Gateway");
  });
});

describe("fetchReps", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  /**
   * A Response body can only be read once, so json() here throws on a second
   * call the way fetch's own Response does.
   */
  function mockResponse(res: {
    ok: boolean;
    status: number;
    statusText?: string;
    json: () => Promise<unknown>;
  }): ReturnType<typeof vi.fn> {
    let consumed = false;
    const json = async (): Promise<unknown> => {
      if (consumed) throw new TypeError("Body has already been consumed.");
      consumed = true;
      return res.json();
    };
    const mock = vi
      .fn()
      .mockResolvedValue({ statusText: "", ...res, json });
    globalThis.fetch = mock as unknown as typeof fetch;
    return mock;
  }

  it("URL-encodes the ZIP into the reps query", async () => {
    const mock = mockResponse({
      ok: true,
      status: 200,
      json: async () => ({ reps: [], message: null }),
    });

    await fetchReps("http://localhost", "campaign-1", "94103");

    expect(mock.mock.calls[0][0]).toBe(
      "http://localhost/api/v1/campaigns/campaign-1/reps?zip=94103"
    );
  });

  it("returns the rep list on success", async () => {
    mockResponse({
      ok: true,
      status: 200,
      json: async () => ({
        reps: [
          {
            name: "Rep Example",
            title: "U.S. Representative",
            level: "federal",
            rep_token: "tok-1",
          },
        ],
        message: null,
      }),
    });

    const result = await fetchReps("http://localhost", "campaign-1", "94103");

    expect(isRepsError(result)).toBe(false);
    expect(result).toEqual({
      reps: [
        {
          name: "Rep Example",
          title: "U.S. Representative",
          level: "federal",
          rep_token: "tok-1",
        },
      ],
      message: null,
    });
  });

  it("returns a manual-entry fallback instead of throwing on 503", async () => {
    mockResponse({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: async () => ({
        detail: {
          fallback: "manual_entry",
          message: "Lookup is down — enter your number instead.",
        },
      }),
    });

    const result = await fetchReps("http://localhost", "campaign-1", "94103");

    expect(isRepsError(result)).toBe(true);
    expect(result).toEqual({
      fallback: "manual_entry",
      message: "Lookup is down — enter your number instead.",
    });
  });

  it("throws on a 503 that offers no fallback", async () => {
    mockResponse({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: async () => ({ detail: "Upstream lookup failed" }),
    });

    await expect(
      fetchReps("http://localhost", "campaign-1", "94103")
    ).rejects.toThrow("Upstream lookup failed");
  });

  it("throws the detail on any other error status", async () => {
    mockResponse({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: async () => ({ detail: "Invalid ZIP code" }),
    });

    await expect(
      fetchReps("http://localhost", "campaign-1", "0000")
    ).rejects.toThrow("Invalid ZIP code");
  });
});
