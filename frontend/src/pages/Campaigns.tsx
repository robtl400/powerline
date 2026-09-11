import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Megaphone } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import {
  BUTTON_PRIMARY,
  CARD_CLASS,
  FOCUS_RING,
  INPUT_CLASS,
  LINK_BUTTON,
  PAGE_HEADING,
} from "@/lib/styles";
import { CAMPAIGN_STATUS_COLORS, FALLBACK_BADGE_COLOR } from "@/lib/constants";
import { EmptyState } from "@/components/EmptyState";
import { LoadMore } from "@/components/LoadMore";
import { CampaignCardList, campaignHref } from "@/components/CampaignCards";
import { usePagedList } from "@/hooks/usePagedList";

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

function listUrl(statusFilter: string, q: string): string {
  const params = new URLSearchParams();
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (q) params.set("q", q);
  const query = params.toString();
  return `/campaigns${query ? `?${query}` : ""}`;
}

export default function Campaigns() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const list = usePagedList<Campaign>(listUrl(statusFilter, debouncedSearch), {
    errorMessage: "Failed to load campaigns.",
  });
  const campaigns = list.items;
  const loading = list.loading;

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
                  ? "border-brand-orange text-brand-black"
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
      {list.error && <p className="text-sm text-brand-grey-dark">{list.error}</p>}

      {!loading && !list.error && campaigns.length === 0 && (
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
                  className="border-t border-brand-border hover:bg-page-bg/50 transition-colors"
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

      {!loading && (
        <LoadMore
          hasMore={list.hasMore}
          shown={campaigns.length}
          total={list.total}
          loading={list.loadingMore}
          onLoadMore={list.loadMore}
          className="mt-4"
        />
      )}
    </div>
  );
}
