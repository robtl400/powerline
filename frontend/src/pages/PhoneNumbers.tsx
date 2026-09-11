import { useEffect, useState } from "react";
import { Phone } from "lucide-react";
import client from "@/api/client";
import {
  CAPABILITY_BADGE_COLOR,
  TRUST_STATUS_COLORS,
  TRUST_STATUS_LABELS,
  FALLBACK_BADGE_COLOR,
} from "@/lib/constants";
import { BUTTON_PRIMARY, BUTTON_SECONDARY, CARD_CLASS, INPUT_CLASS, LINK_BUTTON, PAGE_HEADING } from "@/lib/styles";
import { EmptyTableRow } from "@/components/EmptyState";
import type { Page } from "@/types/api";

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
      client.get<Page<Campaign>>("/campaigns?limit=500"),
    ])
      .then(([numsRes, campsRes]) => {
        setPhoneNumbers(numsRes.data);
        setCampaigns(campsRes.data.items);
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
        <h1 className={PAGE_HEADING}>Phone Numbers</h1>
        <button
          onClick={handleSync}
          disabled={syncing}
          className={BUTTON_PRIMARY}
        >
          {syncing ? "Syncing…" : "Sync from Twilio"}
        </button>
      </div>

      {error && <p className="text-sm text-brand-grey-dark">{error}</p>}
      {loading && <p className="text-sm text-brand-grey-dark">Loading…</p>}

      {!loading && !error && (
        <div className={`${CARD_CLASS} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-page-bg text-brand-grey-dark">
                <th className="px-4 py-3 text-left font-semibold">Number</th>
                <th className="px-4 py-3 text-left font-semibold">Label</th>
                <th className="px-4 py-3 text-left font-semibold">Provider</th>
                <th className="px-4 py-3 text-left font-semibold">Capabilities</th>
                <th className="px-4 py-3 text-left font-semibold">Trust / SHAKEN</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {phoneNumbers.length === 0 && (
                <EmptyTableRow
                  colSpan={6}
                  icon={Phone}
                  title="No phone numbers configured"
                  description="Numbers you own in Twilio can be imported and assigned to campaigns."
                  action={
                    <button
                      onClick={handleSync}
                      disabled={syncing}
                      className={BUTTON_PRIMARY}
                    >
                      {syncing ? "Syncing…" : "Sync from Twilio"}
                    </button>
                  }
                />
              )}
              {phoneNumbers.map((pn) => (
                <tr key={pn.id} className="border-b last:border-0">
                  <td className="px-4 py-3 font-mono text-xs tabular-nums">{pn.number}</td>
                  <td className="px-4 py-3 text-brand-grey-dark">
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
                            className={`inline-block rounded-field px-1.5 py-0.5 text-xs uppercase ${CAPABILITY_BADGE_COLOR}`}
                          >
                            {cap}
                          </span>
                        ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-field px-1.5 py-0.5 text-xs font-medium capitalize ${TRUST_STATUS_COLORS[pn.trust_status] ?? FALLBACK_BADGE_COLOR}`}
                    >
                      {TRUST_STATUS_LABELS[pn.trust_status] || pn.trust_status || "Unknown"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => {
                        setAssignTarget(pn);
                        setSelectedCampaignId("");
                        setAssignError(null);
                      }}
                      className={`${LINK_BUTTON} px-2 text-brand-orange`}
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
        <div className="max-w-md rounded-card border border-brand-border bg-page-bg p-4 space-y-3">
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
            <p className="text-xs text-brand-grey-dark">{assignError}</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleAssign}
              disabled={!selectedCampaignId || assigning}
              className={BUTTON_PRIMARY}
            >
              {assigning ? "Assigning…" : "Assign"}
            </button>
            <button
              onClick={() => setAssignTarget(null)}
              className={BUTTON_SECONDARY}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
