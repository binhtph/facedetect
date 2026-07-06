import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Plus, Clock, Wifi, WifiOff, Copy } from "lucide-react";

import { CameraLiveThumb } from "@/components/camera-live-thumb";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { API_BASE, api } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/cameras/")({
  head: () => ({ meta: [{ title: "Cameras - IRIS" }] }),
  component: CamerasList,
});

function CamerasList() {
  const queryClient = useQueryClient();
  const { data: cameras = [] } = useQuery({ queryKey: ["cameras"], queryFn: api.cameras });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [stillUrl, setStillUrl] = useState("");
  const [cooldown, setCooldown] = useState([60]);
  const createCamera = useMutation({
    mutationFn: () =>
      api.createCamera({
        name,
        still_url: stillUrl,
        status: "online",
        face_detection: true,
        motion: true,
        cooldown: cooldown[0],
        min_face: 8,
        min_confidence: 80,
      }),
    onSuccess: () => {
      toast.success("Camera created");
      setOpen(false);
      setName("");
      setStillUrl("");
      setCooldown([60]);
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (err) => toast.error(err.message),
  });

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Devices"
        title="Cameras"
        description="Trigger webhooks fetch still images and run InsightFace automatically."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" /> Add camera
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add camera</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4">
                <div>
                  <Label className="text-xs">Name</Label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="mt-1"
                    placeholder="Front Door"
                  />
                </div>
                <div>
                  <Label className="text-xs">Still image URL</Label>
                  <Input
                    value={stillUrl}
                    onChange={(e) => setStillUrl(e.target.value)}
                    className="mt-1 font-mono"
                    placeholder="http://camera/snapshot.jpg"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs">
                    <Label className="text-xs">Cooldown</Label>
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
                <Button
                  onClick={() => createCamera.mutate()}
                  disabled={!name.trim() || !stillUrl.trim() || createCamera.isPending}
                >
                  Create camera
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cameras.map((camera) => (
          <Card
            key={camera.id}
            className="overflow-hidden border-border bg-card p-0 transition hover:border-primary/40"
          >
            <Link to="/cameras/$cameraId" params={{ cameraId: camera.id }} className="block">
              <CameraLiveThumb camera={camera} showStatus />
            </Link>
            <div className="border-t border-border p-4">
              <Link
                to="/cameras/$cameraId"
                params={{ cameraId: camera.id }}
                className="font-semibold hover:text-primary"
              >
                {camera.name}
              </Link>
              <div className="mt-2 flex gap-2">
                <Input
                  className="h-8 min-w-0 flex-1 font-mono text-[11px]"
                  value={`${API_BASE}${camera.trigger_path}`}
                  readOnly
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={async () => {
                    await copyText(`${API_BASE}${camera.trigger_path}`);
                    toast.success("Trigger URL copied");
                  }}
                  title="Copy trigger URL"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <div className="mt-3 flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />{" "}
                  {formatDateTime(camera.last_detection, "No detections")}
                </span>
                <span className="flex items-center gap-1">
                  {camera.status === "online" ? (
                    <Wifi className="h-3 w-3 text-success" />
                  ) : (
                    <WifiOff className="h-3 w-3 text-destructive" />
                  )}
                  {camera.cooldown}s cooldown
                </span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </PageShell>
  );
}
