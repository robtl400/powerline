import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CampaignStats, DailyCount, QualityData } from "@/types/campaign";

export function CampaignStatsTab({
  campaignStats,
  qualityData,
  chartData,
  statsLoading,
  statsError,
  statsStartDate,
  setStatsStartDate,
  statsEndDate,
  setStatsEndDate,
  statsGranularity,
  setStatsGranularity,
  onViewCallLog,
}: {
  campaignStats: CampaignStats | null;
  qualityData: QualityData | null;
  chartData: DailyCount[];
  statsLoading: boolean;
  statsError: string | null;
  statsStartDate: string;
  setStatsStartDate: (v: string) => void;
  statsEndDate: string;
  setStatsEndDate: (v: string) => void;
  statsGranularity: "day" | "week";
  setStatsGranularity: (v: "day" | "week") => void;
  onViewCallLog: () => void;
}) {
  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Campaign Analytics</h2>
        <button
          onClick={onViewCallLog}
          className="text-xs px-3 py-1.5 border border-border rounded hover:bg-muted/50 transition-colors"
        >
          View Call Log →
        </button>
      </div>

      {statsLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {statsError && (
        <div className="rounded-md bg-destructive/10 text-destructive px-4 py-3 text-sm">
          {statsError}
        </div>
      )}

      {!statsLoading && !statsError && campaignStats && (
        <>
          {/* Summary metrics */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <p className="text-xs text-muted-foreground">Total Sessions</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{campaignStats.total_sessions}</p>
            </div>
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <p className="text-xs text-muted-foreground">Completion Rate</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {(campaignStats.completion_rate * 100).toFixed(1)}%
              </p>
            </div>
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <p className="text-xs text-muted-foreground">Avg Calls / Session</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{campaignStats.avg_calls_per_session.toFixed(1)}</p>
            </div>
            <div className="rounded-lg border bg-card p-4 shadow-sm">
              <p className="text-xs text-muted-foreground">Connection Type</p>
              <p className="mt-1 text-sm font-medium">
                {campaignStats.connection_type_breakdown["webrtc"] ?? 0} WebRTC
              </p>
              <p className="text-sm text-muted-foreground">
                {campaignStats.connection_type_breakdown["outbound_phone"] ?? 0} Phone
              </p>
            </div>
          </div>

          {/* Volume chart with date controls */}
          <div className="rounded-lg border bg-card p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <h3 className="text-sm font-medium flex-1">Call Volume</h3>
              <input
                type="date"
                className="text-xs border border-border rounded px-2 py-1 bg-background"
                value={statsStartDate}
                max={statsEndDate}
                onChange={(e) => setStatsStartDate(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">to</span>
              <input
                type="date"
                className="text-xs border border-border rounded px-2 py-1 bg-background"
                value={statsEndDate}
                min={statsStartDate}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setStatsEndDate(e.target.value)}
              />
              <select
                className="text-xs border border-border rounded px-2 py-1 bg-background"
                value={statsGranularity}
                onChange={(e) => setStatsGranularity(e.target.value as "day" | "week")}
              >
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
              </select>
            </div>
            {chartData.length === 0 || chartData.every((d) => d.count === 0) ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No calls in this date range.</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 6,
                      border: "1px solid hsl(var(--border))",
                      background: "hsl(var(--card))",
                      color: "hsl(var(--foreground))",
                    }}
                    cursor={{ fill: "hsl(var(--muted))" }}
                  />
                  <Bar dataKey="count" name="Calls" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Per-target breakdown */}
          {campaignStats.per_target.length > 0 && (
            <div className="rounded-lg border bg-card shadow-sm">
              <div className="border-b px-5 py-3">
                <h3 className="text-sm font-medium">Per-Target Breakdown</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="px-5 py-2 font-medium">Target</th>
                    <th className="px-5 py-2 font-medium text-right">Total Calls</th>
                    <th className="px-5 py-2 font-medium text-right">Completed</th>
                    <th className="px-5 py-2 font-medium text-right">Avg Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {campaignStats.per_target.map((t) => (
                    <tr key={t.target_id} className="border-b last:border-0">
                      <td className="px-5 py-2.5">{t.name}</td>
                      <td className="px-5 py-2.5 text-right tabular-nums">{t.total_calls}</td>
                      <td className="px-5 py-2.5 text-right tabular-nums">{t.completed_calls}</td>
                      <td className="px-5 py-2.5 text-right tabular-nums text-muted-foreground">
                        {t.avg_duration_seconds != null
                          ? `${Math.round(t.avg_duration_seconds)}s`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Call Quality panel — only shown when Twilio Voice Insights data exists */}
          {qualityData && qualityData.calls_with_quality > 0 && (
            <div className="rounded-lg border bg-card p-5 shadow-sm">
              <h3 className="text-sm font-medium mb-4">Call Quality (Voice Insights)</h3>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Avg Quality Score</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">
                    {qualityData.avg_quality_score?.toFixed(1) ?? "—"} / 5
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Connection Rate</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">
                    {(qualityData.connection_rate * 100).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Scored Calls</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">
                    {qualityData.calls_with_quality} / {qualityData.total_calls}
                  </p>
                </div>
              </div>
              {Object.keys(qualityData.failure_breakdown).length > 0 && (
                <div className="mt-4 border-t pt-3">
                  <p className="text-xs text-muted-foreground mb-2">Failures</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(qualityData.failure_breakdown).map(([k, v]) => (
                      <span key={k} className="text-xs px-2 py-1 bg-muted/50 rounded">
                        {k.replace("_", " ")}: {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
