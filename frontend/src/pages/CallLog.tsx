import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PhoneOff } from "lucide-react";
import client from "@/api/client";
import {
  CALL_SESSION_STATUS_COLORS,
  CONNECTION_TYPE_COLORS,
  FALLBACK_BADGE_COLOR,
} from "@/lib/constants";
import { formatDateTime } from "@/lib/formatters";
import { BUTTON_SECONDARY, CARD_CLASS, FOCUS_RING, LINK_BUTTON, PAGE_HEADING } from "@/lib/styles";
import { EmptyTableRow } from "@/components/EmptyState";
import type { Page } from "@/types/api";

interface CallSessionRow {
  id: string;
  created_at: string;
  connection_type: string;
  status: string;
  call_count: number;
  duration: number | null;
}

interface CampaignBasic {
  id: string;
  name: string;
}

function Badge({ label, colorClass }: { label: string; colorClass: string }) {
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded-field text-xs font-medium ${colorClass}`}>
      {label.replace("_", " ")}
    </span>
  );
}

const PAGE_SIZE = 50;

export default function CallLog() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [campaign, setCampaign] = useState<CampaignBasic | null>(null);
  const [page, setPage] = useState<Page<CallSessionRow>>({ total: 0, items: [] });
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [csvLoading, setCsvLoading] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const buildParams = useCallback(
    (extraSkip?: number) => {
      const params = new URLSearchParams();
      params.set("limit", String(PAGE_SIZE));
      params.set("skip", String(extraSkip ?? skip));
      if (statusFilter) params.set("status", statusFilter);
      if (typeFilter) params.set("connection_type", typeFilter);
      if (startDate) params.set("start", startDate);
      if (endDate) params.set("end", endDate);
      return params.toString();
    },
    [skip, statusFilter, typeFilter, startDate, endDate]
  );

  // Load campaign name
  useEffect(() => {
    if (!id) return;
    client
      .get<CampaignBasic>(`/campaigns/${id}?include_targets=false`)
      .then((res) => setCampaign(res.data))
      .catch(() => null);
  }, [id]);

  // Load call sessions
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    client
      .get<Page<CallSessionRow>>(`/campaigns/${id}/calls?${buildParams()}`)
      .then((res) => {
        setPage(res.data);
        setError(null);
      })
      .catch(() => setError("Failed to load call log."))
      .finally(() => setLoading(false));
  }, [id, buildParams]); // eslint-disable-line react-hooks/exhaustive-deps

  function applyFilters() {
    setSkip(0);
  }

  function clearFilters() {
    setStatusFilter("");
    setTypeFilter("");
    setStartDate("");
    setEndDate("");
    setSkip(0);
  }

  async function handleCsvExport() {
    if (!id) return;
    setCsvLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (typeFilter) params.set("connection_type", typeFilter);
      if (startDate) params.set("start", startDate);
      if (endDate) params.set("end", endDate);

      // Fetch with auth header → Blob → trigger download
      const res = await client.get(`/campaigns/${id}/calls/export?${params.toString()}`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `calls-${id}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("CSV export failed.");
    } finally {
      setCsvLoading(false);
    }
  }

  const totalPages = Math.ceil(page.total / PAGE_SIZE);
  const currentPage = Math.floor(skip / PAGE_SIZE) + 1;
  const hasActiveFilters = Boolean(statusFilter || typeFilter || startDate || endDate);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
        <button
          onClick={() => navigate(`/campaigns/${id}/edit`)}
          className={`${LINK_BUTTON} text-brand-grey-dark hover:text-brand-black`}
        >
          ← {campaign?.name ?? "Campaign"}
        </button>
        <span className="hidden text-brand-grey-dark sm:inline">/</span>
        <h1 className={PAGE_HEADING}>Call Log</h1>
      </div>

      {/* Filters */}
      <div className={`flex flex-wrap items-end gap-3 ${CARD_CLASS} p-4`}>
        <div>
          <label htmlFor="calllog-status" className="block text-xs text-brand-grey-dark mb-1">Status</label>
          <select
            id="calllog-status"
            className={`min-h-[44px] text-sm border border-brand-border rounded-field px-2 py-1.5 bg-white min-w-[120px] ${FOCUS_RING}`}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All</option>
            <option value="initiated">Initiated</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div>
          <label htmlFor="calllog-type" className="block text-xs text-brand-grey-dark mb-1">Type</label>
          <select
            id="calllog-type"
            className={`min-h-[44px] text-sm border border-brand-border rounded-field px-2 py-1.5 bg-white min-w-[140px] ${FOCUS_RING}`}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All</option>
            <option value="webrtc">WebRTC</option>
            <option value="outbound_phone">Phone Callback</option>
            <option value="inbound_phone">Dial-in</option>
          </select>
        </div>
        <div>
          <label htmlFor="calllog-start" className="block text-xs text-brand-grey-dark mb-1">From</label>
          <input
            id="calllog-start"
            type="date"
            className={`min-h-[44px] text-sm border border-brand-border rounded-field px-2 py-1.5 bg-white ${FOCUS_RING}`}
            value={startDate}
            max={endDate || undefined}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="calllog-end" className="block text-xs text-brand-grey-dark mb-1">To</label>
          <input
            id="calllog-end"
            type="date"
            className={`min-h-[44px] text-sm border border-brand-border rounded-field px-2 py-1.5 bg-white ${FOCUS_RING}`}
            value={endDate}
            min={startDate || undefined}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <div className="flex gap-2 ml-auto">
          <button
            onClick={applyFilters}
            className={`inline-flex min-h-[44px] items-center px-3 py-1.5 bg-brand-orange text-white rounded-control text-sm hover:opacity-90 transition-opacity ${FOCUS_RING}`}
          >
            Apply
          </button>
          <button
            onClick={clearFilters}
            className={BUTTON_SECONDARY}
          >
            Clear
          </button>
          <button
            onClick={handleCsvExport}
            disabled={csvLoading}
            className={BUTTON_SECONDARY}
          >
            {csvLoading ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-field bg-page-bg text-brand-grey-dark px-4 py-3 text-sm border border-brand-border">
          {error}
        </div>
      )}

      {/* Table */}
      <div className={`${CARD_CLASS} overflow-x-auto`}>
        <div className="border-b px-5 py-3 flex items-center justify-between">
          <p className="text-sm text-brand-grey-dark">
            {page.total} session{page.total !== 1 ? "s" : ""}
          </p>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-brand-grey-dark">Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-page-bg text-left text-xs text-brand-grey-dark">
                <th className="px-5 py-2 font-semibold">Date / Time</th>
                <th className="px-5 py-2 font-semibold">Type</th>
                <th className="px-5 py-2 font-semibold">Status</th>
                <th className="px-5 py-2 font-semibold text-right">Calls Made</th>
                <th className="px-5 py-2 font-semibold text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 ? (
                <EmptyTableRow
                  colSpan={5}
                  icon={PhoneOff}
                  title={hasActiveFilters ? "No sessions match your filters" : "No call sessions yet"}
                  description={
                    hasActiveFilters
                      ? undefined
                      : "Sessions appear here as supporters call through this campaign."
                  }
                  action={
                    hasActiveFilters ? (
                      <button
                        onClick={clearFilters}
                        className={`${LINK_BUTTON} px-2 text-brand-orange`}
                      >
                        Clear filters
                      </button>
                    ) : undefined
                  }
                />
              ) : (
                page.items.map((row) => (
                  <tr key={row.id} className="border-b last:border-0 hover:bg-page-bg/50 transition-colors">
                    <td className="px-5 py-3 text-xs tabular-nums text-brand-grey-dark">
                      {formatDateTime(row.created_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Badge
                        label={row.connection_type}
                        colorClass={CONNECTION_TYPE_COLORS[row.connection_type] ?? FALLBACK_BADGE_COLOR}
                      />
                    </td>
                    <td className="px-5 py-3">
                      <Badge
                        label={row.status}
                        colorClass={CALL_SESSION_STATUS_COLORS[row.status] ?? FALLBACK_BADGE_COLOR}
                      />
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums">{row.call_count}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-brand-grey-dark">
                      {row.duration != null ? `${row.duration}s` : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-brand-grey-dark">
          <button
            onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
            disabled={skip === 0}
            className={BUTTON_SECONDARY}
          >
            ← Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setSkip(skip + PAGE_SIZE)}
            disabled={skip + PAGE_SIZE >= page.total}
            className={BUTTON_SECONDARY}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
