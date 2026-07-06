import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ArrowLeft, Upload, CheckCircle2, Cloud, User } from "lucide-react";
import { toast } from "sonner";

import { PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Snapshot } from "@/components/snapshot";
import { api, type Person } from "@/lib/api";
import { personIdFromAlias } from "@/lib/utils";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/people/new")({
  head: () => ({ meta: [{ title: "Add person — IRIS" }] }),
  component: AddPerson,
});

const steps = [
  { n: 1, label: "Profile", icon: User },
  { n: 2, label: "Upload photos", icon: Upload },
  { n: 3, label: "Index in InsightFace", icon: Cloud },
  { n: 4, label: "Done", icon: CheckCircle2 },
];

function AddPerson() {
  const [step, setStep] = useState(1);
  const [createdPerson, setCreatedPerson] = useState<Person | null>(null);
  const [name, setName] = useState("");
  const [alias, setAlias] = useState("");
  const [personIdAttention, setPersonIdAttention] = useState(false);
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const personIdRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const highlightPersonId = () => {
    personIdRef.current?.focus();
    personIdRef.current?.select();
    setPersonIdAttention(false);
    window.requestAnimationFrame(() => setPersonIdAttention(true));
    window.setTimeout(() => setPersonIdAttention(false), 2800);
  };

  const createPerson = useMutation({
    mutationFn: () => api.createPerson({ name, alias, notes }),
    onSuccess: (person) => {
      setCreatedPerson(person);
      queryClient.invalidateQueries({ queryKey: ["people"] });
      setStep(2);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "person_id_exists") highlightPersonId();
      toast.error(error.message);
    },
  });

  const uploadFaces = useMutation({
    mutationFn: async () => {
      if (!createdPerson) throw new Error("Create the person profile first.");
      for (const photo of photos) {
        await api.uploadFace(createdPerson.id, photo);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["people"] });
      toast.success("Faces indexed in InsightFace");
      setStep(4);
    },
    onError: (error) => toast.error(error.message),
  });

  const onFiles = (files: FileList | null) => {
    if (!files) return;
    setPhotos((current) => [...current, ...Array.from(files)].slice(0, 10));
  };

  return (
    <PageShell>
      <Button variant="ghost" size="sm" asChild className="-ml-2 w-fit">
        <Link to="/people">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to people
        </Link>
      </Button>

      <div className="border-b border-border pb-5 sm:pb-6">
        <div className="font-mono text-[11px] uppercase tracking-widest text-primary">
          // Enroll
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Add new person</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload 5–10 clear face photos. We index them with InsightFace and store the resulting Face
          IDs.
        </p>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {steps.map((s, i) => (
          <div key={s.n} className="flex flex-1 items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-mono ${
                step >= s.n
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground"
              }`}
            >
              {step > s.n ? <CheckCircle2 className="h-4 w-4" /> : s.n}
            </div>
            <span
              className={`hidden whitespace-nowrap text-xs sm:inline ${step >= s.n ? "font-semibold" : "text-muted-foreground"}`}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <div className={`h-px flex-1 ${step > s.n ? "bg-primary" : "bg-border"}`} />
            )}
          </div>
        ))}
      </div>

      <Card className="border-border bg-card p-4 sm:p-6">
        {step === 1 && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label className="text-xs">Alias</Label>
              <Input
                value={alias}
                onChange={(e) => {
                  const value = e.target.value;
                  setAlias(value);
                  setName(personIdFromAlias(value));
                }}
                className="mt-1"
                placeholder="Ví dụ: Việt Anh"
              />
            </div>
            <div>
              <Label className="text-xs">Person ID</Label>
              <Input
                ref={personIdRef}
                value={name}
                onChange={(e) => {
                  setName(personIdFromAlias(e.target.value));
                }}
                className={`mt-1 ${personIdAttention ? "insightface-id-attention" : ""}`}
                placeholder="viet_anh"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">
                Used as the local profile key. Avoid changing it; use only unaccented letters,
                numbers, `_`, `.`, `-`.
              </p>
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs">Notes (optional)</Label>
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1"
                placeholder="e.g. Sister visiting from Hanoi"
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
              {photos.map((p) => (
                <Snapshot
                  key={`${p.name}-${p.lastModified}`}
                  size="md"
                  src={URL.createObjectURL(p)}
                />
              ))}
              <label className="grid-bg flex h-20 w-20 cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-border text-xs text-muted-foreground hover:border-primary/50 hover:text-primary">
                <Upload className="mb-1 h-4 w-4" />
                Add
                <input
                  className="sr-only"
                  type="file"
                  accept="image/png,image/jpeg"
                  multiple
                  onChange={(e) => onFiles(e.target.files)}
                />
              </label>
            </div>
            <p className="mt-4 font-mono text-xs text-muted-foreground">
              {photos.length} / 10 photos · recommended 5+ varied angles
            </p>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-3 py-4 text-center">
            <Cloud className="mx-auto h-10 w-10 text-primary" />
            <div className="text-sm font-semibold">Indexing in InsightFace…</div>
            <div className="font-mono text-xs text-muted-foreground">
              {createdPerson?.displayName ?? createdPerson?.name ?? "Person"} - {photos.length}{" "}
              faces
            </div>
            <div className="mx-auto mt-4 max-w-md space-y-1 text-left">
              {photos.map((p, i) => (
                <div
                  key={`${p.name}-${p.lastModified}`}
                  className="flex items-center justify-between rounded-md border border-border bg-surface-elevated px-3 py-2 text-xs"
                >
                  <span className="font-mono text-muted-foreground">photo_{i + 1}.jpg</span>
                  <span className="flex items-center gap-1 text-muted-foreground">ready</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="py-6 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-success/10 ring-1 ring-success/40">
              <CheckCircle2 className="h-7 w-7 text-success" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">Person enrolled</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {photos.length} faces indexed in InsightFace.
            </p>
            <div className="mt-4 flex justify-center gap-2">
              <Button variant="outline" asChild>
                <Link to="/people">Back to list</Link>
              </Button>
              <Button
                onClick={() => {
                  setStep(1);
                  setPhotos([]);
                  setCreatedPerson(null);
                  setName("");
                  setAlias("");
                  setNotes("");
                }}
              >
                Add another
              </Button>
            </div>
          </div>
        )}

        {step < 4 && (
          <div className="mt-6 flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
            <Button
              variant="outline"
              disabled={step === 1 || createPerson.isPending || uploadFaces.isPending}
              onClick={() => setStep((s) => s - 1)}
            >
              Back
            </Button>
            <Button
              onClick={() => {
                if (step === 1) createPerson.mutate();
                else if (step === 2) setStep(3);
                else uploadFaces.mutate();
              }}
              disabled={
                (step === 1 && (!alias.trim() || !name.trim())) ||
                (step === 2 && photos.length < 1) ||
                createPerson.isPending ||
                uploadFaces.isPending
              }
            >
              {step === 3 ? (uploadFaces.isPending ? "Indexing..." : "Index faces") : "Continue"}
            </Button>
          </div>
        )}
      </Card>
    </PageShell>
  );
}
