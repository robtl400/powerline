/**
 * Unit tests for PhoneFallbackClient — the "we'll call you" path.
 *
 * An empty number must never reach the backend, and the opaque rep_token from a
 * representative lookup has to survive the switch from WebRTC to phone callback.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createCall } from "./api.js";
import { PhoneFallbackClient } from "./phone-fallback.js";

vi.mock("./api.js", () => ({
  createCall: vi.fn(async () => ({ session_id: "s-1", status: "queued" })),
}));

const mockCreateCall = vi.mocked(createCall);

describe("PhoneFallbackClient", () => {
  let onStateChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onStateChange = vi.fn();
    mockCreateCall.mockReset();
    mockCreateCall.mockResolvedValue({ session_id: "s-1", status: "queued" });
  });

  it("rejects an empty number without calling the backend", async () => {
    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange
    );

    await client.submit("");

    expect(onStateChange).toHaveBeenCalledWith(
      "error",
      "Please enter a phone number."
    );
    expect(mockCreateCall).not.toHaveBeenCalled();
  });

  it("rejects a whitespace-only number without calling the backend", async () => {
    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange
    );

    await client.submit("   ");

    expect(onStateChange).toHaveBeenCalledWith(
      "error",
      "Please enter a phone number."
    );
    expect(mockCreateCall).not.toHaveBeenCalled();
  });

  it("shows loading then phone_pending on success", async () => {
    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange
    );

    await client.submit("  +15555550123  ");

    expect(mockCreateCall).toHaveBeenCalledWith(
      "http://localhost",
      "campaign-1",
      "+15555550123",
      undefined
    );
    expect(onStateChange.mock.calls.map(([state]) => state)).toEqual([
      "loading",
      "phone_pending",
    ]);
  });

  it("surfaces the backend message when the call cannot be placed", async () => {
    mockCreateCall.mockRejectedValueOnce(new Error("Daily call limit reached"));

    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange
    );

    await client.submit("+15555550123");

    expect(onStateChange).toHaveBeenLastCalledWith(
      "error",
      "Daily call limit reached"
    );
  });

  it("falls back to a generic message for a non-Error rejection", async () => {
    mockCreateCall.mockRejectedValueOnce("boom");

    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange
    );

    await client.submit("+15555550123");

    expect(onStateChange).toHaveBeenLastCalledWith(
      "error",
      "Could not place the call. Please try again."
    );
  });

  it("forwards the selected representative token", async () => {
    const client = new PhoneFallbackClient(
      "http://localhost",
      "campaign-1",
      onStateChange,
      "rep-token-abc"
    );

    await client.submit("+15555550123");

    expect(mockCreateCall).toHaveBeenCalledWith(
      "http://localhost",
      "campaign-1",
      "+15555550123",
      "rep-token-abc"
    );
  });
});
