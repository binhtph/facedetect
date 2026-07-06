import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Save,
  Cpu,
  Bell,
  Plug,
  RadioTower,
  SatelliteDish,
  Send,
  HardDrive,
  Trash2,
  ScrollText,
  Loader2,
  Download,
  CheckCircle2,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings - IRIS" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const { data: models = [] } = useQuery({
    queryKey: ["insightface-models"],
    queryFn: api.insightFaceModels,
    refetchInterval: (query) =>
      query.state.data?.some((model) => model.status === "downloading") ? 500 : false,
  });
  const { data: rebuildStatus } = useQuery({
    queryKey: ["insightface-rebuild"],
    queryFn: api.insightFaceRebuild,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 500 : false),
  });
  const { data: mqttSettings } = useQuery({ queryKey: ["mqtt-settings"], queryFn: api.mqtt });
  const { data: telegramSettings } = useQuery({
    queryKey: ["telegram-settings"],
    queryFn: api.telegram,
  });
  const { data: storageSettings } = useQuery({
    queryKey: ["storage-settings"],
    queryFn: api.storage,
  });
  const { data: logsSettings } = useQuery({
    queryKey: ["logs-settings"],
    queryFn: api.logsSettings,
  });
  const [modelName, setModelName] = useState("buffalo_s");
  const [provider, setProvider] = useState("CPUExecutionProvider");
  const [detSize, setDetSize] = useState(640);
  const [ageGenderEnabled, setAgeGenderEnabled] = useState(false);
  const [match, setMatch] = useState([40]);
  const [accept, setAccept] = useState([55]);
  const [mqttHost, setMqttHost] = useState("");
  const [mqttPort, setMqttPort] = useState(1883);
  const [mqttUsername, setMqttUsername] = useState("");
  const [mqttPassword, setMqttPassword] = useState("");
  const [mqttDiscoveryPrefix, setMqttDiscoveryPrefix] = useState("homeassistant");
  const [mqttBaseTopic, setMqttBaseTopic] = useState("iris");
  const [mqttDeviceId, setMqttDeviceId] = useState("iris_face_recognition");
  const [mqttDeviceName, setMqttDeviceName] = useState("IRIS Face Recognition");
  const [mqttUseTls, setMqttUseTls] = useState(false);
  const [tgBotToken, setTgBotToken] = useState("");
  const [tgChatId, setTgChatId] = useState("");
  const [maxStorageMb, setMaxStorageMb] = useState(2048);
  const [logMaxRows, setLogMaxRows] = useState(500);
  const [trackedRebuild, setTrackedRebuild] = useState(false);
  const [pendingModelSave, setPendingModelSave] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setModelName(settings.model_name);
    setProvider(settings.provider);
    setDetSize(settings.det_size);
    setAgeGenderEnabled(settings.age_gender_enabled ?? false);
    setMatch([settings.thresholds.match]);
    setAccept([settings.thresholds.auto_accept]);
    setMaxStorageMb(settings.storage?.max_storage_mb ?? 2048);
  }, [settings]);

  useEffect(() => {
    if (!mqttSettings) return;
    setMqttHost(mqttSettings.host);
    setMqttPort(mqttSettings.port);
    setMqttUsername(mqttSettings.username);
    setMqttDiscoveryPrefix(mqttSettings.discovery_prefix);
    setMqttBaseTopic(mqttSettings.base_topic);
    setMqttDeviceId(mqttSettings.device_id);
    setMqttDeviceName(mqttSettings.device_name);
    setMqttUseTls(mqttSettings.use_tls);
  }, [mqttSettings]);

  useEffect(() => {
    if (!telegramSettings) return;
    setTgChatId(telegramSettings.chat_id);
  }, [telegramSettings]);

  useEffect(() => {
    if (!logsSettings) return;
    setLogMaxRows(logsSettings.max_rows);
  }, [logsSettings]);

  useEffect(() => {
    if (!trackedRebuild || !rebuildStatus || rebuildStatus.status === "running") return;
    if (rebuildStatus.status === "completed") {
      toast.success("Model changed and face embeddings rebuilt");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    } else if (rebuildStatus.status === "error") {
      toast.error(rebuildStatus.error || "Face embedding rebuild failed");
    }
    setTrackedRebuild(false);
  }, [queryClient, rebuildStatus, trackedRebuild]);

  const saveInsightFace = useMutation({
    mutationFn: api.saveInsightFace,
    onSuccess: (result) => {
      if ("status" in result) {
        setTrackedRebuild(true);
        queryClient.setQueryData(["insightface-rebuild"], result);
        toast.info("Rebuilding face embeddings");
      } else {
        toast.success("InsightFace settings saved");
        queryClient.invalidateQueries({ queryKey: ["settings"] });
        queryClient.invalidateQueries({ queryKey: ["summary"] });
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const downloadModel = useMutation({
    mutationFn: api.downloadInsightFaceModel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["insightface-models"] }),
    onError: (err) => toast.error(err.message),
  });

  const deleteModel = useMutation({
    mutationFn: api.deleteInsightFaceModel,
    onSuccess: () => {
      toast.success("Model deleted");
      queryClient.invalidateQueries({ queryKey: ["insightface-models"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const selectedModel = models.find((model) => model.model_name === modelName);

  const saveInsightFaceConfig = (next: {
    model_name?: string;
    provider?: string;
    det_size?: number;
    age_gender_enabled?: boolean;
  }) => {
    const nextModelName = next.model_name ?? modelName;
    const model = models.find((item) => item.model_name === nextModelName);
    if (model && !model.downloaded) {
      setPendingModelSave(nextModelName);
      if (model.status !== "downloading") {
        toast.info(`Downloading ${nextModelName}`);
        downloadModel.mutate(nextModelName);
      }
      return;
    }
    saveInsightFace.mutate({
      model_name: nextModelName,
      provider: next.provider ?? provider,
      det_size: next.det_size ?? detSize,
      age_gender_enabled: next.age_gender_enabled ?? ageGenderEnabled,
    });
  };

  useEffect(() => {
    if (!pendingModelSave) return;
    const model = models.find((item) => item.model_name === pendingModelSave);
    if (model?.downloaded) {
      const nextModelName = pendingModelSave;
      setPendingModelSave(null);
      saveInsightFace.mutate({
        model_name: nextModelName,
        provider,
        det_size: detSize,
        age_gender_enabled: ageGenderEnabled,
      });
    } else if (model?.status === "error") {
      setPendingModelSave(null);
    }
  }, [ageGenderEnabled, detSize, models, pendingModelSave, provider, saveInsightFace]);

  const saveThresholds = useMutation({
    mutationFn: () => api.saveThresholds({ match: match[0], auto_accept: accept[0] }),
    onSuccess: () => {
      toast.success("Thresholds saved");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const saveMqtt = useMutation({
    mutationFn: () =>
      api.saveMqtt({
        host: mqttHost,
        port: mqttPort,
        username: mqttUsername,
        password: mqttPassword,
        discovery_prefix: mqttDiscoveryPrefix,
        base_topic: mqttBaseTopic,
        device_id: mqttDeviceId,
        device_name: mqttDeviceName,
        use_tls: mqttUseTls,
      }),
    onSuccess: () => {
      toast.success("MQTT saved and Home Assistant discovery published");
      setMqttPassword("");
      queryClient.invalidateQueries({ queryKey: ["mqtt-settings"] });
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const testMqtt = useMutation({
    mutationFn: api.testMqtt,
    onSuccess: () => {
      toast.success("MQTT connection OK");
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const saveTelegram = useMutation({
    mutationFn: () => api.saveTelegram({ bot_token: tgBotToken, chat_id: tgChatId }),
    onSuccess: () => {
      toast.success("Telegram settings saved");
      setTgBotToken("");
      queryClient.invalidateQueries({ queryKey: ["telegram-settings"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const testTelegram = useMutation({
    mutationFn: api.testTelegram,
    onSuccess: (result) => {
      toast.success(`Telegram OK! Bot: @${result.bot_username}`);
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const saveStorage = useMutation({
    mutationFn: () => api.saveStorage({ max_storage_mb: maxStorageMb }),
    onSuccess: (result) => {
      const deleted = result.cleanup?.deleted_files ?? 0;
      toast.success(deleted ? `Storage saved, cleaned ${deleted} file(s)` : "Storage quota saved");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["storage-settings"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const cleanupStorage = useMutation({
    mutationFn: api.cleanupStorage,
    onSuccess: (result) => {
      toast.success(`Cleaned ${result.cleanup?.deleted_files ?? 0} file(s)`);
      queryClient.invalidateQueries({ queryKey: ["storage-settings"] });
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const clearAllData = useMutation({
    mutationFn: api.clearAllData,
    onSuccess: () => {
      toast.success("All IRIS data cleared");
      queryClient.invalidateQueries();
    },
    onError: (err) => toast.error(err.message),
  });

  const saveLogs = useMutation({
    mutationFn: () => api.saveLogsSettings({ max_rows: logMaxRows }),
    onSuccess: () => {
      toast.success("Log retention limit saved");
      queryClient.invalidateQueries({ queryKey: ["logs-settings"] });
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
    onError: (err) => toast.error(err.message),
  });

  const onMatchChange = (value: number[]) => {
    setMatch(value);
    if (accept[0] < value[0]) setAccept([value[0]]);
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="// Configuration"
        title="Settings"
        description="Configure the local InsightFace model, recognition thresholds, storage, and integrations."
      />

      <Tabs defaultValue="insightface">
        <TabsList className="h-auto max-w-full justify-start overflow-x-auto">
          <TabsTrigger value="insightface">
            <Cpu className="mr-2 h-4 w-4" /> InsightFace
          </TabsTrigger>
          <TabsTrigger value="recog">
            <Cpu className="mr-2 h-4 w-4" /> Recognition
          </TabsTrigger>
          <TabsTrigger value="storage">
            <HardDrive className="mr-2 h-4 w-4" /> Storage
          </TabsTrigger>
          <TabsTrigger value="mqtt">
            <RadioTower className="mr-2 h-4 w-4" /> MQTT
          </TabsTrigger>
          <TabsTrigger value="notif">
            <Bell className="mr-2 h-4 w-4" /> Notifications
          </TabsTrigger>
        </TabsList>

        <TabsContent value="insightface" className="mt-4 space-y-6">
          <Card className="border-border bg-card p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">InsightFace runtime</h3>
                <p className="text-xs text-muted-foreground">
                  Models and embeddings are stored locally. No cloud credentials are required.
                </p>
              </div>
              <Badge variant="outline" className="border-success/40 text-success">
                Local
              </Badge>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs">Model pack</Label>
                <div className="mt-1 flex gap-2">
                  <Select
                    value={modelName}
                    onValueChange={(value) => {
                      setModelName(value);
                      saveInsightFaceConfig({ model_name: value });
                    }}
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="antelopev2">
                        <span className="flex items-center gap-2">
                          antelopev2 (high accuracy · 361 MB)
                          {models.find((model) => model.model_name === "antelopev2")
                            ?.downloaded && <CheckCircle2 className="h-4 w-4 text-success" />}
                        </span>
                      </SelectItem>
                      <SelectItem value="buffalo_l">
                        <span className="flex items-center gap-2">
                          buffalo_l (accurate · 289 MB)
                          {models.find((model) => model.model_name === "buffalo_l")?.downloaded && (
                            <CheckCircle2 className="h-4 w-4 text-success" />
                          )}
                        </span>
                      </SelectItem>
                      <SelectItem value="buffalo_m">
                        <span className="flex items-center gap-2">
                          buffalo_m (balanced · 276 MB)
                          {models.find((model) => model.model_name === "buffalo_m")?.downloaded && (
                            <CheckCircle2 className="h-4 w-4 text-success" />
                          )}
                        </span>
                      </SelectItem>
                      <SelectItem value="buffalo_s">
                        <span className="flex items-center gap-2">
                          buffalo_s (lightweight · 128 MB)
                          {models.find((model) => model.model_name === "buffalo_s")?.downloaded && (
                            <CheckCircle2 className="h-4 w-4 text-success" />
                          )}
                        </span>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    title={selectedModel?.downloaded ? "Delete model" : "Download model"}
                    aria-label={selectedModel?.downloaded ? "Delete model" : "Download model"}
                    onClick={() => {
                      if (selectedModel?.downloaded) {
                        if (window.confirm(`Delete ${modelName} to free disk space?`))
                          deleteModel.mutate(modelName);
                      } else {
                        downloadModel.mutate(modelName);
                      }
                    }}
                    disabled={selectedModel?.status === "downloading" || deleteModel.isPending}
                  >
                    {selectedModel?.status === "downloading" || deleteModel.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : selectedModel?.downloaded ? (
                      <Trash2 className="h-4 w-4 text-destructive" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                {selectedModel?.status === "downloading" && (
                  <div className="mt-2 space-y-1">
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${selectedModel.progress}%` }}
                      />
                    </div>
                    <p className="text-right text-xs text-muted-foreground">
                      {selectedModel.progress}%
                    </p>
                  </div>
                )}
                {selectedModel?.status === "error" && (
                  <p className="mt-2 text-xs text-destructive">{selectedModel.error}</p>
                )}
              </div>
              <div>
                <Label className="text-xs">Execution provider</Label>
                <Select
                  value={provider}
                  onValueChange={(value) => {
                    setProvider(value);
                    saveInsightFaceConfig({ provider: value });
                  }}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="CPUExecutionProvider">Generic CPU (ONNX Runtime)</SelectItem>
                    <SelectItem value="OpenVINOCPU">
                      Intel CPU (OpenVINO + oneDNN vector)
                    </SelectItem>
                    <SelectItem value="OpenVINOAUTO">Intel Auto (CPU/iGPU/NPU)</SelectItem>
                    <SelectItem value="OpenVINOGPU">Intel iGPU / Arc GPU</SelectItem>
                    <SelectItem value="OpenVINONPU">Intel NPU</SelectItem>
                    <SelectItem value="CUDAExecutionProvider">NVIDIA CUDA GPU</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Detection size</Label>
                <Select
                  value={String(detSize)}
                  onValueChange={(value) => {
                    const nextDetSize = Number(value);
                    setDetSize(nextDetSize);
                    saveInsightFaceConfig({ det_size: nextDetSize });
                  }}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="320">320 × 320 (fast)</SelectItem>
                    <SelectItem value="640">640 × 640 (balanced)</SelectItem>
                    <SelectItem value="1280">1280 × 1280 (small faces)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="mt-5 flex items-center justify-between gap-4 rounded-md border border-border p-4">
              <div>
                <Label htmlFor="age-gender">Estimate age and gender</Label>
                <p className="text-xs text-muted-foreground">
                  Loads the additional genderage model. Keep disabled for lowest latency.
                </p>
              </div>
              <Switch
                id="age-gender"
                checked={ageGenderEnabled}
                onCheckedChange={(checked) => {
                  setAgeGenderEnabled(checked);
                  saveInsightFaceConfig({ age_gender_enabled: checked });
                }}
              />
            </div>

            {(saveInsightFace.isPending ||
              rebuildStatus?.status === "running" ||
              pendingModelSave) && (
              <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>
                  {pendingModelSave
                    ? `Downloading ${pendingModelSave} before saving`
                    : rebuildStatus?.status === "running"
                      ? "Rebuilding embeddings..."
                      : "Saving InsightFace settings..."}
                </span>
              </div>
            )}
            {rebuildStatus?.status === "running" && (
              <div className="mt-3 max-w-md space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Rebuilding for {rebuildStatus.model_name}</span>
                  <span>
                    {rebuildStatus.processed}/{rebuildStatus.total} ({rebuildStatus.progress}%)
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${rebuildStatus.progress}%` }}
                  />
                </div>
              </div>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="recog" className="mt-4 space-y-6">
          <Card className="border-border bg-card p-5">
            <h3 className="text-sm font-semibold">Recognition thresholds</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Below match is unknown. Between match and auto-accept needs review. Above auto-accept
              is recognized.
            </p>

            <div className="mt-5 space-y-5">
              <div>
                <div className="flex justify-between text-xs">
                  <Label className="text-xs">Face match threshold</Label>
                  <span className="font-mono text-primary">{match[0]}%</span>
                </div>
                <Slider
                  value={match}
                  onValueChange={onMatchChange}
                  min={0}
                  max={100}
                  step={1}
                  className="mt-2"
                />
              </div>
              <div>
                <div className="flex justify-between text-xs">
                  <Label className="text-xs">Auto-accept threshold</Label>
                  <span className="font-mono text-success">{accept[0]}%</span>
                </div>
                <Slider
                  value={accept}
                  onValueChange={setAccept}
                  min={match[0]}
                  max={100}
                  step={1}
                  className="mt-2"
                />
              </div>

              <div className="rounded-md border border-border bg-surface-elevated p-3">
                <div className="relative h-7 overflow-hidden rounded-md">
                  <div className="absolute inset-0 flex">
                    <div className="bg-destructive/30" style={{ width: `${match[0]}%` }} />
                    <div
                      className="bg-warning/30"
                      style={{ width: `${Math.max(0, accept[0] - match[0])}%` }}
                    />
                    <div className="flex-1 bg-success/40" />
                  </div>
                  <div className="absolute inset-0 flex items-center justify-between px-2 font-mono text-[10px] uppercase tracking-widest">
                    <span>Unknown</span>
                    <span>Review</span>
                    <span>Auto-accept</span>
                  </div>
                </div>
              </div>
              <Button onClick={() => saveThresholds.mutate()} disabled={saveThresholds.isPending}>
                <Save className="mr-2 h-4 w-4" /> Save thresholds
              </Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="storage" className="mt-4 space-y-6">
          <Card className="border-border bg-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-md bg-primary/10 p-2 ring-1 ring-primary/30">
                  <HardDrive className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">History storage</h3>
                  <p className="text-xs text-muted-foreground">
                    Unknown originals and trained faces are protected for future training.
                  </p>
                </div>
              </div>
              <Badge
                variant="outline"
                className={
                  (storageSettings?.percent ?? 0) >= 90
                    ? "border-warning/40 text-warning"
                    : "border-success/40 text-success"
                }
              >
                {storageSettings?.used_mb ?? 0} MB /{" "}
                {storageSettings?.max_storage_mb ?? maxStorageMb} MB
              </Badge>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs">Max storage MB</Label>
                <Input
                  type="number"
                  min={256}
                  max={102400}
                  value={maxStorageMb}
                  onChange={(event) => setMaxStorageMb(Number(event.target.value))}
                  className="mt-1 font-mono"
                />
              </div>
              <div className="rounded-md border border-border bg-surface-elevated p-3">
                <div className="text-xs text-muted-foreground">Protected unknown</div>
                <div className="mt-1 font-mono text-lg text-warning">
                  {storageSettings?.protected_unknown ?? 0}
                </div>
              </div>
              <div className="rounded-md border border-border bg-surface-elevated p-3">
                <div className="text-xs text-muted-foreground">Training faces</div>
                <div className="mt-1 font-mono text-lg text-success">
                  {storageSettings?.protected_faces ?? 0}
                </div>
              </div>
            </div>

            <div className="mt-5 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary"
                style={{ width: `${Math.min(100, storageSettings?.percent ?? 0)}%` }}
              />
            </div>

            <div className="mt-5 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap">
              <Button
                onClick={() => saveStorage.mutate()}
                disabled={saveStorage.isPending || maxStorageMb < 256}
              >
                <Save className="mr-2 h-4 w-4" /> Save storage
              </Button>
              <Button
                variant="outline"
                onClick={() => cleanupStorage.mutate()}
                disabled={cleanupStorage.isPending}
              >
                <Trash2 className="mr-2 h-4 w-4" /> Cleanup now
              </Button>
            </div>
          </Card>

          <Card className="border-border bg-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-md bg-primary/10 p-2 ring-1 ring-primary/30">
                  <ScrollText className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Log retention limit</h3>
                  <p className="text-xs text-muted-foreground">
                    Maximum number of log entries kept in the local database.
                  </p>
                </div>
              </div>
              <Badge variant="outline" className="border-primary/40 text-primary">
                {logsSettings?.max_rows ?? logMaxRows} rows
              </Badge>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs">Total rows to keep</Label>
                <Input
                  type="number"
                  min={50}
                  max={10000}
                  step={50}
                  value={logMaxRows}
                  onChange={(event) => setLogMaxRows(Number(event.target.value))}
                  className="mt-1 font-mono"
                />
              </div>
              <div className="rounded-md border border-border bg-surface-elevated p-3">
                <div className="text-xs text-muted-foreground">Preset</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {[100, 200, 500, 1000, 2000].map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setLogMaxRows(v)}
                      className={`rounded-md px-2 py-0.5 font-mono text-xs transition-colors ${
                        logMaxRows === v
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap">
              <Button
                onClick={() => saveLogs.mutate()}
                disabled={saveLogs.isPending || logMaxRows < 50 || logMaxRows > 10000}
              >
                <Save className="mr-2 h-4 w-4" /> Save retention limit
              </Button>
            </div>
          </Card>

          <Card className="border-destructive/40 bg-card p-5">
            <h3 className="text-sm font-semibold text-destructive">Clear all data</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Permanently deletes people, faces, events, cameras, logs, settings, uploads, and
              downloaded models.
            </p>
            <Button
              variant="destructive"
              className="mt-4"
              disabled={clearAllData.isPending}
              onClick={() => {
                if (
                  window.confirm("Permanently delete ALL IRIS data? This action cannot be undone.")
                ) {
                  clearAllData.mutate();
                }
              }}
            >
              {clearAllData.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Clear all data
            </Button>
          </Card>
        </TabsContent>

        <TabsContent value="mqtt" className="mt-4 space-y-6">
          <Card className="border-border bg-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-md bg-primary/10 p-2 ring-1 ring-primary/30">
                  <SatelliteDish className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Home Assistant MQTT</h3>
                  <p className="text-xs text-muted-foreground">
                    Connect to the Home Assistant MQTT broker and publish discovery entities
                    automatically.
                  </p>
                </div>
              </div>
              <Badge
                variant="outline"
                className={
                  mqttSettings?.configured
                    ? "border-success/40 text-success"
                    : "border-warning/40 text-warning"
                }
              >
                {mqttSettings?.configured ? "Configured" : "Not configured"}
              </Badge>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs">Broker host</Label>
                <Input
                  value={mqttHost}
                  onChange={(event) => setMqttHost(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder="homeassistant.local"
                />
              </div>
              <div>
                <Label className="text-xs">Port</Label>
                <Input
                  type="number"
                  value={mqttPort}
                  onChange={(event) => setMqttPort(Number(event.target.value))}
                  className="mt-1 font-mono"
                />
              </div>
              <div>
                <Label className="text-xs">TLS</Label>
                <div className="mt-2">
                  <Switch checked={mqttUseTls} onCheckedChange={setMqttUseTls} />
                </div>
              </div>
              <div>
                <Label className="text-xs">Username</Label>
                <Input
                  value={mqttUsername}
                  onChange={(event) => setMqttUsername(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder="homeassistant"
                />
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs">Password</Label>
                <Input
                  type="password"
                  value={mqttPassword}
                  onChange={(event) => setMqttPassword(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder={
                    mqttSettings?.password_configured
                      ? "Already saved - enter a new password to replace"
                      : "MQTT password"
                  }
                />
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 border-t border-border pt-5 md:grid-cols-2">
              <div>
                <Label className="text-xs">Discovery prefix</Label>
                <Input
                  value={mqttDiscoveryPrefix}
                  onChange={(event) => setMqttDiscoveryPrefix(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder="homeassistant"
                />
              </div>
              <div>
                <Label className="text-xs">Base topic</Label>
                <Input
                  value={mqttBaseTopic}
                  onChange={(event) => setMqttBaseTopic(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder="iris"
                />
              </div>
              <div>
                <Label className="text-xs">Device ID</Label>
                <Input
                  value={mqttDeviceId}
                  onChange={(event) => setMqttDeviceId(event.target.value)}
                  className="mt-1 font-mono"
                  placeholder="iris_face_recognition"
                />
              </div>
              <div>
                <Label className="text-xs">Device name</Label>
                <Input
                  value={mqttDeviceName}
                  onChange={(event) => setMqttDeviceName(event.target.value)}
                  className="mt-1"
                  placeholder="IRIS Face Recognition"
                />
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap">
              <Button
                onClick={() => saveMqtt.mutate()}
                disabled={!mqttHost.trim() || saveMqtt.isPending}
              >
                <Save className="mr-2 h-4 w-4" /> Save MQTT
              </Button>
              <Button
                variant="outline"
                onClick={() => testMqtt.mutate()}
                disabled={!mqttSettings?.configured || testMqtt.isPending}
              >
                <Plug className="mr-2 h-4 w-4" /> Test connection
              </Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="notif" className="mt-4 space-y-4">
          <Card className="border-border bg-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-md bg-primary/10 p-2 ring-1 ring-primary/30">
                  <Send className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Telegram Notifications</h3>
                  <p className="text-xs text-muted-foreground">
                    Get instant recognition alerts via Telegram bot.
                  </p>
                </div>
              </div>
              <Badge
                variant="outline"
                className={
                  telegramSettings?.configured
                    ? "border-success/40 text-success"
                    : "border-warning/40 text-warning"
                }
              >
                {telegramSettings?.configured ? "Active" : "Not configured"}
              </Badge>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <Label className="text-xs">Bot Token</Label>
                <Input
                  type="password"
                  value={tgBotToken}
                  onChange={(e) => setTgBotToken(e.target.value)}
                  className="mt-1 font-mono"
                  placeholder={
                    telegramSettings?.bot_token_configured
                      ? "Already saved - enter new token to replace"
                      : "123456:ABC-DEF..."
                  }
                />
              </div>
              <div>
                <Label className="text-xs">Chat ID</Label>
                <Input
                  value={tgChatId}
                  onChange={(e) => setTgChatId(e.target.value)}
                  className="mt-1 font-mono"
                  placeholder="-1001234567890"
                />
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:flex-wrap">
              <Button
                onClick={() => saveTelegram.mutate()}
                disabled={!tgChatId.trim() || saveTelegram.isPending}
              >
                <Save className="mr-2 h-4 w-4" /> Save Telegram
              </Button>
              <Button
                variant="outline"
                onClick={() => testTelegram.mutate()}
                disabled={!telegramSettings?.configured || testTelegram.isPending}
              >
                <Plug className="mr-2 h-4 w-4" /> Test connection
              </Button>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
