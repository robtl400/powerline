import { useEffect, useState } from "react";
import client from "@/api/client";
import { getErrorDetail } from "@/lib/api-error";
import { INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";

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
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteForm>(EMPTY_FORM);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);

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
    } catch (err) {
      setInviteError(getErrorDetail(err, "Failed to invite user."));
    } finally {
      setInviting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className={PAGE_HEADING}>Users</h1>
        <button
          onClick={() => { setInviteOpen(true); setInviteError(null); setInviteForm(EMPTY_FORM); }}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Invite User
        </button>
      </div>

      {/* Invite modal */}
      {inviteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-background rounded-lg border border-border p-6 w-full max-w-md shadow-lg">
            <h2 className="text-base font-semibold mb-4">Invite User</h2>
            <form onSubmit={handleInvite} className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Name <span className="text-destructive">*</span></label>
                <input
                  className={INPUT_CLASS}
                  required
                  value={inviteForm.name}
                  onChange={(e) => setInviteForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Full name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Email <span className="text-destructive">*</span></label>
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
                <label className="block text-sm font-medium mb-1">Phone <span className="text-destructive">*</span></label>
                <input
                  className={INPUT_CLASS}
                  required
                  value={inviteForm.phone}
                  onChange={(e) => setInviteForm((f) => ({ ...f, phone: e.target.value }))}
                  placeholder="+12025551234"
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
                <p className="text-sm text-destructive">{inviteError}</p>
              )}
              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  disabled={inviting}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
                >
                  {inviting ? "Inviting…" : "Send Invite"}
                </button>
                <button
                  type="button"
                  onClick={() => setInviteOpen(false)}
                  className="px-4 py-2 border border-border rounded-md text-sm"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!isLoading && !error && (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#53565B] text-white">
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Phone</th>
                <th className="px-4 py-3 text-left font-medium">Role</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                    No users yet.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="px-4 py-3">{u.name}</td>
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3">{u.phone}</td>
                  <td className="px-4 py-3 capitalize">{u.role}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                        u.is_active
                          ? "bg-stone-100 text-[#F2542D]"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
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
