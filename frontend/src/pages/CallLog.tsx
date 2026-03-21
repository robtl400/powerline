import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "@/api/client";
import {
  CALL_SESSION_STATUS_COLORS,
  CONNECTION_TYPE_COLORS,
  FALLBACK_BADGE_COLOR,
} from "@/lib/constants";
import { formatDateTime } from "@/lib/formatters";

interface CallSessionRow {
  id: string;
  created_at: string;
  connection_type: string;
  status: string;
  call_count: number;
  duration: number | null;
}

interface CallSessionPage {
  total: number;
  items: CallSessionRow[];
}

interface CampaignBasic {
  id: string;
  name: string;
}

function Badge({ label, colorClass }: { label: string; colorClass: string }) {
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${colorClass}`}>
      {label.replace("_", " ")}
    </span>
  );
}

const PAGE_SIZE = 50;

export default function CallLog() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [campaign, setCampaign] = useState<CampaignBasic | null>(null);
  const [page, setPage] = useState<CallSessionPage>({ total: 0, items: [] });
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
      .get<CampaignBasic>(`/campaigns/${id}`)
      .then((res) => setCampaign(res.data))
      .catch(() => null);
  }, [id]);

  // Load call sessions
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    client
      .get<CallSessionPage>(`/campaigns/${id}/calls?${buildParams()}`)
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
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(`/campaigns/${id}/edit`)}
          className="text-sm text-brand-grey-light hover:text-brand-black"
        >
          ← {campaign?.name ?? "Campaign"}
        </button>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-xl font-semibold tracking-tight">Call Log</h1>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] p-4">
        <div>
          <label className="block text-xs text-brand-grey-light mb-1">Status</label>
          <select
            className="text-sm border border-brand-border rounded px-2 py-1.5 bg-white min-w-[120px]"
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
          <label className="block text-xs text-brand-grey-light mb-1">Type</label>
          <select
            className="text-sm border border-brand-border rounded px-2 py-1.5 bg-white min-w-[140px]"
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
          <label className="block text-xs text-brand-grey-light mb-1">From</label>
          <input
            type="date"
            className="text-sm border border-brand-border rounded px-2 py-1.5 bg-white"
            value={startDate}
            max={endDate || undefined}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-brand-grey-light mb-1">To</label>
          <input
            type="date"
            className="text-sm border border-brand-border rounded px-2 py-1.5 bg-white"
            value={endDate}
            min={startDate || undefined}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <div className="flex gap-2 ml-auto">
          <button
            onClick={applyFilters}
            className="px-3 py-1.5 bg-brand-orange text-white rounded text-sm hover:opacity-90 transition-opacity"
          >
            Apply
          </button>
          <button
            onClick={clearFilters}
            className="px-3 py-1.5 border border-brand-border rounded text-sm hover:bg-page-bg transition-colors"
          >
            Clear
          </button>
          <button
            onClick={handleCsvExport}
            disabled={csvLoading}
            className="px-3 py-1.5 border border-brand-border rounded text-sm hover:bg-page-bg transition-colors disabled:opacity-50"
          >
            {csvLoading ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-page-bg text-brand-grey-dark px-4 py-3 text-sm border border-brand-border">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="rounded-[10px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] overflow-x-auto">
        <div className="border-b px-5 py-3 flex items-center justify-between">
          <p className="text-sm text-brand-grey-light">
            {page.total} session{page.total !== 1 ? "s" : ""}
          </p>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-brand-grey-light">Loading…</p>
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
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-brand-grey-light">
                    {hasActiveFilters ? (
                      <>No sessions match your filters — <button onClick={clearFilters} className="text-brand-orange hover:underline">Clear filters</button></>
                    ) : "No call sessions yet"}
                  </td>
                </tr>
              ) : (
                page.items.map((row) => (
                  <tr key={row.id} className="border-b last:border-0 hover:bg-page-bg/50 transition-colors">
                    <td className="px-5 py-3 font-mono text-xs text-brand-grey-light">
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
                    <td className="px-5 py-3 text-right tabular-nums text-brand-grey-light">
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
        <div className="flex items-center justify-between text-sm text-brand-grey-light">
          <button
            onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
            disabled={skip === 0}
            className="px-3 py-1.5 border border-border rounded hover:bg-muted/50 disabled:opacity-40 transition-colors"
          >
            ← Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setSkip(skip + PAGE_SIZE)}
            disabled={skip + PAGE_SIZE >= page.total}
            className="px-3 py-1.5 border border-border rounded hover:bg-muted/50 disabled:opacity-40 transition-colors"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
