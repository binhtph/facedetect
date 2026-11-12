import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { RefreshCcw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/analytics")({
  head: () => ({ meta: [{ title: "Analytics - IRIS" }] }),
  component: AnalyticsPage,
});

const SERIES = [
  { key: "known", label: "Recognized", color: "var(--success)" },
  { key: "review", label: "Needs review", color: "var(--warning)" },
  { key: "unknown", label: "Unknown", color: "var(--destructive)" },
  { key: "no_face", label: "No face", color: "var(--muted-foreground)" },
] as const;

const axisProps = {
  stroke: "var(--muted-foreground)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

const tooltipStyle = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    fontSize: 12,
    color: "var(--popover-foreground)",
  },
  cursor: { fill: "var(--muted)", opacity: 0.4 },
};

function shortDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card className="border-border bg-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </Card>
  );
}

function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["analytics", days],
    queryFn: () => api.analytics(days),
    refetchInterval: 30000,
  });
  const summary = data?.summary;
  const hasData = (summary?.total ?? 0) > 0;

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Insights"
        title="Analytics"
        description="Who was seen, when, and how confident the recognition was."
        actions={
          <>
            <Select value={String(days)} onValueChange={(value) => setDays(Number(value))}>
              <SelectTrigger className="sm:w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Today</SelectItem>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCcw className={`mr-2 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Events" value={summary?.total ?? "–"} />
        <Stat
          label="Recognized"
          value={summary ? summary.known + summary.review : "–"}
          hint={summary ? `${summary.recognized_rate}% of faces` : undefined}
        />
        <Stat label="Unknown" value={summary?.unknown ?? "–"} />
        <Stat label="People seen" value={summary?.unique_people ?? "–"} />
        <Stat
          label="Avg confidence"
          value={summary?.avg_known_confidence ? `${summary.avg_known_confidence}%` : "–"}
          hint="auto-accepted matches"
        />
        <Stat
          label="Avg processing"
          value={summary?.avg_processing_ms ? `${Math.round(summary.avg_processing_ms)} ms` : "–"}
        />
      </div>

      {!isLoading && !hasData ? (
        <Card className="border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No recognition events in this period yet.
        </Card>
      ) : (
        <>
          <Card className="border-border bg-card p-5">
            <h3 className="text-sm font-semibold">Recognitions per day</h3>
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.daily ?? []}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} {...axisProps} />
                  <YAxis allowDecimals={false} width={32} {...axisProps} />
                  <Tooltip {...tooltipStyle} labelFormatter={(value) => shortDate(String(value))} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {SERIES.map((series) => (
                    <Bar
                      key={series.key}
                      dataKey={series.key}
                      name={series.label}
                      stackId="events"
                      fill={series.color}
                      radius={series.key === "no_face" ? [3, 3, 0, 0] : 0}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card className="border-border bg-card p-5">
              <h3 className="text-sm font-semibold">Busiest hours</h3>
              <p className="text-xs text-muted-foreground">All events, in your local time</p>
              <div className="mt-4 h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data?.hourly ?? []}>
                    <CartesianGrid stroke="var(--border)" vertical={false} />
                    <XAxis
                      dataKey="hour"
                      tickFormatter={(hour) => `${String(hour).padStart(2, "0")}h`}
                      interval={2}
                      {...axisProps}
                    />
                    <YAxis allowDecimals={false} width={32} {...axisProps} />
                    <Tooltip
                      {...tooltipStyle}
                      labelFormatter={(hour) => `${String(hour).padStart(2, "0")}:00`}
                    />
                    <Bar
                      dataKey="count"
                      name="Events"
                      fill="var(--primary)"
                      radius={[3, 3, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card className="border-border bg-card p-5">
              <h3 className="text-sm font-semibold">By camera</h3>
              <ul className="mt-3 space-y-2">
                {(data?.cameras ?? []).map((camera) => {
                  const max = data?.cameras[0]?.count || 1;
                  return (
                    <li key={camera.camera_name}>
                      <div className="flex justify-between text-xs">
                        <span className="truncate">{camera.camera_name}</span>
                        <span className="font-mono tabular-nums text-muted-foreground">
                          {camera.count}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full bg-primary"
                          style={{ width: `${(camera.count / max) * 100}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>

          <Card className="overflow-hidden border-border bg-card p-0">
            <div className="border-b border-border px-5 py-4">
              <h3 className="text-sm font-semibold">Most seen people</h3>
            </div>
            {(data?.top_people.length ?? 0) === 0 ? (
              <div className="px-5 py-6 text-sm text-muted-foreground">
                Nobody was recognized in this period.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {data?.top_people.map((person, index) => (
                  <div
                    key={person.person_id}
                    className="grid grid-cols-12 items-center gap-3 px-5 py-2.5 text-sm"
                  >
                    <span className="col-span-1 font-mono text-xs text-muted-foreground">
                      {index + 1}
                    </span>
                    <Link
                      to="/people/$personId"
                      params={{ personId: person.person_id }}
                      className="col-span-5 truncate font-medium hover:underline"
                    >
                      {person.person_name}
                    </Link>
                    <span className="col-span-2 text-right font-mono tabular-nums">
                      {person.count}×
                    </span>
                    <span className="col-span-2 text-right font-mono text-xs tabular-nums text-muted-foreground">
                      {person.avg_confidence.toFixed(1)}%
                    </span>
                    <span className="col-span-2 truncate text-right text-xs text-muted-foreground">
                      {formatDateTime(person.last_seen)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </PageShell>
  );
}
