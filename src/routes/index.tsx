import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Users,
  UserX,
  ShieldAlert,
  Clock,
  Cloud,
  RadioTower,
  Send,
  ScanFace,
  HardDrive,
  AlertTriangle,
  Camera,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Snapshot } from "@/components/snapshot";
import { api, uploadUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { EventItem } from "@/lib/types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard - IRIS" },
      { name: "description", content: "Visitor recognition overview." },
    ],
  }),
  component: Dashboard,
});

function parseJsonObject(value?: string): Record<string, unknown> | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

type FaceBoundingBox = { Left?: number; Top?: number; Width?: number; Height?: number };

function isBoundingBox(value: unknown): value is FaceBoundingBox {
  return Boolean(
    value &&
    typeof value === "object" &&
    typeof (value as FaceBoundingBox).Width === "number" &&
    typeof (value as FaceBoundingBox).Height === "number",
  );
}

function eventBoundingBox(event?: EventItem | null): FaceBoundingBox | undefined {
  if (!event) return undefined;
  const fromEvent = parseJsonObject(event.face_bounding_box);
  if (isBoundingBox(fromEvent)) return fromEvent;
  const fromDetails = parseJsonObject(event.face_details_json)?.bounding_box;
  return isBoundingBox(fromDetails) ? fromDetails : undefined;
}

function eventPreviewPath(event: EventItem) {
  return event.face_crop_path || event.image_path || event.thumb_path;
}

function previewBoundingBox(event?: EventItem | null): FaceBoundingBox | undefined {
  if (!event || event.face_crop_path) return undefined;
  return eventBoundingBox(event);
}

