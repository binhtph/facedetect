import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Upload, Trash2, Power, Save, Loader2 } from "lucide-react";

import { PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Snapshot } from "@/components/snapshot";
import { api, uploadUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export const Route = createFileRoute("/people/$personId")({
  head: ({ params }) => ({ meta: [{ title: `${params.personId} - IRIS` }] }),
  component: PersonDetail,
});

function PersonDetail() {
  const { personId } = Route.useParams();
  const queryClient = useQueryClient();
  const {
    data: person,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["people", personId],
    queryFn: () => api.person(personId),
  });
  const [name, setName] = useState("");
  const [alias, setAlias] = useState("");
  const [notes, setNotes] = useState("");
  const [faceToDelete, setFaceToDelete] = useState<string | null>(null);

  useEffect(() => {
    if (!person) return;
    setName(person.name);
    setAlias(person.alias ?? "");
    setNotes(person.notes ?? "");
  }, [person]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["people"] });
    queryClient.invalidateQueries({ queryKey: ["people", personId] });
  };

  const savePerson = useMutation({
    mutationFn: () =>
      api.updatePerson(personId, {
        name: person?.name ?? personId,
        alias,
        notes,
        status: person?.status ?? "Active",
      }),
    onSuccess: () => {
      toast.success("Person saved");
      invalidate();
    },
    onError: (err) => toast.error(err.message),
  });

  const toggleStatus = useMutation({
    mutationFn: () =>
      api.updatePerson(personId, {
        name,
        alias,
        notes,
        status: person?.status === "Active" ? "Disabled" : "Active",
      }),
    onSuccess: invalidate,
    onError: (err) => toast.error(err.message),
  });

  const deletePerson = useMutation({
    mutationFn: () => api.deletePerson(personId),
    onSuccess: () => {
      toast.success("Person deleted");
      window.location.href = "/people";
    },
    onError: (err) => toast.error(err.message),
  });

  const uploadFace = useMutation({
    mutationFn: (file: File) => api.uploadFace(personId, file),
    onSuccess: () => {
      toast.success("Face indexed");
      invalidate();
    },
    onError: (err) => toast.error(err.message),
  });

  const deleteFace = useMutation({
    mutationFn: (faceId: string) => api.deleteFace(personId, faceId),
    onSuccess: () => {
      toast.success("Face deleted");
      setFaceToDelete(null);
      invalidate();
    },
    onError: (err) => toast.error(err.message),
  });

  if (isLoading)
    return (
      <PageShell>
        <div className="text-sm text-muted-foreground">Loading person...</div>
      </PageShell>
    );

  if (error || !person) {
    return (
      <PageShell>
        <Card className="border-border bg-card p-8 text-center">
          <h2 className="text-lg font-semibold">Person not found</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            No record for <code>{personId}</code>.
          </p>
          <Button asChild className="mt-4">
            <Link to="/people">Back to People</Link>
          </Button>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Button variant="ghost" size="sm" asChild className="w-fit">
          <Link to="/people">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Link>
        </Button>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="outline" onClick={() => toggleStatus.mutate()}>
            <Power className="mr-2 h-4 w-4" /> {person.status === "Active" ? "Disable" : "Enable"}
          </Button>
          <Button
            variant="outline"
            onClick={() => deletePerson.mutate()}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" /> Delete
          </Button>
          <Button
            onClick={() => savePerson.mutate()}
            disabled={!name.trim() || savePerson.isPending}
          >
            <Save className="mr-2 h-4 w-4" /> Save
          </Button>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 border-b border-border pb-5 sm:flex-row sm:gap-6 sm:pb-6">
        <Snapshot
          size="lg"
          label={person.displayName || person.name}
          src={uploadUrl(person.latest_image_path || person.faces?.[0]?.image_path)}
        />
        <div className="min-w-[240px] flex-1">
          <div className="font-mono text-[11px] uppercase tracking-widest text-primary">
            // {person.id}
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            {person.displayName || person.name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className={
                person.status === "Active"
                  ? "border-success/40 text-success"
                  : "border-muted-foreground/30 text-muted-foreground"
              }
            >
              {person.status}
            </Badge>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Last seen {formatDateTime(person.lastSeen, "Never")} - {person.totalRecognitions} total
            recognitions
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="border-border bg-card p-5 lg:col-span-2">
          <h3 className="text-sm font-semibold">Profile</h3>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label className="text-xs">Alias</Label>
              <Input
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                className="mt-1"
                placeholder="Tên hiển thị"
              />
            </div>
            <div>
              <Label className="text-xs">Person ID</Label>
              <Input value={person.id} className="mt-1" readOnly />
              <p className="mt-1 text-[10px] text-muted-foreground">
                Used as the local profile key. Avoid changing it after faces are indexed.
              </p>
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs">Notes</Label>
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1"
                placeholder="Optional notes..."
              />
            </div>
          </div>
        </Card>

        <Card className="border-border bg-card p-5">
          <h3 className="text-sm font-semibold">InsightFace</h3>
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Indexed faces</span>
              <span className="font-mono">{person.indexedFaces}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">External ID</span>
              <span className="font-mono text-xs">{person.id}</span>
            </div>
          </div>
        </Card>
      </div>

      <Card className="border-border bg-card p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold">Reference photos - {person.photos}</h3>
          <Button size="sm" asChild disabled={uploadFace.isPending}>
            <label>
              {uploadFace.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              {uploadFace.isPending ? "Indexing..." : "Upload photo"}
              <input
                className="sr-only"
                type="file"
                accept="image/png,image/jpeg"
                disabled={uploadFace.isPending}
                onChange={(e) => e.target.files?.[0] && uploadFace.mutate(e.target.files[0])}
              />
            </label>
          </Button>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
          {(person.faces ?? []).map((face) => (
            <div key={face.id} className="group relative w-fit">
              <Snapshot size="md" src={uploadUrl(face.image_path)} />
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="absolute right-1 top-1 h-7 w-7 border-destructive/30 bg-background/90 text-destructive opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus:opacity-100"
                onClick={() => setFaceToDelete(face.id)}
                aria-label="Delete reference face"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          {person.faces?.length === 0 && (
            <div className="text-sm text-muted-foreground">No reference photos yet.</div>
          )}
        </div>
      </Card>

      <AlertDialog
        open={faceToDelete !== null}
        onOpenChange={(open) => !open && setFaceToDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete reference face?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the face from InsightFace and deletes its local image if nothing else
              uses it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteFace.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={!faceToDelete || deleteFace.isPending}
              onClick={() => faceToDelete && deleteFace.mutate(faceToDelete)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Card className="overflow-hidden border-border bg-card p-0">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold">Recent recognitions</h3>
        </div>
        {(person.events ?? []).length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">No recognitions yet.</div>
        ) : (
          <div className="divide-y divide-border">
            {(person.events ?? []).map((event) => (
              <Link
                key={event.id}
                to="/events/$eventId"
                params={{ eventId: event.id }}
                className="flex items-center gap-3 px-5 py-3 hover:bg-surface-elevated/40"
              >
                <Snapshot
                  size="sm"
                  src={uploadUrl(event.face_crop_path || event.image_path || event.thumb_path)}
                />
                <div className="flex-1">
                  <div className="text-sm font-medium">{event.camera_name}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">
                    {formatDateTime(event.event_time)}
                  </div>
                </div>
                <span className="font-mono text-xs text-success">
                  {event.confidence.toFixed(1)}%
                </span>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </PageShell>
  );
}
