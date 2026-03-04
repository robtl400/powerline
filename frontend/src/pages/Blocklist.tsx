import { useEffect, useState } from "react";
import client from "@/api/client";
import { getErrorDetail } from "@/lib/api-error";
import { INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";

interface BlocklistEntry {
  id: string;
  created_at: string;
  phone_hash: string | null;
  ip_address: string | null;
  reason: string | null;
  created_by_id: string | null;
}


function formatIdentifier(entry: BlocklistEntry): string {
  if (entry.phone_hash && entry.ip_address)
    return `phone + IP`;
  if (entry.phone_hash)
    return `phone: ${entry.phone_hash.slice(0, 16)}…`;
  if (entry.ip_address)
    return `IP: ${entry.ip_address}`;
  return "—";
}

export default function Blocklist() {
  const [entries, setEntries] = useState<BlocklistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [phoneHash, setPhoneHash] = useState("");
  const [ipAddress, setIpAddress] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    client
      .get<BlocklistEntry[]>("/admin/blocklist")
      .then((res) => setEntries(res.data))
      .catch(() => setError("Failed to load blocklist."))
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd() {
    if (!phoneHash.trim() && !ipAddress.trim()) {
      setFormError("At least one of phone hash or IP address is required.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const res = await client.post<BlocklistEntry>("/admin/blocklist", {
        phone_hash: phoneHash.trim() || null,
        ip_address: ipAddress.trim() || null,
        reason: reason.trim() || null,
      });
      setEntries((prev) => [res.data, ...prev]);
      setPhoneHash("");
      setIpAddress("");
      setReason("");
      setShowForm(false);
    } catch (e: unknown) {
      setFormError(getErrorDetail(e, "Failed to add entry."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(entry: BlocklistEntry) {
    if (!confirm(`Remove this blocklist entry (${formatIdentifier(entry)})?`)) return;
    try {
      await client.delete(`/admin/blocklist/${entry.id}`);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    } catch {
      setError("Failed to delete entry.");
    }
  }

  if (loading) return <p className="text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className={PAGE_HEADING}>Blocklist</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
        >
          {showForm ? "Cancel" : "+ Add Entry"}
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}

      {/* Add entry form */}
      {showForm && (
        <div className="rounded-md border border-border p-4 mb-6 space-y-3 bg-muted/20">
          <p className="text-sm font-medium">New blocklist entry</p>
          {formError && (
            <p className="text-xs text-destructive">{formError}</p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Phone Hash (sha256 hex)
              </label>
              <input
                className={INPUT_CLASS}
                value={phoneHash}
                onChange={(e) => setPhoneHash(e.target.value)}
                placeholder="64-char hex"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                IP Address
              </label>
              <input
                className={INPUT_CLASS}
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
                placeholder="e.g. 192.168.1.1"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Reason (optional)
            </label>
            <input
              className={INPUT_CLASS}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. spam, abuse"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={saving}
              className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
            >
              {saving ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setFormError(null);
              }}
              className="px-4 py-1.5 border border-border rounded-md text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {entries.length === 0 ? (
        <p className="text-muted-foreground text-sm">No entries yet.</p>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#53565B] text-white">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Identifier</th>
                <th className="text-left px-4 py-2 font-medium">Reason</th>
                <th className="text-left px-4 py-2 font-medium">Added</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-t border-border bg-background">
                  <td className="px-4 py-2 font-mono text-xs">{formatIdentifier(entry)}</td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {entry.reason ?? <span className="italic">—</span>}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleDelete(entry)}
                      className="text-destructive text-sm hover:underline"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
