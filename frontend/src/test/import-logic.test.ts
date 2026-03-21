/**
 * Tests for CSV import column-mapping and CSV-rebuild logic.
 *
 * These functions live in useCampaignData.ts but are tested here in isolation
 * against representative inputs from real-world target CSVs.
 */

import { describe, it, expect } from "vitest";

// ── Replicated constants from useCampaignData (keep in sync) ─────────────────

const _FIELD_ALIASES: Record<string, string[]> = {
  name: ["name", "full name", "fullname"],
  title: ["title"],
  phone_number: ["phone", "phone_number", "phone number", "phonenumber"],
  location: ["location", "district"],
  external_id: ["external_id", "external id", "id"],
};

/**
 * Auto-map CSV headers to canonical field names.
 * Extracted from handleImportFileSelect in useCampaignData.ts.
 */
function autoMapHeaders(headers: string[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const header of headers) {
    const lower = header.toLowerCase();
    for (const [field, aliases] of Object.entries(_FIELD_ALIASES)) {
      if (aliases.includes(lower)) {
        map[field] = header;
        break;
      }
    }
  }
  return map;
}

/**
 * Rebuild CSV with canonical column names based on the column map.
 * Extracted from handleImportSubmit in useCampaignData.ts.
 */
function remapCsvHeaders(csvText: string, columnMap: Record<string, string>): string {
  const lines = csvText.replace(/^\uFEFF/, "").split(/\r?\n/);
  const originalHeaders = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));

  const colToField: Record<number, string> = {};
  for (const [field, origHeader] of Object.entries(columnMap)) {
    const idx = originalHeaders.indexOf(origHeader);
    if (idx !== -1) colToField[idx] = field;
  }

  const newHeader = originalHeaders.map((_, i) => colToField[i] ?? originalHeaders[i]).join(",");
  return [newHeader, ...lines.slice(1)].join("\n");
}

// ── normalizePhone tests ──────────────────────────────────────────────────────

describe("normalizePhone", () => {
  it("normalizes bare 10-digit number", () => {
    expect(normalizePhone("2025550142")).toBe("+12025550142");
  });

  it("normalizes E.164 +12025550142 unchanged", () => {
    expect(normalizePhone("+12025550142")).toBe("+12025550142");
  });

  it("throws for 9-digit number", () => {
    expect(() => normalizePhone("202555014")).toThrow();
  });

  it("throws for 11-digit non-US number", () => {
    expect(() => normalizePhone("44202555014")).toThrow();
  });
});

// ── autoMapHeaders ────────────────────────────────────────────────────────────

describe("autoMapHeaders", () => {
  it("maps canonical headers directly", () => {
    const result = autoMapHeaders(["name", "title", "phone_number", "location"]);
    expect(result).toEqual({
      name: "name",
      title: "title",
      phone_number: "phone_number",
      location: "location",
    });
  });

  it("maps alias: 'Phone Number' → phone_number", () => {
    const result = autoMapHeaders(["Name", "Title", "Phone Number", "Location"]);
    expect(result.phone_number).toBe("Phone Number");
    expect(result.name).toBe("Name");
    expect(result.location).toBe("Location");
  });

  it("maps alias: 'District' → location", () => {
    const result = autoMapHeaders(["name", "title", "phone", "district"]);
    expect(result.location).toBe("district");
    expect(result.phone_number).toBe("phone");
  });

  it("maps alias: 'Full Name' → name", () => {
    const result = autoMapHeaders(["Full Name", "Title", "Phone", "Location"]);
    expect(result.name).toBe("Full Name");
  });

  it("maps alias: 'external id' → external_id", () => {
    const result = autoMapHeaders(["name", "title", "phone_number", "location", "external id"]);
    expect(result.external_id).toBe("external id");
  });

  it("leaves unknown headers unmapped", () => {
    const result = autoMapHeaders(["name", "title", "phone_number", "location", "notes"]);
    expect(result.notes).toBeUndefined();
  });

  it("returns empty map for empty headers", () => {
    expect(autoMapHeaders([])).toEqual({});
  });
});

// ── normalizePhone ────────────────────────────────────────────────────────────
// Mirrors CSV phone normalization that should happen before import submission.

function normalizePhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`;
  throw new Error(`Invalid phone number: ${raw}`);
}

// ── remapCsvHeaders ───────────────────────────────────────────────────────────

describe("remapCsvHeaders", () => {
  it("renames 'Phone Number' to 'phone_number' in header", () => {
    const csv = "Name,Title,Phone Number,Location\nRep Smith,Senator,+12025551001,CA\n";
    const map = { name: "Name", title: "Title", phone_number: "Phone Number", location: "Location" };
    const result = remapCsvHeaders(csv, map);
    const firstLine = result.split("\n")[0];
    expect(firstLine).toBe("name,title,phone_number,location");
  });

  it("preserves data rows unchanged", () => {
    const csv = "Phone,Name,Title,Location\n+12025551001,Rep Smith,Senator,CA\n";
    const map = { phone_number: "Phone", name: "Name", title: "Title", location: "Location" };
    const result = remapCsvHeaders(csv, map);
    const lines = result.split("\n");
    expect(lines[1]).toBe("+12025551001,Rep Smith,Senator,CA");
  });

  it("keeps unmapped columns with their original name", () => {
    const csv = "name,title,phone_number,location,notes\nRep,Senator,+12025551001,CA,some note\n";
    const map = { name: "name", title: "title", phone_number: "phone_number", location: "location" };
    const result = remapCsvHeaders(csv, map);
    expect(result.split("\n")[0]).toBe("name,title,phone_number,location,notes");
  });

  it("strips UTF-8 BOM before processing", () => {
    const csv = "\uFEFFname,title,phone_number,location\nRep,Senator,+12025551001,CA\n";
    const map = { name: "name", title: "title", phone_number: "phone_number", location: "location" };
    const result = remapCsvHeaders(csv, map);
    expect(result.startsWith("\uFEFF")).toBe(false);
    expect(result.split("\n")[0]).toBe("name,title,phone_number,location");
  });
});
