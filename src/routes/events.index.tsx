import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Calendar,
  Download,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Camera,
  Clock,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Snapshot } from "@/components/snapshot";
import { api, uploadUrl, type EventItem } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/events/")({
  head: () => ({ meta: [{ title: "Events - IRIS" }] }),
  component: EventsList,
});

function statusBadge(t: string) {
  const base =
    "h-7 w-auto justify-center gap-1 whitespace-nowrap px-2 text-[11px] sm:h-8 sm:w-32 sm:text-xs";
  if (t === "known")
    return (
      <Badge variant="outline" className={`${base} border-success/40 text-success`}>
        <CheckCircle2 className="h-3 w-3 shrink-0" /> Recognized
      </Badge>
    );
  if (t === "review")
    return (
      <Badge variant="outline" className={`${base} border-warning/40 text-warning`}>
        <AlertTriangle className="h-3 w-3 shrink-0" /> Review
      </Badge>
    );
  if (t === "no_face")
    return (
      <Badge
        variant="outline"
        className={`${base} border-muted-foreground/30 text-muted-foreground`}
      >
        <XCircle className="h-3 w-3 shrink-0" /> No face
      </Badge>
    );
  if (t === "skipped")
    return (
      <Badge
        variant="outline"
        className={`${base} border-muted-foreground/30 text-muted-foreground`}
      >
        Skipped
      </Badge>
    );
  if (t === "error")
    return (
      <Badge variant="outline" className={`${base} border-destructive/40 text-destructive`}>
        <XCircle className="h-3 w-3 shrink-0" /> Error
      </Badge>
    );
  if (t === "processing")
    return (
      <Badge variant="outline" className={`${base} border-primary/30 text-primary`}>
        Processing
      </Badge>
    );
  return (
    <Badge variant="outline" className={`${base} border-muted-foreground/30 text-muted-foreground`}>
      <XCircle className="h-3 w-3 shrink-0" /> Unknown
    </Badge>
  );
}

