/**
 * Tests for PhoneInput pure helper functions.
 */

import { describe, it, expect } from "vitest";
import { formatPhoneInput, toE164, validatePhone } from "@/components/PhoneInput";

describe("formatPhoneInput", () => {
  it("formats 10 digits to (XXX) XXX-XXXX", () => {
    expect(formatPhoneInput("2025551234")).toBe("(202) 555-1234");
  });

  it("formats partial: 3 digits", () => {
    expect(formatPhoneInput("202")).toBe("(202)");
  });

  it("formats partial: 6 digits", () => {
    expect(formatPhoneInput("202555")).toBe("(202) 555");
  });

  it("strips non-digits before formatting", () => {
    expect(formatPhoneInput("202-555-1234")).toBe("(202) 555-1234");
  });

  it("returns empty string for empty input", () => {
    expect(formatPhoneInput("")).toBe("");
  });

  it("truncates to 10 digits", () => {
    expect(formatPhoneInput("20255512345678")).toBe("(202) 555-1234");
  });
});

describe("toE164", () => {
  it("converts formatted number to E.164", () => {
    expect(toE164("(202) 555-1234")).toBe("+12025551234");
  });

  it("converts raw 10-digit string", () => {
    expect(toE164("2025551234")).toBe("+12025551234");
  });

  it("returns empty string when the input has no digits", () => {
    expect(toE164("")).toBe("");
    expect(toE164("()- ")).toBe("");
  });
});

describe("validatePhone", () => {
  it("accepts valid E.164 with 10 digits", () => {
    expect(validatePhone("+12025551234")).toBe(true);
  });

  it("rejects 9-digit E.164", () => {
    expect(validatePhone("+1202555123")).toBe(false);
  });

  it("rejects 11-digit E.164", () => {
    expect(validatePhone("+120255512345")).toBe(false);
  });

  it("rejects missing +1 prefix", () => {
    expect(validatePhone("2025551234")).toBe(false);
  });
});

describe("paste handling simulation", () => {
  it("+12025551234 paste: strip +1, format remainder", () => {
    // Simulate the paste logic: strip +1 if 11 digits
    let pasted = "+12025551234".replace(/\D/g, ""); // "12025551234"
    if (pasted.startsWith("1") && pasted.length === 11) {
      pasted = pasted.slice(1); // "2025551234"
    }
    const formatted = formatPhoneInput(pasted);
    expect(formatted).toBe("(202) 555-1234");
    expect(toE164(formatted)).toBe("+12025551234");
  });
});
