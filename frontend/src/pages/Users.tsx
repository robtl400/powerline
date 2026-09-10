import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Users as UsersIcon } from "lucide-react";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { useIsNarrow } from "@/hooks/useMediaQuery";
import { getErrorDetail } from "@/lib/api-error";
import { USER_STATUS_COLORS } from "@/lib/constants";
import { BUTTON_PRIMARY, CARD_CLASS, FOCUS_RING, INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";
import { EmptyState, EmptyTableRow } from "@/components/EmptyState";
import { Modal } from "@/components/Modal";
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
  const isNarrow = useIsNarrow();

  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteForm>(EMPTY_FORM);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);

  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [rowBusy, setRowBusy] = useState<Record<string, boolean>>({});

  useEffect(() => {
    client
      .get<User[]>("/users")
      .then((res) => setUsers(res.data))
      .catch(() => setError("Failed to load users."))
      .finally(() => setIsLoading(false));
  }, []);

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

  function roleControl(u: User) {
    if (!isAdmin) return <span className="capitalize">{u.role}</span>;
    return (
      <select
        aria-label={`Role for ${u.name}`}
        value={u.role}
        disabled={rowBusy[u.id]}
        onChange={(e) => patchUser(u.id, { role: e.target.value })}
        className={`min-h-[44px] rounded-field border border-brand-border bg-white px-2 py-1 text-sm disabled:opacity-50 ${FOCUS_RING}`}
      >
        <option value="admin">Admin</option>
        <option value="staff">Staff</option>
      </select>
    );
  }

  function statusChip(u: User) {
    return (
      <span
        className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
          USER_STATUS_COLORS[u.is_active ? "active" : "inactive"]
        }`}
      >
        {u.is_active ? "Active" : "Inactive"}
      </span>
    );
  }

  function activationControl(u: User) {
    return (
      <>
        <button
          onClick={() => patchUser(u.id, { is_active: !u.is_active })}
          disabled={rowBusy[u.id] || (u.is_active && u.id === currentUser?.id)}
          title={
            u.is_active && u.id === currentUser?.id
              ? "You cannot deactivate your own account"
              : undefined
          }
          className={`inline-flex min-h-[44px] items-center rounded-control border border-brand-border bg-white px-3 py-1.5 text-sm text-brand-grey-dark hover:bg-page-bg disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${FOCUS_RING}`}
        >
          {u.is_active ? "Deactivate" : "Activate"}
        </button>
        {rowErrors[u.id] && (
          <p className="mt-1 text-[11px] text-brand-grey-dark">{rowErrors[u.id]}</p>
        )}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className={PAGE_HEADING}>Users</h1>
        {isAdmin && (
          <button
            onClick={() => { setInviteOpen(true); setInviteError(null); setInviteForm(EMPTY_FORM); }}
            className={BUTTON_PRIMARY}
          >
            Invite User
          </button>
        )}
      </div>

      {/* Invite modal */}
      <Modal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        titleId="invite-modal-title"
        title="Invite User"
      >
        <form onSubmit={handleInvite} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">Name <span className="text-brand-grey-dark">*</span></label>
            <input
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
              className={BUTTON_PRIMARY}
            >
              {inviting ? "Inviting…" : "Send Invite"}
            </button>
            <button
              type="button"
              onClick={() => setInviteOpen(false)}
              className="px-4 py-2 border border-brand-border rounded-control text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      {isLoading && <p className="text-sm text-brand-grey-dark">Loading…</p>}
      {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

      {/* Mobile: one card per user — the table controls are unreachable below sm */}
      {!isLoading && !error && isNarrow && (
        <div className="space-y-3">
          {users.length === 0 ? (
            <div className={CARD_CLASS}>
              <EmptyState
                icon={UsersIcon}
                title="No users yet"
                description="Invited teammates appear here once they are added."
              />
            </div>
          ) : (
            users.map((u) => (
              <div key={u.id} className={`${CARD_CLASS} p-4 space-y-2`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-brand-black">{u.name}</p>
                    <p className="truncate text-[11px] text-brand-grey-dark">{u.email}</p>
                    <p className="text-[11px] tabular-nums text-brand-grey-dark">{u.phone}</p>
                  </div>
                  {statusChip(u)}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {roleControl(u)}
                  {isAdmin && activationControl(u)}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {!isLoading && !error && !isNarrow && (
        <div className={`${CARD_CLASS} overflow-x-auto`}>
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
                <EmptyTableRow
                  colSpan={columnCount}
                  icon={UsersIcon}
                  title="No users yet"
                  description="Invited teammates appear here once they are added."
                />
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="px-4 py-3">{u.name}</td>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3 tabular-nums">{u.phone}</td>
                  <td className="px-4 py-3">{roleControl(u)}</td>
                  <td className="px-4 py-3">{statusChip(u)}</td>
                  {isAdmin && <td className="px-4 py-3">{activationControl(u)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
