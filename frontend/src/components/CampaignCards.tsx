import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CARD_CLASS, FOCUS_RING } from "@/lib/styles";
import { CAMPAIGN_STATUS_COLORS, FALLBACK_BADGE_COLOR } from "@/lib/constants";

export interface CampaignCardItem {
  id: string;
  name: string;
  status: string;
  session_count: number;
  completed_session_count: number;
}

/** The campaign's own page — the route every campaign layout points at. */
export function campaignHref(id: string): string {
  return `/campaigns/${id}/edit`;
}

/**
 * Per-campaign progress from the list payload: calls placed is the campaign's
 * call sessions, and the share is the sessions that ran to completion against
 * that total. A campaign nobody has called yet sits at zero.
 */
export function campaignProgress(campaign: CampaignCardItem): {
  calls: number;
  percent: number;
} {
  const calls = campaign.session_count ?? 0;
  const completed = campaign.completed_session_count ?? 0;
  const percent = calls > 0 ? Math.min(100, Math.round((completed / calls) * 100)) : 0;
  return { calls, percent };
}

interface CampaignCardListProps {
  campaigns: CampaignCardItem[];
  empty?: ReactNode;
}

/**
 * Below `sm` this replaces the campaign tables on Dashboard and Campaigns.
 * Both layouts render and Tailwind switches between them.
 */
export function CampaignCardList({ campaigns, empty }: CampaignCardListProps) {
  if (campaigns.length === 0 && !empty) return null;

  return (
    <ul aria-label="Campaigns" className="space-y-3 sm:hidden">
      {campaigns.length === 0 ? (
        <li className={CARD_CLASS}>{empty}</li>
      ) : (
        campaigns.map((c) => {
          const { calls, percent } = campaignProgress(c);
          return (
            <li key={c.id}>
              <Link
                to={campaignHref(c.id)}
                className={`${CARD_CLASS} block space-y-2 p-4 transition-colors hover:bg-page-bg/50 ${FOCUS_RING}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-semibold text-brand-black">
                    {c.name}
                  </span>
                  <span
                    className={`inline-block shrink-0 rounded-field px-1.5 py-0.5 text-xs font-medium capitalize ${
                      CAMPAIGN_STATUS_COLORS[c.status] ?? FALLBACK_BADGE_COLOR
                    }`}
                  >
                    {c.status}
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-field bg-page-bg">
                  <div
                    role="progressbar"
                    aria-label={`${c.name} progress`}
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    style={{ width: `${percent}%` }}
                    className={`h-full ${c.status === "live" ? "bg-brand-orange" : "bg-brand-grey-mid"}`}
                  />
                </div>
                <div className="flex items-center justify-between text-[11px] text-brand-grey-dark">
                  <span className="tabular-nums">{calls} calls</span>
                  <span className="tabular-nums">{percent}% completed</span>
                </div>
              </Link>
            </li>
          );
        })
      )}
    </ul>
  );
}
