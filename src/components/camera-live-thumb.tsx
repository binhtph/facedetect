import { useEffect, useState } from "react";
import { Camera as CameraIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cameraSnapshotUrl, type Camera } from "@/lib/api";

interface CameraLiveThumbProps {
  camera: Camera;
  showStatus?: boolean;
  iconClassName?: string;
}

export function CameraLiveThumb({
  camera,
  showStatus = false,
  iconClassName = "h-10 w-10 text-primary/40",
}: CameraLiveThumbProps) {
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(() => Date.now());
  const src = camera.status === "online" ? cameraSnapshotUrl(camera.id, tick) : undefined;

  useEffect(() => {
    if (camera.status !== "online") return;
    const timer = window.setInterval(() => setTick(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, [camera.id, camera.status]);

  useEffect(() => {
    setFailed(false);
  }, [camera.id, camera.status, tick]);

  return (
    <div className="grid-bg relative aspect-video bg-black/60">
      {src && !failed ? (
        <img
          src={src}
          alt={camera.name}
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <CameraIcon
            className={
              camera.status === "online" ? iconClassName : "h-10 w-10 text-muted-foreground/30"
            }
          />
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/35 to-transparent" />
      {showStatus &&
        (camera.status === "online" ? (
          <Badge
            variant="outline"
            className="absolute left-2 top-2 border-success/40 bg-background/80 text-success backdrop-blur"
          >
            <span className="mr-1 h-1.5 w-1.5 animate-pulse rounded-full bg-success" /> Live
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="absolute left-2 top-2 border-destructive/40 bg-background/80 text-destructive backdrop-blur"
          >
            Offline
          </Badge>
        ))}
    </div>
  );
}
