import { useEffect, useState } from "react";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { getErrorDetail } from "@/lib/api-error";
import { INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";
import { PhoneInput, validatePhone } from "@/components/PhoneInput";

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
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [entries, setEntries] = useState<BlocklistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [showHashField, setShowHashField] = useState(false);
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
    const hasPhone = phoneNumber.replace(/\D/g, "").length > 1;
    const hash = phoneHash.trim();
    const ip = ipAddress.trim();

    if (!hasPhone && !hash && !ip) {
      setFormError("Enter a phone number, a phone hash, or an IP address.");
      return;
    }
    if (hasPhone && !validatePhone(phoneNumber)) {
      setFormError("Enter a 10-digit US phone number");
      return;
    }

    setSaving(true);
    setFormError(null);
    try {
      const res = await client.post<BlocklistEntry>("/admin/blocklist", {
        ...(hasPhone ? { phone_number: phoneNumber } : hash ? { phone_hash: hash } : {}),
        ip_address: ip || null,
        reason: reason.trim() || null,
      });
      setEntries((prev) => [res.data, ...prev]);
      setPhoneNumber("");
      setPhoneHash("");
      setShowHashField(false);
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
        {isAdmin && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
          >
            {showForm ? "Cancel" : "+ Add Entry"}
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}

      {/* Add entry form */}
      {isAdmin && showForm && (
        <div className="rounded-md border border-border p-4 mb-6 space-y-3 bg-muted/20">
          <p className="text-sm font-medium">New blocklist entry</p>
          {formError && (
            <p className="text-xs text-destructive">{formError}</p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Phone Number
              </label>
              <PhoneInput value={phoneNumber} onChange={setPhoneNumber} />
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
            <button
              type="button"
              onClick={() => setShowHashField((v) => !v)}
              aria-expanded={showHashField}
              className="text-xs text-brand-grey-dark hover:text-brand-black"
            >
              Advanced: paste a sha256 hash instead
            </button>
            {showHashField && (
              <div className="mt-2">
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Phone Hash (sha256 hex)
                </label>
                <input
                  className={INPUT_CLASS}
                  value={phoneHash}
                  onChange={(e) => setPhoneHash(e.target.value)}
                  placeholder="64-char hex"
                />
                <p className="mt-1 text-[11px] text-brand-grey-light">
                  Used only when the phone number field is empty.
                </p>
              </div>
            )}
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
        <p className="text-sm text-brand-grey-light py-8 text-center">No blocked numbers or IP addresses</p>
      ) : (
        <div className="rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-page-bg text-brand-grey-dark">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Identifier</th>
                <th className="text-left px-4 py-2 font-semibold">Reason</th>
                <th className="text-left px-4 py-2 font-semibold">Added</th>
                {isAdmin && <th className="px-4 py-2" />}
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
                  {isAdmin && (
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => handleDelete(entry)}
                        className="text-destructive text-sm hover:underline"
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
