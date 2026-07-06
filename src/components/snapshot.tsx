import { useEffect, useMemo, useRef, useState } from "react";
import { ScanFace, type LucideIcon } from "lucide-react";

interface SnapshotProps {
  label?: string;
  confidence?: number;
  size?: "sm" | "md" | "lg" | "full";
  icon?: LucideIcon;
  unknown?: boolean;
  src?: string;
  boundingBox?: { Left?: number; Top?: number; Width?: number; Height?: number };
  imageFit?: "contain" | "cover";
  labelMode?: "frame" | "box";
}

const sizes = {
  sm: "h-12 w-12 text-[10px]",
  md: "h-20 w-20 text-xs",
  lg: "h-40 w-40 text-sm",
  full: "h-full w-full text-sm",
};

/** Stylized snapshot placeholder — replace with real <img> when backend wires snapshots. */
export function Snapshot({
  label,
  confidence,
  size = "md",
  icon: Icon = ScanFace,
  unknown,
  src,
  boundingBox,
  imageFit = boundingBox ? "contain" : "cover",
  labelMode = "frame",
}: SnapshotProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const update = () =>
      setContainerSize({ width: element.clientWidth, height: element.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(() => {
    if (!containerSize.width || !containerSize.height || !imageSize.width || !imageSize.height) {
      return undefined;
    }
    const containerRatio = containerSize.width / containerSize.height;
    const imageRatio = imageSize.width / imageSize.height;
    const base =
      imageFit === "cover"
        ? imageRatio > containerRatio
          ? {
              width: containerSize.height * imageRatio,
              height: containerSize.height,
              left: (containerSize.width - containerSize.height * imageRatio) / 2,
              top: 0,
            }
          : {
              width: containerSize.width,
              height: containerSize.width / imageRatio,
              left: 0,
              top: (containerSize.height - containerSize.width / imageRatio) / 2,
            }
        : imageRatio > containerRatio
          ? {
              width: containerSize.width,
              height: containerSize.width / imageRatio,
              left: 0,
              top: (containerSize.height - containerSize.width / imageRatio) / 2,
            }
          : {
              width: containerSize.height * imageRatio,
              height: containerSize.height,
              left: (containerSize.width - containerSize.height * imageRatio) / 2,
              top: 0,
            };
    if (imageFit !== "cover" || !boundingBox?.Width || !boundingBox.Height) return base;

    const faceCenterX = (boundingBox.Left ?? 0) + boundingBox.Width / 2;
    const faceCenterY = (boundingBox.Top ?? 0) + boundingBox.Height / 2;
    const minLeft = Math.min(0, containerSize.width - base.width);
    const minTop = Math.min(0, containerSize.height - base.height);
    return {
      ...base,
      left: Math.min(0, Math.max(minLeft, containerSize.width / 2 - faceCenterX * base.width)),
      top: Math.min(0, Math.max(minTop, containerSize.height / 2 - faceCenterY * base.height)),
    };
  }, [boundingBox, containerSize, imageFit, imageSize]);

  const box = useMemo(() => {
    if (!boundingBox?.Width || !boundingBox.Height || !layout) {
      return undefined;
    }
    return {
      left: layout.left + (boundingBox.Left ?? 0) * layout.width,
      top: layout.top + (boundingBox.Top ?? 0) * layout.height,
      width: boundingBox.Width * layout.width,
      height: boundingBox.Height * layout.height,
    };
  }, [boundingBox, layout]);

  return (
    <div
      className={`relative ${sizes[size]} shrink-0 overflow-hidden rounded-md border ${
        unknown ? "border-warning/40 bg-warning/5" : "border-primary/30 bg-primary/5"
      }`}
      ref={containerRef}
    >
      {src ? (
        <img
          src={src}
          alt={label ?? "Face snapshot"}
          className="absolute max-w-none"
          style={
            layout
              ? {
                  left: layout.left,
                  top: layout.top,
                  width: layout.width,
                  height: layout.height,
                }
              : { inset: 0, width: "100%", height: "100%" }
          }
          onLoad={(event) =>
            setImageSize({
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            })
          }
        />
      ) : (
        <>
          <div className="grid-bg absolute inset-0 opacity-50" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Icon className={`${unknown ? "text-warning/60" : "text-primary/60"} h-1/3 w-1/3`} />
          </div>
        </>
      )}
      {box && (
        <>
          <span
            className={`absolute ${unknown ? "text-warning" : "text-primary"}`}
            style={{
              left: box.left,
              top: box.top,
              width: box.width,
              height: box.height,
            }}
          >
            <span className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-current" />
            <span className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-current" />
            <span className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-current" />
            <span className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-current" />
          </span>
          {label && size !== "sm" && labelMode === "box" && (
            <div
              className="absolute max-w-[calc(100%-0.5rem)] whitespace-nowrap rounded-md bg-background/75 px-2 py-0.5 text-center font-mono backdrop-blur"
              style={{
                left: Math.min(
                  Math.max(4, box.left + box.width / 2 - Math.max(box.width, 96) / 2),
                  Math.max(4, containerSize.width - Math.max(box.width, 96) - 4),
                ),
                top: Math.min(containerSize.height - 24, box.top + box.height),
                minWidth: Math.max(box.width, 96),
              }}
            >
              {label}
            </div>
          )}
        </>
      )}
      {/* corner brackets */}
      <span
        className={`absolute left-1 top-1 h-2 w-2 border-l border-t ${unknown ? "border-warning" : "border-primary"}`}
      />
      <span
        className={`absolute right-1 top-1 h-2 w-2 border-r border-t ${unknown ? "border-warning" : "border-primary"}`}
      />
      <span
        className={`absolute bottom-1 left-1 h-2 w-2 border-b border-l ${unknown ? "border-warning" : "border-primary"}`}
      />
      <span
        className={`absolute bottom-1 right-1 h-2 w-2 border-b border-r ${unknown ? "border-warning" : "border-primary"}`}
      />
      {label && size !== "sm" && labelMode === "frame" && (
        <div className="absolute bottom-0 left-0 right-0 truncate bg-background/70 px-1.5 py-0.5 text-center font-mono backdrop-blur">
          {label}
        </div>
      )}
      {confidence != null && size !== "sm" && (
        <div className="absolute top-1 right-1 rounded-sm bg-background/80 px-1 py-0.5 text-[9px] font-mono text-primary">
          {confidence.toFixed(1)}%
        </div>
      )}
    </div>
  );
}
