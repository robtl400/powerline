import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PAGE_HEADING } from "@/lib/styles";
import {
  Line,
  LineChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import client from "@/api/client";
import { formatDate } from "@/lib/formatters";

interface DailyCount {
  date: string;
  count: number;
}

interface DashboardData {
  calls_today: number;
  calls_this_week: number;
  calls_this_month: number;
  active_campaigns: number;
  webrtc_count: number;
  phone_count: number;
  calls_last_7_days: DailyCount[];
}

interface Campaign {
  id: string;
  name: string;
  status: string;
  campaign_type: string;
  target_count: number;
  created_at: string;
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-lg border bg-card p-5 shadow-sm">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      client.get<DashboardData>("/admin/dashboard"),
      client.get<Campaign[]>("/campaigns?status=live"),
    ])
      .then(([dashRes, campRes]) => {
        setData(dashRes.data);
        setCampaigns(campRes.data);
        setError(null);
      })
      .catch(() => setError("Failed to load dashboard data."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-destructive/10 text-destructive px-4 py-3 text-sm">
        {error}
      </div>
    );
  }

  const totalCalls = (data?.webrtc_count ?? 0) + (data?.phone_count ?? 0);
  const webrtcPct =
    totalCalls > 0 ? Math.round(((data?.webrtc_count ?? 0) / totalCalls) * 100) : 0;

  const chartData =
    data?.calls_last_7_days.map((d) => ({
      date: formatDate(d.date),
      calls: d.count,
    })) ?? [];

  return (
    <div className="space-y-8">
      <h1 className={PAGE_HEADING}>Dashboard</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Calls Today" value={data?.calls_today ?? 0} />
        <StatCard label="Calls This Week" value={data?.calls_this_week ?? 0} />
        <StatCard label="Calls This Month" value={data?.calls_this_month ?? 0} />
        <StatCard
          label="Active Campaigns"
          value={data?.active_campaigns ?? 0}
          sub={totalCalls > 0 ? `${webrtcPct}% via WebRTC` : undefined}
        />
      </div>

      {/* 7-day call volume chart */}
      <div className="rounded-lg border bg-card p-5 shadow-sm">
        <h2 className="mb-4 text-sm font-medium text-muted-foreground">
          Call Volume — Last 7 Days
        </h2>
        {chartData.every((d) => d.calls === 0) ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No calls recorded yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 2,
                  border: "1px solid hsl(var(--border))",
                  background: "hsl(var(--card))",
                  color: "hsl(var(--foreground))",
                }}
                cursor={{ stroke: "hsl(var(--border))", strokeWidth: 1 }}
              />
              {/* Primary series — small solid dot */}
              <Line
                type="monotone"
                dataKey="calls"
                name="Calls"
                stroke="#F2542D"
                strokeWidth={1.5}
                dot={{ r: 3, fill: "#F2542D", strokeWidth: 0 }}
                activeDot={{ r: 4, fill: "#F2542D", strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Live campaigns table */}
      <div className="rounded-lg border bg-card shadow-sm">
        <div className="border-b px-5 py-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">Live Campaigns</h2>
          <button
            onClick={() => navigate("/campaigns")}
            className="text-xs text-[#111111] hover:underline"
          >
            View all
          </button>
        </div>
        {campaigns.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-muted-foreground">
            <p>No live campaigns.</p>
            <button
              onClick={() => navigate("/campaigns/new")}
              className="mt-1 text-[#F2542D] underline underline-offset-2 hover:opacity-80 font-semibold"
            >
              Create one
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#53565B] text-left text-xs text-white">
                <th className="px-5 py-2 font-medium">Campaign</th>
                <th className="px-5 py-2 font-medium">Type</th>
                <th className="px-5 py-2 font-medium">Targets</th>
                <th className="px-5 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr
                  key={c.id}
                  className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="px-5 py-3 font-medium">{c.name}</td>
                  <td className="px-5 py-3 capitalize text-muted-foreground">{c.campaign_type}</td>
                  <td className="px-5 py-3 text-muted-foreground">{c.target_count}</td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => navigate(`/campaigns/${c.id}/edit`)}
                      className="text-xs text-primary hover:underline"
                    >
                      Manage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
