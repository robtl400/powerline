/**
 * Tests for CSV import column-mapping and header-rewrite logic against
 * representative inputs from real-world target CSVs.
 */

import { describe, it, expect } from "vitest";
import { parseCsvHeader, remapCsvHeaders } from "@/lib/csv";

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

  it("renames a quoted header that contains a comma", () => {
    const csv =
      '"Name, Full",Title,"Phone, Primary",Location\nRep Smith,Senator,+12025551001,CA\n';
    const map = {
      name: "Name, Full",
      title: "Title",
      phone_number: "Phone, Primary",
      location: "Location",
    };
    const result = remapCsvHeaders(csv, map);
    expect(result.split("\n")[0]).toBe("name,title,phone_number,location");
  });

  it("re-quotes an unmapped header that contains a comma", () => {
    const csv = 'Name,Title,Phone,"Notes, extra"\nRep,Senator,+12025551001,none\n';
    const map = { name: "Name", title: "Title", phone_number: "Phone" };
    const result = remapCsvHeaders(csv, map);
    expect(result.split("\n")[0]).toBe('name,title,phone_number,"Notes, extra"');
  });

  it("leaves a body with quoted newlines byte-for-byte intact", () => {
    const body =
      'Rep Smith,Senator,+12025551001,"CA\nDistrict 12"\r\nRep Jones,"Rep, Jr.",+12025551002,"He said ""hi"""\n';
    const csv = "Name,Title,Phone,Location\n" + body;
    const map = { name: "Name", title: "Title", phone_number: "Phone", location: "Location" };
    const result = remapCsvHeaders(csv, map);
    expect(result).toBe("name,title,phone_number,location\n" + body);
  });

  it("preserves CRLF line endings", () => {
    const csv = "Name,Title,Phone,Location\r\nRep,Senator,+12025551001,CA\r\n";
    const map = { name: "Name", title: "Title", phone_number: "Phone", location: "Location" };
    const result = remapCsvHeaders(csv, map);
    expect(result).toBe("name,title,phone_number,location\r\nRep,Senator,+12025551001,CA\r\n");
  });
});

// \u2500\u2500 parseCsvHeader \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

describe("parseCsvHeader", () => {
  it("splits a plain header row", () => {
    expect(parseCsvHeader("name,title,phone_number").fields).toEqual([
      "name",
      "title",
      "phone_number",
    ]);
  });

  it("keeps commas inside quoted fields", () => {
    expect(parseCsvHeader('"Name, Full",Title,"Phone, Primary"').fields).toEqual([
      "Name, Full",
      "Title",
      "Phone, Primary",
    ]);
  });

  it("unescapes doubled quotes", () => {
    expect(parseCsvHeader('"He said ""hi""",Title').fields).toEqual(['He said "hi"', "Title"]);
  });

  it("trims whitespace around unquoted fields", () => {
    expect(parseCsvHeader(" name , title ").fields).toEqual(["name", "title"]);
  });

  it("stops at the first unquoted line terminator", () => {
    const text = 'name,"loc\nation"\nrow1,row2';
    const { fields, endIndex } = parseCsvHeader(text);
    expect(fields).toEqual(["name", "loc\nation"]);
    expect(text.slice(endIndex)).toBe("\nrow1,row2");
  });

  it("handles a header-only file with no line terminator", () => {
    const { fields, endIndex } = parseCsvHeader("name,title");
    expect(fields).toEqual(["name", "title"]);
    expect(endIndex).toBe("name,title".length);
  });
});
