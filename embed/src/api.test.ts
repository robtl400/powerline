/**
 * Unit tests for the request bodies the embed sends to the backend.
 *
 * The widget never sees a representative's phone number — it only ever forwards
 * the opaque rep_token it was handed by the reps lookup, and omits the field
 * entirely when no representative was selected.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createCall, requestToken } from "./api.js";

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
