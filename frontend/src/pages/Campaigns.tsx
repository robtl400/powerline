import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Megaphone } from "lucide-react";
import client from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import {
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  CARD_CLASS,
  FOCUS_RING,
  INPUT_CLASS,
  LINK_BUTTON,
  PAGE_HEADING,
} from "@/lib/styles";
import { CAMPAIGN_STATUS_COLORS, FALLBACK_BADGE_COLOR } from "@/lib/constants";
import { EmptyState } from "@/components/EmptyState";
import { CampaignCardList, campaignHref } from "@/components/CampaignCards";
import type { Page } from "@/types/api";

interface Campaign {
  id: string;
  name: string;
  status: string;
  campaign_type: string;
  target_count: number;
  session_count: number;
  completed_session_count: number;
  created_at: string;
}

const STATUSES = ["all", "draft", "live", "paused", "archived"];

function listUrl(statusFilter: string, q: string, skip: number): string {
  const params = new URLSearchParams();
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (q) params.set("q", q);
  if (skip > 0) params.set("skip", String(skip));
  const query = params.toString();
  return `/campaigns${query ? `?${query}` : ""}`;
}

export default function Campaigns() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    client
      .get<Page<Campaign>>(listUrl(statusFilter, debouncedSearch, 0))
      .then((res) => {
        setCampaigns(res.data.items);
        setTotal(res.data.total);
        setError(null);
      })
      .catch(() => setError("Failed to load campaigns."))
      .finally(() => setLoading(false));
  }, [statusFilter, debouncedSearch]);

  function loadMore() {
    setLoadingMore(true);
    client
      .get<Page<Campaign>>(listUrl(statusFilter, debouncedSearch, campaigns.length))
      .then((res) => {
        setCampaigns((prev) => [...prev, ...res.data.items]);
        setTotal(res.data.total);
        setError(null);
      })
      .catch(() => setError("Failed to load more campaigns."))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className={PAGE_HEADING}>Campaigns</h1>
        {isAdmin && (
          <button
            onClick={() => navigate("/campaigns/new")}
            className={BUTTON_PRIMARY}
          >
            New Campaign
          </button>
        )}
      </div>

      {/* Status filter tabs + search */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6 border-b border-brand-border">
        <div className="flex gap-1">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`inline-flex min-h-[44px] items-center px-3 py-2 text-sm font-medium capitalize border-b-2 transition-colors ${FOCUS_RING} ${
                statusFilter === s
                  ? "border-brand-orange text-brand-orange"
                  : "border-transparent text-brand-grey-dark hover:text-brand-black"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="pb-2">
          <input
            type="search"
            aria-label="Search campaigns"
            placeholder="Search campaigns…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSearch("");
            }}
            className={`${INPUT_CLASS} min-h-[44px] sm:w-[240px]`}
          />
        </div>
      </div>

      {loading && <p className="text-sm text-brand-grey-dark">Loading…</p>}
      {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

      {!loading && !error && campaigns.length === 0 && (
        <div className={CARD_CLASS}>
          <EmptyState
            icon={Megaphone}
            title={debouncedSearch ? "No campaigns match your search" : "No campaigns yet"}
            description={
              debouncedSearch
                ? "Try a different name, or clear the search."
                : "Campaigns hold the targets, audio and embed for one call-in drive."
            }
            action={
              isAdmin && !debouncedSearch ? (
                <button
                  onClick={() => navigate("/campaigns/new")}
                  className={BUTTON_PRIMARY}
                >
                  Create campaign
                </button>
              ) : undefined
            }
          />
        </div>
      )}

      {!loading && campaigns.length > 0 && <CampaignCardList campaigns={campaigns} />}

      {!loading && campaigns.length > 0 && (
        <div className={`${CARD_CLASS} hidden overflow-x-auto sm:block`}>
          <table className="w-full text-sm">
            <thead className="bg-page-bg text-brand-grey-dark">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Name</th>
                <th className="text-left px-4 py-3 font-semibold">Type</th>
                <th className="text-left px-4 py-3 font-semibold">Status</th>
                <th className="text-right px-4 py-3 font-semibold">Targets</th>
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
                  <td className="px-4 py-3 font-medium">
                    <Link
                      to={campaignHref(c.id)}
                      className={`-my-3 inline-flex min-h-[44px] items-center py-3 rounded-control text-brand-black hover:underline ${FOCUS_RING}`}
                    >
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize text-brand-grey-dark">{c.campaign_type}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded-field text-xs font-medium capitalize ${CAMPAIGN_STATUS_COLORS[c.status] ?? FALLBACK_BADGE_COLOR}`}
                    >
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-brand-grey-dark">
                    {c.target_count}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-brand-grey-dark">
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {c.status === "draft" ? (
                      <button
                        onClick={() => navigate(`/campaigns/${c.id}/wizard`)}
                        className={`${LINK_BUTTON} text-brand-orange`}
                      >
                        Resume wizard
                      </button>
                    ) : (
                      <button
                        onClick={() => navigate(`/campaigns/${c.id}/edit`)}
                        className={`${LINK_BUTTON} text-brand-orange`}
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

      {!loading && campaigns.length < total && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <p className="text-sm text-brand-grey-dark">
            Showing {campaigns.length} of {total}
          </p>
          <button onClick={loadMore} disabled={loadingMore} className={BUTTON_SECONDARY}>
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