function Dashboard() {
  const { data: summary } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: 5000,
  });
  const { data: storage } = useQuery({
    queryKey: ["storage-settings"],
    queryFn: api.storage,
    refetchInterval: 15000,
  });
  const events = summary?.events ?? [];
  const stats = summary?.summary;

  const latest = events[0];
  const latestBoundingBox = previewBoundingBox(latest);
  const unknownCount = stats?.unknown ?? 0;
  const latestDetectionValue = latest
    ? latest.type === "no_face"
      ? "No face"
      : latest.type === "skipped"
        ? "Skipped"
        : latest.type === "error"
          ? "Error"
          : latest.personName || latest.person_name || "Unknown"
    : "None";

  const services = [
    {
      label: "Storage",
      value: storage ? `${storage.used_mb} / ${storage.max_storage_mb} MB` : "Loading...",
      detail: "",
      percent: storage?.percent ?? 0,
      icon: HardDrive,
      ok: true,
      showStatus: false,
    },
    {
      label: "InsightFace",
      value: summary?.services.insightface
        ? summary.local_inference.average_processing_ms > 0
          ? `${summary.local_inference.average_processing_ms.toFixed(0)} ms avg`
          : "No timing data"
        : "Not configured",
      detail: "",
      percent: undefined,
      icon: Cloud,
      ok: Boolean(summary?.services.insightface),
      showStatus: true,
    },
    {
      label: "MQTT",
      value: summary?.services.mqtt ? "Connected" : "Not configured",
      detail: "",
      percent: undefined,
      icon: RadioTower,
      ok: Boolean(summary?.services.mqtt),
      showStatus: true,
    },
    {
      label: "Telegram",
      value: summary?.services.telegram ? "Active" : "Not configured",
      detail: "",
      percent: undefined,
      icon: Send,
      ok: Boolean(summary?.services.telegram),
      showStatus: true,
    },
  ];

  const dynamicStats = [
    {
      label: "Local face embeddings",
      value: String(summary?.local_inference.indexed_faces ?? 0),
      detail: summary?.local_inference.model ?? "buffalo_s",
      icon: ScanFace,
      tone: "text-success",
    },
    {
      label: "Unknown pending",
      value: String(unknownCount),
      icon: UserX,
      tone: "text-warning",
    },
    {
      label: "Known people",
      value: String(stats?.people ?? 0),
      icon: ShieldAlert,
      tone: "text-primary",
    },
    { label: "Last detection", value: latestDetectionValue, icon: Clock, tone: "text-primary" },
  ];

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Overview"
        title="Dashboard"
        description="Real-time activity from cameras matched against InsightFace."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/events">All events</Link>
            </Button>
            <Button asChild>
              <Link to="/people">
                <Users className="mr-2 h-4 w-4" /> Manage people
              </Link>
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {services.map((s) => (
          <Card key={s.label} className="border-border bg-card p-3 sm:p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {s.label}
              </span>
              {s.showStatus && (
                <span
                  className={`h-2 w-2 rounded-full ${s.ok ? "bg-success animate-pulse" : "bg-destructive"}`}
                />
              )}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <s.icon className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">{s.value}</span>
            </div>
            {s.percent !== undefined && (
              <>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full ${(s.percent ?? 0) >= 90 ? "bg-warning" : "bg-primary"}`}
                    style={{ width: `${Math.min(100, s.percent ?? 0)}%` }}
                  />
                </div>
              </>
            )}
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {dynamicStats.map((s) => (
          <Card key={s.label} className="relative overflow-hidden border-border bg-card p-3 sm:p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {s.label}
            </div>
            <div className="mt-1 flex min-w-0 items-end justify-between gap-2">
              <span
                className={`min-w-0 truncate font-display text-xl font-semibold sm:text-2xl md:text-3xl ${s.tone}`}
                title={s.value}
              >
                {s.value}
              </span>
              <s.icon className={`h-5 w-5 ${s.tone} opacity-70`} />
            </div>
            {s.detail && (
              <div className="mt-1 font-mono text-[10px] text-muted-foreground">{s.detail}</div>
            )}
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2 overflow-hidden border-border bg-card p-0">
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3 sm:px-5">
            <h3 className="text-sm font-semibold">Activity feed</h3>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/events">View all -&gt;</Link>
            </Button>
          </div>
          <div className="divide-y divide-border">
            {events.slice(0, 6).map((e) => (
              <Link
                key={e.id}
                to="/events/$eventId"
                params={{ eventId: e.id }}
                className="flex items-start gap-3 px-4 py-3 hover:bg-surface-elevated/50 sm:items-center sm:px-5"
              >
                <Snapshot
                  size="sm"
                  unknown={e.type === "unknown"}
                  src={uploadUrl(eventPreviewPath(e))}
                  boundingBox={previewBoundingBox(e)}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="min-w-0 truncate font-medium">{e.personName}</span>
                    {e.type === "known" && (
                      <Badge variant="outline" className="border-success/40 text-success">
                        recognized
                      </Badge>
                    )}
                    {e.type === "unknown" && (
                      <Badge variant="outline" className="border-warning/40 text-warning">
                        unknown
                      </Badge>
                    )}
                    {e.type === "review" && (
                      <Badge variant="outline" className="border-warning/40 text-warning">
                        review
                      </Badge>
                    )}
                    {e.type === "no_face" && (
                      <Badge
                        variant="outline"
                        className="border-muted-foreground/30 text-muted-foreground"
                      >
                        no face
                      </Badge>
                    )}
                    {e.type === "skipped" && (
                      <Badge
                        variant="outline"
                        className="border-muted-foreground/30 text-muted-foreground"
                      >
                        skipped
                      </Badge>
                    )}
                    {e.type === "error" && (
                      <Badge variant="outline" className="border-destructive/40 text-destructive">
                        error
                      </Badge>
                    )}
                    {e.type === "processing" && (
                      <Badge variant="outline" className="border-primary/30 text-primary">
                        processing
                      </Badge>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-muted-foreground">
                    <Camera className="h-3 w-3" /> {e.cameraName}
                    <span>-</span>
                    <span>{formatDateTime(e.time)}</span>
                  </div>
                </div>
                {e.confidence > 0 && (
                  <span className="hidden font-mono text-xs text-success sm:inline">
                    {e.confidence.toFixed(1)}%
                  </span>
                )}
              </Link>
            ))}
            {events.length === 0 && (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No recognition events yet.
              </div>
            )}
          </div>
        </Card>

        <Card className="border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Latest detection</h3>
          {latest ? (
            <div className="mt-4 flex flex-col items-center text-center">
              <Snapshot
                size="lg"
                label={latest.personName}
                confidence={latest.confidence}
                unknown={latest.type === "unknown"}
                src={uploadUrl(eventPreviewPath(latest))}
                boundingBox={latestBoundingBox}
              />
              <div className="mt-4 w-full space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Person</span>
                  <span className="font-medium">{latest.personName}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Confidence</span>
                  <span className="font-mono text-success">{latest.confidence.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Camera</span>
                  <span className="font-mono">{latest.cameraName}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Time</span>
                  <span className="font-mono">{formatDateTime(latest.time)}</span>
                </div>
              </div>
              <Button variant="outline" size="sm" className="mt-4 w-full" asChild>
                <Link to="/events/$eventId" params={{ eventId: latest.id }}>
                  View event
                </Link>
              </Button>
            </div>
          ) : (
            <div className="mt-4 rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              Upload a snapshot from Events to start recognition.
            </div>
          )}
        </Card>
      </div>

      {unknownCount > 0 && (
        <Card className="border-warning/40 bg-warning/5 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
            <AlertTriangle className="h-5 w-5 shrink-0 text-warning" />
            <div className="flex-1">
              <h4 className="text-sm font-semibold">
                {unknownCount} unknown {unknownCount === 1 ? "visitor" : "visitors"} pending review
              </h4>
              <p className="text-xs text-muted-foreground">
                Assign them to existing people or create new records.
              </p>
            </div>
            <Button asChild variant="outline" size="sm" className="w-full sm:w-auto">
              <Link to="/unknown">Review</Link>
            </Button>
          </div>
        </Card>
      )}
    </PageShell>
  );
}
