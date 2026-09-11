/**
 * Unit tests for submitPhoneFallback — the "we'll call you" path.
 *
 * An empty number must never reach the backend, and the opaque rep_token from a
 * representative lookup has to survive the switch from WebRTC to phone callback.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError, createCall } from "./api.js";
import { submitPhoneFallback } from "./phone-fallback.js";

vi.mock("./api.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api.js")>()),
  createCall: vi.fn(async () => ({ session_id: "s-1", status: "queued" })),
}));

const mockCreateCall = vi.mocked(createCall);

describe("submitPhoneFallback", () => {
  let onStateChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onStateChange = vi.fn();
    mockCreateCall.mockReset();
    mockCreateCall.mockResolvedValue({ session_id: "s-1", status: "queued" });
  });

  it("rejects an empty number without calling the backend", async () => {
    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "",
      onStateChange,
    });

    expect(onStateChange).toHaveBeenCalledWith(
      "error",
      "Please enter a phone number."
    );
    expect(mockCreateCall).not.toHaveBeenCalled();
  });

  it("rejects a whitespace-only number without calling the backend", async () => {
    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "   ",
      onStateChange,
    });

    expect(onStateChange).toHaveBeenCalledWith(
      "error",
      "Please enter a phone number."
    );
    expect(mockCreateCall).not.toHaveBeenCalled();
  });

  it("shows loading then phone_pending on success", async () => {
    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "  +15555550123  ",
      onStateChange,
    });

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

    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "+15555550123",
      onStateChange,
    });

    expect(onStateChange).toHaveBeenLastCalledWith("error", {
      message: "Daily call limit reached",
    });
  });

  it("carries the backend error code alongside the message", async () => {
    mockCreateCall.mockRejectedValueOnce(
      new ApiError("Pick a representative again", 422, "rep_token_invalid")
    );

    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "+15555550123",
      onStateChange,
    });

    expect(onStateChange).toHaveBeenLastCalledWith("error", {
      message: "Pick a representative again",
      code: "rep_token_invalid",
    });
  });

  it("falls back to a generic message for a non-Error rejection", async () => {
    mockCreateCall.mockRejectedValueOnce("boom");

    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "+15555550123",
      onStateChange,
    });

    expect(onStateChange).toHaveBeenLastCalledWith("error", {
      message: "Could not place the call. Please try again.",
    });
  });

  it("forwards the selected representative token", async () => {
    await submitPhoneFallback({
      baseUrl: "http://localhost",
      campaignId: "campaign-1",
      phoneNumber: "+15555550123",
      repToken: "rep-token-abc",
      onStateChange,
    });

    expect(mockCreateCall).toHaveBeenCalledWith(
      "http://localhost",
      "campaign-1",
      "+15555550123",
      "rep-token-abc"
    );
  });
});
