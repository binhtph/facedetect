import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Upload,
  ScanFace,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Camera,
  Clock,
  Timer,
  Percent,
  User,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FaceDetailsPanel, parseFaceDetails } from "@/components/face-details-panel";
import { Snapshot } from "@/components/snapshot";
import { api, uploadUrl, type EventItem } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/test")({
  head: () => ({ meta: [{ title: "Test Recognition - IRIS" }] }),
  component: TestPage,
});

type FaceBoundingBox = { Left?: number; Top?: number; Width?: number; Height?: number };

function parseJsonObject(value?: string): Record<string, unknown> | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function isBoundingBox(value: unknown): value is FaceBoundingBox {
  return Boolean(
    value &&
    typeof value === "object" &&
    typeof (value as FaceBoundingBox).Width === "number" &&
    typeof (value as FaceBoundingBox).Height === "number",
  );
}

function resultBoundingBox(result: EventItem): FaceBoundingBox | undefined {
  if (result.face_crop_path) return undefined;
  const fromEvent = parseJsonObject(result.face_bounding_box);
  if (isBoundingBox(fromEvent)) return fromEvent;
  const fromDetails = parseJsonObject(result.face_details_json)?.bounding_box;
  return isBoundingBox(fromDetails) ? fromDetails : undefined;
}

