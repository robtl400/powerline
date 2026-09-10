import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { getErrorDetail } from "@/lib/api-error";
import { INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";
import { PhoneInput } from "@/components/PhoneInput";

interface User {
  id: string;
  email: string;
  name: string;
  phone: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface InviteForm {
  name: string;
  email: string;
  phone: string;
  role: string;
}

const EMPTY_FORM: InviteForm = { name: "", email: "", phone: "", role: "staff" };

export default function Users() {
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser?.role === "admin";

  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteForm>(EMPTY_FORM);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [rowBusy, setRowBusy] = useState<Record<string, boolean>>({});

  useEffect(() => {
    client
      .get<User[]>("/users")
      .then((res) => setUsers(res.data))
      .catch(() => setError("Failed to load users."))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (!inviteOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setInviteOpen(false);
    }
    document.addEventListener("keydown", handleKeyDown);
    nameInputRef.current?.focus();
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [inviteOpen]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setInviteError(null);
    try {
      const res = await client.post<User>("/users", inviteForm);
      setUsers((prev) => [...prev, res.data]);
      setInviteOpen(false);
      setInviteForm(EMPTY_FORM);
      toast(`Invite sent to ${inviteForm.email}`);
    } catch (err) {
      setInviteError(getErrorDetail(err, "Failed to invite user."));
    } finally {
      setInviting(false);
    }
  }

  async function patchUser(id: string, body: { role?: string; is_active?: boolean }) {
    setRowBusy((prev) => ({ ...prev, [id]: true }));
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    try {
      const res = await client.patch<User>(`/users/${id}`, body);
      setUsers((prev) => prev.map((u) => (u.id === id ? res.data : u)));
    } catch (err) {
      const detail = getErrorDetail(err, "Failed to update user.");
      setRowErrors((prev) => ({ ...prev, [id]: detail }));
    } finally {
      setRowBusy((prev) => ({ ...prev, [id]: false }));
    }
  }

  const columnCount = isAdmin ? 6 : 5;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className={PAGE_HEADING}>Users</h1>
        {isAdmin && (
          <button
            onClick={() => { setInviteOpen(true); setInviteError(null); setInviteForm(EMPTY_FORM); }}
            className="rounded-[7px] bg-brand-orange px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition-opacity"
          >
            Invite User
          </button>
        )}
      </div>

      {/* Invite modal */}
      {inviteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="invite-modal-title"
            className="bg-white rounded-[10px] border border-brand-border p-6 w-full max-w-[min(480px,90vw)] shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)]"
          >
            <h2 id="invite-modal-title" className="text-base font-semibold mb-4">Invite User</h2>
            <form onSubmit={handleInvite} className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Name <span className="text-brand-grey-dark">*</span></label>
                <input
                  ref={nameInputRef}
                  className={INPUT_CLASS}
                  required
                  value={inviteForm.name}
                  onChange={(e) => setInviteForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Full name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Email <span className="text-brand-grey-dark">*</span></label>
                <input
                  className={INPUT_CLASS}
                  type="email"
                  required
                  value={inviteForm.email}
                  onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
                  placeholder="user@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Phone <span className="text-brand-grey-dark">*</span></label>
                <PhoneInput
                  value={inviteForm.phone}
                  onChange={(v) => setInviteForm((f) => ({ ...f, phone: v }))}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Role</label>
                <select
                  className={INPUT_CLASS}
                  value={inviteForm.role}
                  onChange={(e) => setInviteForm((f) => ({ ...f, role: e.target.value }))}
                >
                  <option value="staff">Staff</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              {inviteError && (
                <p className="text-sm text-brand-grey-dark">{inviteError}</p>
              )}
              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  disabled={inviting}
                  className="px-4 py-2 bg-brand-orange text-white rounded-[7px] text-sm font-medium disabled:opacity-50"
                >
                  {inviting ? "Inviting…" : "Send Invite"}
                </button>
                <button
                  type="button"
                  onClick={() => setInviteOpen(false)}
                  className="px-4 py-2 border border-brand-border rounded-[7px] text-sm"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-brand-grey-light">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!isLoading && !error && (
        <div className="rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-page-bg text-brand-grey-dark">
                <th className="px-4 py-3 text-left font-semibold">Name</th>
                <th className="px-4 py-3 text-left font-semibold">Email</th>
                <th className="px-4 py-3 text-left font-semibold">Phone</th>
                <th className="px-4 py-3 text-left font-semibold">Role</th>
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                {isAdmin && <th className="px-4 py-3 text-left font-semibold">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={columnCount} className="px-4 py-8 text-center text-brand-grey-light">
                    No users yet.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="px-4 py-3">{u.name}</td>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3">{u.phone}</td>
                  <td className="px-4 py-3 capitalize">
                    {isAdmin ? (
                      <select
                        aria-label={`Role for ${u.name}`}
                        value={u.role}
                        disabled={rowBusy[u.id]}
                        onChange={(e) => patchUser(u.id, { role: e.target.value })}
                        className="rounded-lg border border-brand-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-black disabled:opacity-50"
                      >
                        <option value="admin">Admin</option>
                        <option value="staff">Staff</option>
                      </select>
                    ) : (
                      u.role
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium border ${
                        u.is_active
                          ? "bg-[rgba(176,83,87,0.10)] text-[#B05357] border-[rgba(176,83,87,0.20)]"
                          : "bg-[#F4F5F7] text-[#92918F] border-[#E4E6EC]"
                      }`}
                    >
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      <button
                        onClick={() => patchUser(u.id, { is_active: !u.is_active })}
                        disabled={rowBusy[u.id] || (u.is_active && u.id === currentUser?.id)}
                        title={
                          u.is_active && u.id === currentUser?.id
                            ? "You cannot deactivate your own account"
                            : undefined
                        }
                        className="rounded-[7px] border border-brand-border bg-white px-3 py-1.5 text-sm text-brand-grey-dark hover:bg-page-bg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                      {rowErrors[u.id] && (
                        <p className="mt-1 text-[11px] text-brand-grey-dark">{rowErrors[u.id]}</p>
                      )}
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
