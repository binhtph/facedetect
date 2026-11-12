import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Pause, Play, Search, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, type MqttMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/mqtt")({
  head: () => ({ meta: [{ title: "MQTT Monitor - IRIS" }] }),
  component: MqttMonitorPage,
});

const directionInfo: Record<
  MqttMessage["direction"],
  { label: string; icon: typeof Zap; cls: string }
> = {
  out: { label: "Sent", icon: ArrowUpRight, cls: "text-primary" },
  in: { label: "Received", icon: ArrowDownLeft, cls: "text-success" },
  system: { label: "Connection", icon: Zap, cls: "text-warning" },
};

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function prettyPayload(payload: string) {
  try {
    return JSON.stringify(JSON.parse(payload), null, 2);
  } catch {
    return payload;
  }
}

function MqttMonitorPage() {
  const queryClient = useQueryClient();
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["mqtt-messages"],
    queryFn: () => api.mqttMessages(200),
    refetchInterval: paused ? false : 2000,
  });
  const clear = useMutation({
    mutationFn: api.clearMqttMessages,
    onSuccess: () => {
      toast.success("Message log cleared");
      queryClient.invalidateQueries({ queryKey: ["mqtt-messages"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const status = data?.status;
  const messages = useMemo(() => {
    const items = data?.messages ?? [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (item) =>
        item.topic.toLowerCase().includes(needle) || item.payload.toLowerCase().includes(needle),
    );
  }, [data?.messages, filter]);

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Integration"
        title="MQTT monitor"
        description="Live view of what IRIS sends to and receives from Home Assistant over MQTT."
        actions={
          <>
            <Button variant="outline" onClick={() => setPaused((value) => !value)}>
              {paused ? <Play className="mr-2 h-4 w-4" /> : <Pause className="mr-2 h-4 w-4" />}
              {paused ? "Resume" : "Pause"}
            </Button>
            <Button variant="outline" onClick={() => clear.mutate()} disabled={clear.isPending}>
              <Trash2 className="mr-2 h-4 w-4" /> Clear
            </Button>
          </>
        }
      />

      <Card className="border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              status?.connected
                ? "bg-success"
                : status?.configured
                  ? "bg-destructive"
                  : "bg-muted-foreground"
            }`}
          />
          <span className="text-sm font-semibold">
            {!status
              ? "Loading…"
              : !status.configured
                ? "MQTT is not configured"
                : status.connected
                  ? `Connected to ${status.host}:${status.port}`
                  : `Disconnected from ${status.host}:${status.port} — retrying`}
          </span>
          {status?.client_id && (
            <Badge variant="outline" className="font-mono text-[11px]">
              client id: {status.client_id}
            </Badge>
          )}
        </div>
        {status?.configured && (
          <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-muted-foreground sm:grid-cols-3">
            <div>Last connected: {formatDateTime(status.last_connected_at)}</div>
            <div>Last disconnected: {formatDateTime(status.last_disconnected_at)}</div>
            <div className={status.last_error ? "text-destructive" : undefined}>
              Last error: {status.last_error || "none"}
            </div>
          </div>
        )}
      </Card>

      <Card className="border-border bg-card p-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by topic or payload…"
            className="pl-9"
          />
        </div>
      </Card>

      <Card className="overflow-hidden border-border bg-card p-0">
        {messages.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-muted-foreground">
            No MQTT messages yet. Recognitions, discovery and camera trigger commands show up here.
          </div>
        ) : (
          <div className="divide-y divide-border font-mono text-xs">
            {messages.map((message, index) => {
              const info = directionInfo[message.direction] ?? directionInfo.system;
              const Icon = info.icon;
              const key = `${message.time}-${index}`;
              const isOpen = expanded === key;
              return (
                <button
                  type="button"
                  key={key}
                  onClick={() => setExpanded(isOpen ? null : key)}
                  className="block w-full px-4 py-2.5 text-left hover:bg-surface-elevated/40"
                >
                  <div className="grid grid-cols-12 items-center gap-2">
                    <span className="col-span-3 text-muted-foreground sm:col-span-2">
                      {formatTime(message.time)}
                    </span>
                    <span
                      className={`col-span-3 flex items-center gap-1 sm:col-span-2 ${info.cls}`}
                    >
                      <Icon className="h-3.5 w-3.5" /> {info.label}
                    </span>
                    <span className="col-span-6 truncate sm:col-span-5">
                      {message.topic || "—"}
                    </span>
                    <span className="hidden truncate text-muted-foreground sm:col-span-3 sm:block">
                      {[
                        message.direction !== "system" ? `QoS ${message.qos}` : "",
                        message.retain ? "retained" : "",
                        message.status,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                  {isOpen ? (
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/50 p-3 text-[11px]">
                      {prettyPayload(message.payload)}
                    </pre>
                  ) : (
                    <div className="mt-1 truncate text-muted-foreground">{message.payload}</div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </Card>
    </PageShell>
  );
}