function EventsList() {
  const { data: people = [] } = useQuery({ queryKey: ["people"], queryFn: api.people });
  const { data: cameras = [] } = useQuery({ queryKey: ["cameras"], queryFn: api.cameras });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [search, setSearch] = useState("");
  const [person, setPerson] = useState("all-people");
  const [camera, setCamera] = useState("all-cam");
  const [type, setType] = useState("all-type");
  const [minConfidence, setMinConfidence] = useState([0]);
  const [page, setPage] = useState(1);
  const serverFilters = {
    event_type: type === "all-type" ? "" : type,
    camera_id: camera === "all-cam" ? "" : camera,
    person_id: person === "all-people" ? "" : person,
  };
  const { data: eventsPage } = useQuery({
    queryKey: ["events", page, serverFilters],
    queryFn: () => api.events({ page, limit: 50, ...serverFilters }),
  });
  const events = useMemo(() => eventsPage?.items ?? [], [eventsPage?.items]);

  useEffect(() => setPage(1), [camera, person, type]);

  const filtered = useMemo(
    () =>
      events.filter((event) => {
        const haystack = `${event.personName} ${event.id} ${event.cameraName}`.toLowerCase();
        const matchesSearch = haystack.includes(search.toLowerCase());
        const matchesConfidence = event.confidence >= minConfidence[0] || event.confidence <= 0;
        return matchesSearch && matchesConfidence;
      }),
    [events, minConfidence, search],
  );

  const exportCsv = () => {
    const rows = [
      ["id", "person", "confidence", "camera", "type", "time"],
      ...filtered.map((event) => [
        event.id,
        event.personName ?? "",
        event.confidence,
        event.cameraName ?? "",
        event.type,
        event.time ?? "",
      ]),
    ];
    const csv = rows
      .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "iris-events.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Audit"
        title="Events"
        description="Every recognition attempt across all cameras."
        actions={
          <Button variant="outline" onClick={exportCsv}>
            <Download className="mr-2 h-4 w-4" /> Export CSV
          </Button>
        }
      />

      <Card className="border-border bg-card p-3 sm:p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
          <div className="relative lg:col-span-2">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="pl-9"
            />
          </div>
          <Button variant="outline" size="sm" className="w-full">
            <Calendar className="mr-2 h-4 w-4" /> All dates
          </Button>
          <Select value={person} onValueChange={setPerson}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-people">All people</SelectItem>
              {people.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.displayName || p.alias || p.name}
                </SelectItem>
              ))}
              <SelectItem value="unknown">Unknown only</SelectItem>
            </SelectContent>
          </Select>
          <Select value={camera} onValueChange={setCamera}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-cam">All cameras</SelectItem>
              {cameras.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Select value={type} onValueChange={setType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-type">All types</SelectItem>
              <SelectItem value="known">Known only</SelectItem>
              <SelectItem value="unknown">Unknown only</SelectItem>
              <SelectItem value="review">Needs review</SelectItem>
              <SelectItem value="no_face">No face</SelectItem>
              <SelectItem value="skipped">Skipped</SelectItem>
              <SelectItem value="error">Errors</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-input bg-background px-3 py-2">
            <span className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:w-auto">
              Min confidence
            </span>
            <Slider
              value={minConfidence}
              onValueChange={setMinConfidence}
              min={0}
              max={100}
              step={1}
              className="flex-1"
            />
            <span className="w-10 text-right font-mono text-xs text-primary">
              {minConfidence[0]}%
            </span>
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden border-border bg-card p-0">
        <div className="divide-y divide-border">
          {filtered.map((event: EventItem) => (
            <Link
              key={event.id}
              to="/events/$eventId"
              params={{ eventId: event.id }}
              className="flex gap-3 px-3 py-3 hover:bg-surface-elevated/40 sm:grid sm:grid-cols-12 sm:items-center sm:px-4"
            >
              <Snapshot
                size="sm"
                unknown={event.type === "unknown"}
                src={uploadUrl(event.face_crop_path || event.image_path || event.thumb_path)}
              />
              <div className="min-w-0 flex-1 sm:col-span-11 sm:grid sm:grid-cols-11 sm:items-center sm:gap-3">
                <div className="min-w-0 sm:col-span-3">
                  <div className="flex min-w-0 items-center justify-between gap-2 sm:block">
                    <span className="min-w-0 truncate text-sm font-medium sm:text-sm">
                      {event.personName}
                    </span>
                    <span className="shrink-0 sm:hidden">{statusBadge(event.type)}</span>
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground sm:text-[11px]">
                    {event.id}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground sm:col-span-6 sm:mt-0 sm:grid sm:grid-cols-3 sm:gap-3">
                  <span className="font-mono">
                    {event.confidence > 0 ? (
                      <span
                        className={
                          event.confidence >= (settings?.thresholds.auto_accept ?? 55)
                            ? "text-success"
                            : event.confidence >= (settings?.thresholds.match ?? 40)
                              ? "text-warning"
                              : "text-destructive"
                        }
                      >
                        {event.confidence.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </span>
                  <span className="flex min-w-0 items-center gap-1">
                    <Camera className="h-3 w-3 shrink-0" />
                    <span className="truncate">{event.cameraName}</span>
                  </span>
                  <span className="flex min-w-0 items-center gap-1 font-mono">
                    <Clock className="h-3 w-3 shrink-0 sm:hidden" />
                    <span className="truncate">{formatDateTime(event.time)}</span>
                  </span>
                </div>
                <div className="hidden justify-end sm:col-span-2 sm:flex">
                  {statusBadge(event.type)}
                </div>
              </div>
            </Link>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No events found.
            </div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted-foreground">
          <span>
            Page {eventsPage?.page ?? 1}/{eventsPage?.total_pages ?? 1} - {eventsPage?.total ?? 0}{" "}
            events
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={(eventsPage?.page ?? 1) <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={(eventsPage?.page ?? 1) >= (eventsPage?.total_pages ?? 1)}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </PageShell>
  );
}
