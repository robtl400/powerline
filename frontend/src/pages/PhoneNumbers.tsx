import { useEffect, useState } from "react";
import client from "@/api/client";
import { TRUST_STATUS_COLORS, FALLBACK_BADGE_COLOR } from "@/lib/constants";
import { INPUT_CLASS } from "@/lib/styles";

interface PhoneNumber {
  id: string;
  number: string;
  label: string;
  provider: string;
  capabilities: Record<string, boolean>;
  trust_status: string;
  trust_product_sid: string | null;
  created_at: string;
}

interface Campaign {
  id: string;
  name: string;
}


export default function PhoneNumbers() {
  const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumber[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [assignTarget, setAssignTarget] = useState<PhoneNumber | null>(null);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      client.get<PhoneNumber[]>("/phone-numbers"),
      client.get<Campaign[]>("/campaigns"),
    ])
      .then(([numsRes, campsRes]) => {
        setPhoneNumbers(numsRes.data);
        setCampaigns(campsRes.data);
        setError(null);
      })
      .catch(() => setError("Failed to load data."))
      .finally(() => setLoading(false));
  }, []);

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      const res = await client.post<PhoneNumber[]>("/phone-numbers/sync");
      setPhoneNumbers(res.data);
    } catch {
      setError("Failed to sync from Twilio.");
    } finally {
      setSyncing(false);
    }
  }

  async function handleAssign() {
    if (!assignTarget || !selectedCampaignId) return;
    setAssigning(true);
    setAssignError(null);
    try {
      await client.post(`/phone-numbers/${assignTarget.id}/assign`, {
        campaign_id: selectedCampaignId,
      });
      setAssignTarget(null);
      setSelectedCampaignId("");
    } catch {
      setAssignError("Failed to assign phone number.");
    } finally {
      setAssigning(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Phone Numbers</h1>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {syncing ? "Syncing…" : "Sync from Twilio"}
        </button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && !error && (
        <div className="rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">Number</th>
                <th className="px-4 py-3 text-left font-medium">Label</th>
                <th className="px-4 py-3 text-left font-medium">Provider</th>
                <th className="px-4 py-3 text-left font-medium">Capabilities</th>
                <th className="px-4 py-3 text-left font-medium">Trust / SHAKEN</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {phoneNumbers.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    No phone numbers. Click "Sync from Twilio" to import.
                  </td>
                </tr>
              )}
              {phoneNumbers.map((pn) => (
                <tr key={pn.id} className="border-b last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{pn.number}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {pn.label || "—"}
                  </td>
                  <td className="px-4 py-3 capitalize">{pn.provider}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(pn.capabilities)
                        .filter(([, enabled]) => enabled)
                        .map(([cap]) => (
                          <span
                            key={cap}
                            className="inline-block rounded px-1.5 py-0.5 text-xs uppercase bg-blue-100 text-blue-700"
                          >
                            {cap}
                          </span>
                        ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium capitalize ${TRUST_STATUS_COLORS[pn.trust_status] ?? FALLBACK_BADGE_COLOR}`}
                    >
                      {pn.trust_status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => {
                        setAssignTarget(pn);
                        setSelectedCampaignId("");
                        setAssignError(null);
                      }}
                      className="text-primary text-sm hover:underline"
                    >
                      Assign
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Inline assign panel — consistent with CampaignEdit target add/edit pattern */}
      {assignTarget && (
        <div className="max-w-md rounded-md border border-border bg-muted/20 p-4 space-y-3">
          <p className="text-sm font-medium">
            Assign{" "}
            <span className="font-mono">{assignTarget.number}</span> to campaign
          </p>
          <select
            className={INPUT_CLASS}
            value={selectedCampaignId}
            onChange={(e) => setSelectedCampaignId(e.target.value)}
          >
            <option value="">Select a campaign…</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {assignError && (
            <p className="text-xs text-destructive">{assignError}</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleAssign}
              disabled={!selectedCampaignId || assigning}
              className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {assigning ? "Assigning…" : "Assign"}
            </button>
            <button
              onClick={() => setAssignTarget(null)}
              className="rounded-md border border-border px-4 py-1.5 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
