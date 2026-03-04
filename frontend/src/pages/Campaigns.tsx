import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "@/api/client";
import { PAGE_HEADING } from "@/lib/styles";
import { CAMPAIGN_STATUS_COLORS, FALLBACK_BADGE_COLOR } from "@/lib/constants";

interface Campaign {
  id: string;
  name: string;
  status: string;
  campaign_type: string;
  target_count: number;
  created_at: string;
}

const STATUSES = ["all", "draft", "live", "paused", "archived"];

export default function Campaigns() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = statusFilter !== "all" ? `?status=${statusFilter}` : "";
    client
      .get<Campaign[]>(`/campaigns${params}`)
      .then((res) => {
        setCampaigns(res.data);
        setError(null);
      })
      .catch(() => setError("Failed to load campaigns."))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className={PAGE_HEADING}>Campaigns</h1>
        <button
          onClick={() => navigate("/campaigns/new")}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
        >
          New Campaign
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-1 mb-6 border-b border-border">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-2 text-sm font-medium capitalize border-b-2 transition-colors ${
              statusFilter === s
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && <p className="text-muted-foreground">Loading…</p>}
      {error && <p className="text-destructive">{error}</p>}

      {!loading && !error && campaigns.length === 0 && (
        <p className="text-muted-foreground">No campaigns found.</p>
      )}

      {!loading && !error && campaigns.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#53565B] text-white">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Type</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Targets</th>
                <th className="text-left px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr
                  key={c.id}
                  className="border-t border-border hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="px-4 py-3 capitalize text-muted-foreground">{c.campaign_type}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium capitalize ${CAMPAIGN_STATUS_COLORS[c.status] ?? FALLBACK_BADGE_COLOR}`}
                    >
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{c.target_count}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => navigate(`/campaigns/${c.id}/edit`)}
                      className="text-primary text-sm hover:underline"
                    >
                      Edit
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
