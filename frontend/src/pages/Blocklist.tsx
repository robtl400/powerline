import { useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { getErrorDetail } from "@/lib/api-error";
import {
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  CARD_CLASS,
  INPUT_CLASS,
  LINK_BUTTON,
  PAGE_HEADING,
} from "@/lib/styles";
import { EmptyState } from "@/components/EmptyState";
import { Modal } from "@/components/Modal";
import { PHONE_VALIDATION_MESSAGE, PhoneInput, validatePhone } from "@/components/PhoneInput";
import type { Page } from "@/types/api";

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
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
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
  const [pendingDelete, setPendingDelete] = useState<BlocklistEntry | null>(null);

  useEffect(() => {
    client
      .get<Page<BlocklistEntry>>("/admin/blocklist")
      .then((res) => {
        setEntries(res.data.items);
        setTotal(res.data.total);
      })
      .catch(() => setError("Failed to load blocklist."))
      .finally(() => setLoading(false));
  }, []);

  function loadMore() {
    setLoadingMore(true);
    client
      .get<Page<BlocklistEntry>>(`/admin/blocklist?skip=${entries.length}`)
      .then((res) => {
        setEntries((prev) => [...prev, ...res.data.items]);
        setTotal(res.data.total);
      })
      .catch(() => setError("Failed to load more blocklist entries."))
      .finally(() => setLoadingMore(false));
  }

  async function handleAdd() {
    const hasPhone = phoneNumber.replace(/\D/g, "").length > 1;
    const hash = phoneHash.trim();
    const ip = ipAddress.trim();

    if (!hasPhone && !hash && !ip) {
      setFormError("Enter a phone number, a phone hash, or an IP address.");
      return;
    }
    if (hasPhone && !validatePhone(phoneNumber)) {
      setFormError(PHONE_VALIDATION_MESSAGE);
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
      setTotal((n) => n + 1);
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

  async function handleDelete() {
    const entry = pendingDelete;
    if (!entry) return;
    setPendingDelete(null);
    try {
      await client.delete(`/admin/blocklist/${entry.id}`);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
      setTotal((n) => Math.max(0, n - 1));
    } catch {
      setError("Failed to delete entry.");
    }
  }

  if (loading) return <p className="text-brand-grey-dark">Loading…</p>;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className={PAGE_HEADING}>Blocklist</h1>
        {isAdmin && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className={BUTTON_PRIMARY}
          >
            {showForm ? "Cancel" : "+ Add Entry"}
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md border border-brand-border bg-page-bg text-brand-grey-dark text-sm">
          {error}
        </div>
      )}

      {/* Add entry form */}
      {isAdmin && showForm && (
        <div className="rounded-md border border-brand-border p-4 mb-6 space-y-3 bg-page-bg">
          <p className="text-sm font-medium">New blocklist entry</p>
          {formError && (
            <p className="text-xs text-brand-grey-dark">{formError}</p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-brand-grey-dark mb-1">
                Phone Number
              </label>
              <PhoneInput value={phoneNumber} onChange={setPhoneNumber} />
            </div>
            <div>
              <label className="block text-xs font-medium text-brand-grey-dark mb-1">
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
                <label className="block text-xs font-medium text-brand-grey-dark mb-1">
                  Phone Hash (sha256 hex)
                </label>
                <input
                  className={INPUT_CLASS}
                  value={phoneHash}
                  onChange={(e) => setPhoneHash(e.target.value)}
                  placeholder="64-char hex"
                />
                <p className="mt-1 text-[11px] text-brand-grey-dark">
                  Used only when the phone number field is empty.
                </p>
              </div>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-brand-grey-dark mb-1">
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
              className={BUTTON_PRIMARY}
            >
              {saving ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setFormError(null);
              }}
              className="px-4 py-1.5 border border-brand-border rounded-md text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {entries.length === 0 ? (
        <div className={CARD_CLASS}>
          <EmptyState
            icon={ShieldOff}
            title="No blocked numbers or IP addresses"
            description="Blocked callers are turned away before a call starts."
            action={
              isAdmin && !showForm ? (
                <button
                  onClick={() => setShowForm(true)}
                  className={BUTTON_PRIMARY}
                >
                  Add Entry
                </button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <div className={`${CARD_CLASS} overflow-x-auto`}>
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
                <tr key={entry.id} className="border-t border-brand-border bg-white">
                  <td className="px-4 py-2 font-mono text-xs">{formatIdentifier(entry)}</td>
                  <td className="px-4 py-2 text-brand-grey-dark">
                    {entry.reason ?? <span className="italic">—</span>}
                  </td>
                  <td className="px-4 py-2 text-brand-grey-dark text-xs tabular-nums">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => setPendingDelete(entry)}
                        className={`${LINK_BUTTON} px-2 text-brand-grey-dark`}
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

      {entries.length < total && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <p className="text-sm text-brand-grey-dark">
            Showing {entries.length} of {total}
          </p>
          <button onClick={loadMore} disabled={loadingMore} className={BUTTON_SECONDARY}>
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        titleId="delete-blocklist-entry-title"
        title="Remove blocklist entry"
      >
        <p className="text-sm text-brand-grey-dark mb-4">
          {pendingDelete ? formatIdentifier(pendingDelete) : ""} will no longer be blocked.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setPendingDelete(null)}
            className="px-4 py-2 border border-brand-border rounded-control text-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            className={BUTTON_PRIMARY}
          >
            Remove
          </button>
        </div>
      </Modal>
    </div>
  );
}
