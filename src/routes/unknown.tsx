import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { UserPlus, UserCheck, EyeOff, Trash2, Camera, Clock, Loader2 } from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Snapshot } from "@/components/snapshot";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, uploadUrl, type UnknownVisitor } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { personIdFromAlias, formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/unknown")({
  head: () => ({ meta: [{ title: "Unknown Visitors - IRIS" }] }),
  component: UnknownList,
});

function UnknownList() {
  const queryClient = useQueryClient();
  const { data: unknowns = [] } = useQuery({ queryKey: ["unknowns"], queryFn: api.unknowns });
  const { data: people = [] } = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [selected, setSelected] = useState<UnknownVisitor | null>(null);
  const [personId, setPersonId] = useState("");
  const [newName, setNewName] = useState("");
  const [newAlias, setNewAlias] = useState("");
  const [newPersonIdAttention, setNewPersonIdAttention] = useState(false);
  const newPersonIdRef = useRef<HTMLInputElement>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["unknowns"] });
    queryClient.invalidateQueries({ queryKey: ["people"] });
    queryClient.invalidateQueries({ queryKey: ["events"] });
    queryClient.invalidateQueries({ queryKey: ["summary"] });
  };

  const highlightNewPersonId = () => {
    newPersonIdRef.current?.focus();
    newPersonIdRef.current?.select();
    setNewPersonIdAttention(false);
    window.requestAnimationFrame(() => setNewPersonIdAttention(true));
    window.setTimeout(() => setNewPersonIdAttention(false), 2800);
  };

  const assign = useMutation({
    mutationFn: async () => {
      if (!selected || !personId) throw new Error("Choose a person first.");
      return api.assignUnknown(selected.id, personId);
    },
    onSuccess: () => {
      toast.success("Unknown assigned and indexed");
      setSelected(null);
      invalidate();
    },
    onError: (err) => toast.error(err.message),
  });

  const createAndAssign = useMutation({
    mutationFn: async () => {
      if (!selected || !newAlias.trim() || !newName.trim())
        throw new Error("Alias and Person ID are required.");
      const person = await api.createPerson({
        name: newName,
        alias: newAlias,
        notes: "Created from unknown visitor",
      });
      return api.assignUnknown(selected.id, person.id);
    },
    onSuccess: () => {
      toast.success("Person created and face indexed");
      setSelected(null);
      setNewName("");
      setNewAlias("");
      invalidate();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "person_id_exists") highlightNewPersonId();
      toast.error(err.message);
    },
  });

  const remove = useMutation({
    mutationFn: (unknownId: string) => api.deleteUnknown(unknownId),
    onSuccess: () => {
      toast.success("Unknown ignored");
      setSelected(null);
      invalidate();
    },
    onError: (err) => toast.error(err.message),
  });

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Review queue"
        title="Unknown visitors"
        description="Faces detected but not matched. Assign them to existing people or create new records."
        actions={<span className="chip">{unknowns.length} pending</span>}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
        {unknowns.map((unknown) => (
          <Card key={unknown.id} className="overflow-hidden border-border bg-card p-0">
            <div className="relative aspect-square bg-black/40">
              <div className="absolute inset-0 flex items-center justify-center">
                <Snapshot size="lg" unknown src={uploadUrl(unknown.image_path)} />
              </div>
              <Badge
                variant="outline"
                className="absolute right-2 top-2 border-warning/40 bg-background/80 text-warning backdrop-blur"
              >
                x{unknown.detections}
              </Badge>
            </div>
            <div className="space-y-1 border-t border-border p-3">
              <div className="flex items-center gap-1.5 text-xs">
                <Camera className="h-3 w-3 text-muted-foreground" />
                <span className="truncate font-medium">{unknown.cameraName}</span>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                <Clock className="h-3 w-3" /> {formatDateTime(unknown.time)}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="mt-2 w-full"
                onClick={() => setSelected(unknown)}
              >
                Review
              </Button>
            </div>
          </Card>
        ))}
        {unknowns.length === 0 && (
          <div className="col-span-full rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            No unknown visitors pending.
          </div>
        )}
      </div>

      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Unknown visitor - {selected?.id}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="grid-bg relative aspect-square overflow-hidden rounded-md border border-border bg-black/40">
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Snapshot size="lg" unknown src={uploadUrl(selected.image_path)} />
                  </div>
                </div>
                <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                  <div>
                    <Camera className="mr-1 inline h-3 w-3" /> {selected.cameraName}
                  </div>
                  <div>
                    <Clock className="mr-1 inline h-3 w-3" /> {formatDateTime(selected.time)}
                  </div>
                  <div>
                    {selected.detections} detection{selected.detections > 1 ? "s" : ""}
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <Label className="text-xs">Assign to existing person</Label>
                  <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                    <Select value={personId} onValueChange={setPersonId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Choose..." />
                      </SelectTrigger>
                      <SelectContent>
                        {people.map((person) => (
                          <SelectItem key={person.id} value={person.id}>
                            {person.displayName || person.alias || person.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      onClick={() => assign.mutate()}
                      disabled={!personId || assign.isPending}
                    >
                      {assign.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <UserCheck className="mr-2 h-4 w-4" />
                      )}
                      {assign.isPending ? "Indexing..." : "Assign"}
                    </Button>
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Image is attached and InsightFace faces are re-indexed.
                  </p>
                </div>

                <div className="border-t border-border pt-4">
                  <Label className="text-xs">Or create new person</Label>
                  <Input
                    value={newAlias}
                    onChange={(e) => {
                      const value = e.target.value;
                      setNewAlias(value);
                      setNewName(personIdFromAlias(value));
                    }}
                    className="mt-1"
                    placeholder="Alias..."
                  />
                  <Input
                    ref={newPersonIdRef}
                    value={newName}
                    onChange={(e) => {
                      setNewName(personIdFromAlias(e.target.value));
                    }}
                    className={`mt-2 ${newPersonIdAttention ? "insightface-id-attention" : ""}`}
                    placeholder="Person ID..."
                  />
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Person ID is the local profile key. Use only unaccented letters, numbers, `_`,
                    `.`, `-`.
                  </p>
                  <Button
                    className="mt-2 w-full"
                    onClick={() => createAndAssign.mutate()}
                    disabled={!newAlias.trim() || !newName.trim() || createAndAssign.isPending}
                  >
                    {createAndAssign.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <UserPlus className="mr-2 h-4 w-4" />
                    )}
                    {createAndAssign.isPending ? "Indexing..." : "Create person"}
                  </Button>
                </div>

                <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => remove.mutate(selected.id)}
                  >
                    <EyeOff className="mr-2 h-4 w-4" /> Ignore
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1 text-destructive hover:text-destructive"
                    onClick={() => remove.mutate(selected.id)}
                  >
                    <Trash2 className="mr-2 h-4 w-4" /> Delete
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
