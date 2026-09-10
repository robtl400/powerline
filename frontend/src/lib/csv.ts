/**
 * Minimal RFC 4180 helpers for the target-import CSV header row.
 *
 * Only the header is ever parsed or rewritten — data rows are passed through
 * byte-for-byte so quoted commas, quoted newlines and escaped quotes in the
 * body reach the backend exactly as the user's file had them.
 */

/**
 * Parse the first CSV record of `text`.
 * Returns the header fields plus the index at which the header record ends
 * (the first line terminator that is not inside a quoted field, or the end of
 * the text when the file has a single line).
 */
export function parseCsvHeader(text: string): { fields: string[]; endIndex: number } {
  const fields: string[] = [];
  let current = "";
  let quoted = false;
  let inQuotes = false;
  let i = 0;

  const push = () => {
    fields.push(quoted ? current : current.trim());
    current = "";
    quoted = false;
  };

  for (; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      quoted = true;
      continue;
    }
    if (ch === ",") {
      push();
      continue;
    }
    if (ch === "\n" || ch === "\r") break;
    current += ch;
  }
  push();

  return { fields, endIndex: i };
}

/** Quote a header field only when RFC 4180 requires it. */
export function csvEscapeField(field: string): string {
  if (/[",\r\n]/.test(field)) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

/**
 * Rewrite the header row of `csvText` so mapped columns carry their canonical
 * field name. Everything after the header record is copied verbatim.
 */
export function remapCsvHeaders(
  csvText: string,
  columnMap: Record<string, string>
): string {
  const text = csvText.replace(/^\uFEFF/, "");
  const { fields, endIndex } = parseCsvHeader(text);

  const colToField: Record<number, string> = {};
  for (const [field, origHeader] of Object.entries(columnMap)) {
    const idx = fields.indexOf(origHeader);
    if (idx !== -1) colToField[idx] = field;
  }

  const newHeader = fields
    .map((header, i) => csvEscapeField(colToField[i] ?? header))
    .join(",");

  return newHeader + text.slice(endIndex);
}
