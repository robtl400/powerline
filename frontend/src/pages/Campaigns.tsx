import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
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
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
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
        {isAdmin && (
          <button
            onClick={() => navigate("/campaigns/new")}
            className="px-4 py-2 bg-brand-orange text-white rounded-[7px] text-sm font-medium hover:opacity-90 transition-opacity"
          >
            New Campaign
          </button>
        )}
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-1 mb-6 border-b border-brand-border">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-2 text-sm font-medium capitalize border-b-2 transition-colors ${
              statusFilter === s
                ? "border-brand-orange text-brand-orange"
                : "border-transparent text-brand-grey-dark hover:text-brand-black"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-brand-grey-dark">Loading…</p>}
      {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

      {!loading && !error && campaigns.length === 0 && (
        <div className="rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] px-6 py-12 text-center">
          <p className="text-sm text-brand-grey-dark mb-4">No campaigns yet</p>
          {isAdmin && (
            <button
              onClick={() => navigate("/campaigns/new")}
              className="px-4 py-2 bg-brand-orange text-white rounded-[7px] text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Create campaign
            </button>
          )}
        </div>
      )}

      {!loading && !error && campaigns.length > 0 && (
        <div className="rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-page-bg text-brand-grey-dark">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Name</th>
                <th className="text-left px-4 py-3 font-semibold">Type</th>
                <th className="text-left px-4 py-3 font-semibold">Status</th>
                <th className="text-left px-4 py-3 font-semibold">Targets</th>
                <th className="text-left px-4 py-3 font-semibold">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr
                  key={c.id}
                  className={`border-t border-brand-border hover:bg-page-bg/50 transition-colors ${c.status === "draft" ? "opacity-50" : ""}`}
                >
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="px-4 py-3 capitalize text-brand-grey-dark">{c.campaign_type}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium capitalize ${CAMPAIGN_STATUS_COLORS[c.status] ?? FALLBACK_BADGE_COLOR}`}
                    >
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-brand-grey-dark">{c.target_count}</td>
                  <td className="px-4 py-3 text-brand-grey-dark">
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {c.status === "draft" ? (
                      <button
                        onClick={() => navigate(`/campaigns/${c.id}/wizard`)}
                        className="text-brand-grey-dark text-sm hover:underline"
                      >
                        Resume wizard
                      </button>
                    ) : (
                      <button
                        onClick={() => navigate(`/campaigns/${c.id}/edit`)}
                        className="text-brand-orange text-sm hover:underline"
                      >
                        Edit
                      </button>
                    )}
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