function TestPage() {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<EventItem | null>(null);
  const [otherFaces, setOtherFaces] = useState<EventItem[]>([]);
  // Test uploads stay silent by default so they never trigger automations; switch on to
  // check the whole chain (MQTT sensors, iris/event, Telegram) with a photo.
  const [sendToHome, setSendToHome] = useState(false);
  useEffect(() => {
    try {
      setSendToHome(window.localStorage.getItem("iris.test.notify") === "1");
    } catch {
      // storage unavailable: keep the default (off)
    }
  }, []);
  const toggleSendToHome = (value: boolean) => {
    setSendToHome(value);
    try {
      window.localStorage.setItem("iris.test.notify", value ? "1" : "0");
    } catch {
      // storage unavailable (private mode / sandboxed iframe): keep the in-memory value
    }
  };
  const [dragOver, setDragOver] = useState(false);

  const recognize = useMutation({
    mutationFn: (file: File) => api.recognize(file, "Test upload", "", sendToHome),
    onSuccess: (event) => {
      setResult(event);
      setOtherFaces(event.additional_events ?? []);
      const faceCount = 1 + (event.additional_events?.length ?? 0);
      toast.success(
        faceCount > 1 ? `Recognition complete: ${faceCount} faces` : "Recognition complete",
      );
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      queryClient.invalidateQueries({ queryKey: ["unknowns"] });
      queryClient.invalidateQueries({ queryKey: ["people"] });

      if (!event.face_details_json) {
        let attempts = 0;
        const timer = window.setInterval(async () => {
          attempts += 1;
          try {
            const fresh = await api.event(event.id);
            if (fresh.face_details_json) {
              setResult(fresh);
              window.clearInterval(timer);
            }
          } catch {
            window.clearInterval(timer);
          }
          if (attempts >= 8) window.clearInterval(timer);
        }, 1000);
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const handleFile = useCallback(
    (file: File) => {
      if (!file.type.startsWith("image/")) {
        toast.error("Only image files are supported");
        return;
      }
      setResult(null);
      setOtherFaces([]);
      setPreview(URL.createObjectURL(file));
      recognize.mutate(file);
    },
    [recognize],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const statusInfo = (type: string) => {
    if (type === "known")
      return { label: "Recognized", icon: CheckCircle2, cls: "text-success border-success/40" };
    if (type === "review")
      return { label: "Needs Review", icon: AlertTriangle, cls: "text-warning border-warning/40" };
    if (type === "no_face")
      return {
        label: "No Face",
        icon: XCircle,
        cls: "text-muted-foreground border-muted-foreground/30",
      };
    if (type === "skipped")
      return {
        label: "Skipped",
        icon: AlertTriangle,
        cls: "text-muted-foreground border-muted-foreground/30",
      };
    if (type === "error")
      return { label: "Error", icon: XCircle, cls: "text-destructive border-destructive/40" };
    if (type === "processing")
      return { label: "Processing", icon: ScanFace, cls: "text-primary border-primary/30" };
    return {
      label: "Unknown",
      icon: XCircle,
      cls: "text-muted-foreground border-muted-foreground/30",
    };
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Sandbox"
        title="Test Recognition"
        description="Upload an image to test recognition against the local InsightFace gallery."
        actions={
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-border px-3 py-2 text-sm">
            <Switch checked={sendToHome} onCheckedChange={toggleSendToHome} />
            <span>
              Send to Home Assistant &amp; Telegram
              <span className="block text-xs text-muted-foreground">
                {sendToHome
                  ? "Results update MQTT sensors and can trigger automations"
                  : "Off: test results stay inside IRIS"}
              </span>
            </span>
          </label>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Upload area */}
        <Card
          className={`relative border-2 border-dashed bg-card p-0 overflow-hidden transition-colors ${
            dragOver ? "border-primary bg-primary/5" : "border-border"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          {preview ? (
            <div className="relative aspect-video">
              <img
                src={preview}
                alt="Upload preview"
                className="h-full w-full object-contain bg-black/80"
              />
              {recognize.isPending && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                  <div className="flex flex-col items-center gap-3">
                    <ScanFace className="h-10 w-10 animate-pulse text-primary" />
                    <span className="font-mono text-xs text-primary">Analyzing...</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <label className="flex aspect-video cursor-pointer flex-col items-center justify-center gap-4 p-8">
              <div className="rounded-full bg-primary/10 p-4 ring-1 ring-primary/30">
                <Upload className="h-8 w-8 text-primary" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium">Drop an image here or click to upload</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">JPG, PNG supported</p>
              </div>
              <input
                className="sr-only"
                type="file"
                accept="image/png,image/jpeg"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
            </label>
          )}
        </Card>

        {/* Result panel */}
        <div className="space-y-4">
          {result ? (
            <>
              {(() => {
                const s = statusInfo(result.type);
                const faceDetails = parseFaceDetails(result.face_details_json);
                return (
                  <Card className={`border-border bg-card p-5`}>
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Result</h3>
                      <Badge variant="outline" className={s.cls}>
                        <s.icon className="mr-1 h-3 w-3" /> {s.label}
                      </Badge>
                    </div>

                    <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-start">
                      <Snapshot
                        size="lg"
                        label={result.personName || result.person_name}
                        confidence={result.confidence}
                        unknown={result.type === "unknown"}
                        src={uploadUrl(
                          result.face_crop_path || result.image_path || result.thumb_path,
                        )}
                        boundingBox={resultBoundingBox(result)}
                      />
                      <div className="min-w-0 flex-1 space-y-3">
                        <div className="flex items-center gap-2 text-sm">
                          <User className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium">
                            {result.personName || result.person_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Percent className="h-4 w-4 text-muted-foreground" />
                          {result.confidence > 0 ? (
                            <span
                              className={`font-mono ${result.confidence >= 95 ? "text-success" : result.confidence >= 90 ? "text-warning" : "text-destructive"}`}
                            >
                              {result.confidence.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-muted-foreground">No match</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Camera className="h-4 w-4 text-muted-foreground" />
                          <span className="text-muted-foreground">
                            {result.cameraName || result.camera_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Clock className="h-4 w-4 text-muted-foreground" />
                          <span className="font-mono text-xs text-muted-foreground">
                            {formatDateTime(result.time || result.event_time)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Timer className="h-4 w-4 text-muted-foreground" />
                          <span className="text-muted-foreground">Recognition time</span>
                          <span className="font-mono text-xs">
                            {result.processing_ms > 0
                              ? `${result.processing_ms.toFixed(0)} ms`
                              : "-"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 rounded-md border border-border bg-surface-elevated/50 p-3">
                      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Event ID
                      </div>
                      <div className="mt-0.5 font-mono text-xs">{result.id}</div>
                    </div>

                    <div className="mt-4 rounded-md border border-border bg-surface-elevated/50 p-3">
                      <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Face details
                      </div>
                      <FaceDetailsPanel details={faceDetails} />
                    </div>
                  </Card>
                );
              })()}

              {otherFaces.length > 0 && (
                <Card className="border-border bg-card p-5">
                  <h3 className="text-sm font-semibold">
                    Other faces in this image ({otherFaces.length})
                  </h3>
                  <ul className="mt-3 divide-y divide-border">
                    {otherFaces.map((face) => {
                      const info = statusInfo(face.type);
                      return (
                        <li key={face.id} className="flex items-center justify-between gap-3 py-2">
                          <Link
                            to="/events/$eventId"
                            params={{ eventId: face.id }}
                            className="truncate text-sm font-medium hover:underline"
                          >
                            {face.personName || face.person_name}
                          </Link>
                          <div className="flex shrink-0 items-center gap-2">
                            {face.confidence > 0 && (
                              <span className="font-mono text-xs text-muted-foreground">
                                {face.confidence.toFixed(1)}%
                              </span>
                            )}
                            <Badge variant="outline" className={info.cls}>
                              {info.label}
                            </Badge>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </Card>
              )}

              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setPreview(null);
                  setResult(null);
                  setOtherFaces([]);
                }}
              >
                <Upload className="mr-2 h-4 w-4" /> Test another image
              </Button>
            </>
          ) : (
            <Card className="border-border bg-card p-8">
              <div className="flex flex-col items-center gap-3 text-center">
                <ScanFace className="h-10 w-10 text-muted-foreground/30" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">No result yet</p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground/60">
                    Upload an image to start testing
                  </p>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageShell>
  );
}
