import { createFileRoute, Link } from "@tanstack/react-router";
import { appPath, clientBasepath } from "@/lib/basepath";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Save, Trash2, Copy } from "lucide-react";

import { CameraLiveThumb } from "@/components/camera-live-thumb";
import { PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Snapshot } from "@/components/snapshot";
import { API_BASE, api, uploadUrl } from "@/lib/api";
import { copyText } from "@/lib/clipboard";

export const Route = createFileRoute("/cameras/$cameraId")({
  head: ({ params }) => ({ meta: [{ title: `${params.cameraId} - IRIS` }] }),
  component: CameraDetail,
});

function CameraDetail() {
  const { cameraId } = Route.useParams();
  const queryClient = useQueryClient();
  const {
    data: camera,
    isLoading,
    error,
  } = useQuery({ queryKey: ["cameras", cameraId], queryFn: () => api.camera(cameraId) });
  const { data: eventsPage } = useQuery({
    queryKey: ["events", "camera", cameraId],
    queryFn: () => api.events({ camera_id: cameraId, limit: 12 }),
  });
  const [name, setName] = useState("");
  const [stillUrl, setStillUrl] = useState("");
  const [cooldown, setCooldown] = useState([60]);

  useEffect(() => {
    if (!camera) return;
    setName(camera.name);
    setStillUrl(camera.still_url || camera.stream_url || "");
    setCooldown([camera.cooldown]);
  }, [camera]);

  const save = useMutation({
    mutationFn: () =>
      api.updateCamera(cameraId, {
        name,
        status: camera?.status ?? "online",
        still_url: stillUrl,
        face_detection: true,
        motion: true,
        cooldown: cooldown[0],
        min_face: camera?.min_face ?? 8,
        min_confidence: camera?.min_confidence ?? 80,
      }),
    onSuccess: () => {
      toast.success("Camera saved");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["cameras", cameraId] });
    },
    onError: (err) => toast.error(err.message),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteCamera(cameraId),
    onSuccess: () => {
      toast.success("Camera removed");
      window.location.href = appPath("/cameras");
    },
    onError: (err) => toast.error(err.message),
  });

  const cameraEvents = useMemo(() => eventsPage?.items ?? [], [eventsPage?.items]);

  if (isLoading)
    return (
      <PageShell>
        <div className="text-sm text-muted-foreground">Loading camera...</div>
      </PageShell>
    );
  if (error || !camera) {
    return (
      <PageShell>
        <Card className="border-border bg-card p-8 text-center">
          <h2 className="text-lg font-semibold">Camera not found</h2>
          <Button asChild className="mt-4">
            <Link to="/cameras">Back to Cameras</Link>
          </Button>
        </Card>
      </PageShell>
    );
  }

  // Inside the Home Assistant sidebar the page URL carries a session-bound ingress token
  // that automations cannot use, so show the add-on's direct port instead.
  const underIngress = clientBasepath() !== "";
  const triggerUrl = underIngress
    ? `http://${window.location.hostname}:8080${camera.trigger_path}`
    : `${API_BASE}${camera.trigger_path}`;

  return (
    <PageShell>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Button variant="ghost" size="sm" asChild className="w-fit">
          <Link to="/cameras">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Link>
        </Button>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            variant="outline"
            onClick={() => remove.mutate()}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" /> Remove
          </Button>
          <Button onClick={() => save.mutate()}>
            <Save className="mr-2 h-4 w-4" /> Save
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between sm:gap-6 sm:pb-6">
        <div className="min-w-0">
          <div className="font-mono text-[11px] uppercase tracking-widest text-primary">
            // {camera.id}
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{camera.name}</h1>
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{triggerUrl}</p>
        </div>
        <Badge
          variant="outline"
          className={
            camera.status === "online"
              ? "border-success/40 text-success"
              : "border-destructive/40 text-destructive"
          }
        >
          {camera.status === "online" ? "Online" : "Offline"}
        </Badge>
      </div>

      <Card className="overflow-hidden border-border bg-card p-0">
        <CameraLiveThumb camera={camera} iconClassName="h-12 w-12 text-primary/30" />
      </Card>

      <Card className="border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Image history</h3>
          <span className="font-mono text-xs text-muted-foreground">
            {cameraEvents.length} recent
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-6">
          {cameraEvents.map((event) => (
            <Link
              key={event.id}
              to="/events/$eventId"
              params={{ eventId: event.id }}
              className="block"
            >
              <div className="space-y-2">
                <Snapshot
                  size="md"
                  src={uploadUrl(event.face_crop_path || event.image_path || event.thumb_path)}
                  confidence={event.confidence}
                  unknown={event.type === "unknown"}
                />
                <div className="truncate text-xs text-muted-foreground">{event.personName}</div>
              </div>
            </Link>
          ))}
          {cameraEvents.length === 0 && (
            <div className="col-span-full text-sm text-muted-foreground">
              No trigger images yet.
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Cooldown</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Prevent duplicate InsightFace calls within this window after a trigger.
          </p>
          <div className="mt-4">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Cooldown</span>
              <span className="font-mono text-primary">{cooldown[0]}s</span>
            </div>
            <Slider
              value={cooldown}
              onValueChange={setCooldown}
              min={10}
              max={300}
              step={10}
              className="mt-2"
            />
          </div>
        </Card>

        <Card className="border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Camera profile</h3>
          <div className="mt-5 grid grid-cols-1 gap-5">
            <div>
              <Label className="text-xs">Name</Label>
              <Input className="mt-1" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Still image URL</Label>
              <Input
                className="mt-1 font-mono"
                value={stillUrl}
                onChange={(e) => setStillUrl(e.target.value)}
                placeholder="http://camera/snapshot.jpg"
              />
            </div>
            <div>
              <Label className="text-xs">Trigger URL</Label>
              <div className="mt-1 flex gap-2">
                <Input className="min-w-0 font-mono" value={triggerUrl} readOnly />
                <Button
                  type="button"
                  variant="outline"
                  onClick={async () => {
                    await copyText(triggerUrl);
                    toast.success("Trigger URL copied");
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              {underIngress && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Direct add-on port (needs port 8080 enabled). From Home Assistant automations the
                  simplest option is the MQTT button “Trigger {camera.name}”.
                </p>
              )}
            </div>
          </div>
        </Card>
      </div>
    </PageShell>
  );
}
