type FaceDetails = {
  confidence?: number;
  bounding_box?: { Left?: number; Top?: number; Width?: number; Height?: number };
  landmarks?: { X?: number; Y?: number }[];
  model?: string;
  provider?: string;
  inference_id?: string;
  age?: number | null;
  gender?: "male" | "female" | null;
};

interface FaceDetailsPanelProps {
  details?: FaceDetails;
}

export function parseFaceDetails(value?: string): FaceDetails | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function percent(value?: number, ratio = false) {
  return typeof value === "number" ? `${(ratio ? value * 100 : value).toFixed(1)}%` : "-";
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all text-right font-mono">{value}</span>
    </div>
  );
}

export function FaceDetailsPanel({ details }: FaceDetailsPanelProps) {
  if (!details || Object.keys(details).length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-4 text-xs text-muted-foreground">
        Analyzing face…
      </div>
    );
  }

  const box = details.bounding_box;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <DetailRow label="Detection confidence" value={percent(details.confidence)} />
        <DetailRow label="Model" value={details.model || "-"} />
        <DetailRow label="Provider" value={details.provider || "-"} />
        <DetailRow label="Inference ID" value={details.inference_id || "-"} />
        <DetailRow label="Estimated age" value={details.age == null ? "-" : String(details.age)} />
        <DetailRow label="Estimated gender" value={details.gender || "-"} />
      </div>
      <div className="space-y-2">
        <DetailRow label="Box left" value={percent(box?.Left, true)} />
        <DetailRow label="Box top" value={percent(box?.Top, true)} />
        <DetailRow label="Box width" value={percent(box?.Width, true)} />
        <DetailRow label="Box height" value={percent(box?.Height, true)} />
        <DetailRow label="Landmarks" value={String(details.landmarks?.length ?? 0)} />
      </div>
    </div>
  );
}
