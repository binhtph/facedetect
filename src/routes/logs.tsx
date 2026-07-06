import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Download,
  RefreshCcw,
  AlertCircle,
  AlertTriangle,
  Info,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

export const Route = createFileRoute("/logs")({
  head: () => ({ meta: [{ title: "System Logs - IRIS" }] }),
  component: LogsPage,
});

const sevIcon = {
  info: <Info className="h-3.5 w-3.5 text-primary" />,
  warn: <AlertTriangle className="h-3.5 w-3.5 text-warning" />,
  error: <AlertCircle className="h-3.5 w-3.5 text-destructive" />,
};

const sevTone = {
  info: "text-primary",
  warn: "text-warning",
  error: "text-destructive",
};

function formatLogTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function LogsPage() {
  const [page, setPage] = useState(1);
  const { data: logsSettings } = useQuery({
    queryKey: ["logs-settings"],
    queryFn: api.logsSettings,
  });
  const perPage = 50;
  const { data, refetch } = useQuery({
    queryKey: ["logs", page, perPage, logsSettings?.max_rows],
    queryFn: () => api.logs(page, perPage),
    enabled: Boolean(logsSettings),
  });
  const logs = useMemo(() => data?.items ?? [], [data?.items]);
  const totalPages = data?.total_pages ?? 1;
  const totalEntries = data?.total ?? 0;
  const currentPage = data?.page ?? 1;

  useEffect(() => {
    if (data && data.page !== page) setPage(data.page);
  }, [data, page]);

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all-sev");
  const [service, setService] = useState("all-svc");
  const filtered = useMemo(
    () =>
      logs.filter((log) => {
        const matchesSearch = log.message.toLowerCase().includes(search.toLowerCase());
        const matchesSeverity = severity === "all-sev" || log.severity === severity;
        const matchesService = service === "all-svc" || log.service === service;
        return matchesSearch && matchesSeverity && matchesService;
      }),
    [logs, search, service, severity],
  );

  const exportLogs = () => {
    const rows = [
      ["time", "service", "severity", "message"],
      ...filtered.map((log) => [
        formatLogTime(log.created_at),
        log.service,
        log.severity,
        log.message,
      ]),
    ];
    const csv = rows
      .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "iris-logs.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const goToPage = (p: number) => {
    const clamped = Math.max(1, Math.min(p, totalPages));
    setPage(clamped);
  };

  const formatMessage = (message: string) => {
    const rawPrefix = " raw: ";
    const rawIndex = message.indexOf(rawPrefix);
    if (rawIndex === -1) return message;
    const title = message.slice(0, rawIndex + rawPrefix.length);
    const raw = message.slice(rawIndex + rawPrefix.length);
    try {
      return `${title}\n${JSON.stringify(JSON.parse(raw), null, 2)}`;
    } catch {
      return message;
    }
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Audit"
        title="System logs"
        description="Aggregated activity from InsightFace, recognition, camera, and system services."
        actions={
          <>
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCcw className="mr-2 h-4 w-4" /> Refresh
            </Button>
            <Button variant="outline" onClick={exportLogs}>
              <Download className="mr-2 h-4 w-4" /> Export
            </Button>
          </>
        }
      />

      <Card className="border-border bg-card p-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
          <div className="relative md:col-span-2">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search messages..."
              className="pl-9"
            />
          </div>
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-sev">All severity</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warn">Warning</SelectItem>
              <SelectItem value="error">Error</SelectItem>
            </SelectContent>
          </Select>
          <Select value={service} onValueChange={setService}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-svc">All services</SelectItem>
              <SelectItem value="InsightFace">InsightFace</SelectItem>
              <SelectItem value="UniFi">UniFi</SelectItem>
              <SelectItem value="Recognition">Recognition</SelectItem>
              <SelectItem value="Notification">Notification</SelectItem>
              <SelectItem value="System">System</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>

      <Card className="overflow-hidden border-border bg-card p-0">
        <div className="divide-y divide-border font-mono text-xs">
          {filtered.map((log) => (
            <div
              key={log.id}
              className="grid grid-cols-1 gap-1 px-4 py-3 hover:bg-surface-elevated/40 sm:grid-cols-12 sm:items-center sm:gap-3 sm:py-2.5"
            >
              <div className="text-muted-foreground sm:col-span-2">
                {formatLogTime(log.created_at)}
              </div>
              <div className="flex items-center gap-1 sm:col-span-1">
                {sevIcon[log.severity]}
                <span className={`uppercase ${sevTone[log.severity]}`}>{log.severity}</span>
              </div>
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground sm:col-span-2">
                {log.service}
              </div>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono sm:col-span-7">
                {formatMessage(log.message)}
              </pre>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No logs found.
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2 border-t border-border px-4 py-2 font-mono text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>
            /// {filtered.length} shown of {totalEntries} total entries
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={currentPage <= 1}
                onClick={() => goToPage(1)}
              >
                <ChevronsLeft className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={currentPage <= 1}
                onClick={() => goToPage(currentPage - 1)}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="px-2 tabular-nums">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={currentPage >= totalPages}
                onClick={() => goToPage(currentPage + 1)}
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={currentPage >= totalPages}
                onClick={() => goToPage(totalPages)}
              >
                <ChevronsRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </Card>
    </PageShell>
  );
}
