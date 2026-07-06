import { request } from "@/lib/http";
import type {
  Camera,
  DashboardData,
  EventItem,
  LogsSettings,
  MqttSettings,
  PaginatedEvents,
  PaginatedLogs,
  Person,
  Role,
  Settings,
  ModelDownloadStatus,
  ModelRebuildStatus,
  StorageSettings,
  TelegramSettings,
  UnknownVisitor,
} from "@/lib/types";

export { API_BASE, apiUrl, request } from "@/lib/http";
export { cameraSnapshotUrl, uploadUrl } from "@/lib/uploads";
export type {
  Camera,
  EventItem,
  EventType,
  DashboardData,
  LogEntry,
  LogsSettings,
  MqttSettings,
  PaginatedEvents,
  PaginatedLogs,
  Person,
  PersonFace,
  Role,
  Settings,
  Severity,
  StorageSettings,
  TelegramSettings,
  UnknownVisitor,
} from "@/lib/types";

export const normalizeEvent = (event: EventItem): EventItem => ({
  ...event,
  personId: event.person_id,
  personName: event.person_name,
  cameraId: event.camera_id,
  cameraName: event.camera_name,
  time: event.event_time,
  faceId: event.face_id,
  inferenceId: event.inference_id,
  isTrained: event.is_trained,
});

export const normalizeUnknown = (unknown: UnknownVisitor): UnknownVisitor => ({
  ...unknown,
  cameraId: unknown.camera_id,
  cameraName: unknown.camera_name,
  time: unknown.created_at,
});

export const api = {
  settings: () => request<Settings>("/api/settings"),
  insightFaceModels: () => request<ModelDownloadStatus[]>("/api/settings/insightface/models"),
  downloadInsightFaceModel: (modelName: string) =>
    request<ModelDownloadStatus>(`/api/settings/insightface/models/${modelName}/download`, {
      method: "POST",
    }),
  deleteInsightFaceModel: (modelName: string) =>
    request<ModelDownloadStatus>(`/api/settings/insightface/models/${modelName}`, {
      method: "DELETE",
    }),
  saveInsightFace: (payload: { model_name: string; provider: string; det_size: number; age_gender_enabled: boolean }) =>
    request<Settings | ModelRebuildStatus>("/api/settings/insightface", { method: "PUT", body: JSON.stringify(payload) }),
  insightFaceRebuild: () =>
    request<ModelRebuildStatus>("/api/settings/insightface/rebuild"),
  testInsightFace: () =>
    request<{ ok: boolean }>("/api/settings/insightface/test", {
      method: "POST",
    }),
  mqtt: () => request<MqttSettings>("/api/settings/mqtt"),
  saveMqtt: (payload: {
    host: string;
    port: number;
    username: string;
    password: string;
    discovery_prefix: string;
    base_topic: string;
    device_id: string;
    device_name: string;
    use_tls: boolean;
  }) =>
    request<MqttSettings>("/api/settings/mqtt", { method: "PUT", body: JSON.stringify(payload) }),
  testMqtt: () => request<{ ok: boolean }>("/api/settings/mqtt/test", { method: "POST" }),
  publishMqttDiscovery: () =>
    request<{ ok: boolean; entities: number }>("/api/settings/mqtt/discovery", { method: "POST" }),
  telegram: () => request<TelegramSettings>("/api/settings/telegram"),
  saveTelegram: (payload: { bot_token: string; chat_id: string }) =>
    request<TelegramSettings>("/api/settings/telegram", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testTelegram: () =>
    request<{ ok: boolean; bot_username: string }>("/api/settings/telegram/test", {
      method: "POST",
    }),
  saveThresholds: (payload: { match: number; auto_accept: number }) =>
    request<Settings>("/api/settings/thresholds", { method: "PUT", body: JSON.stringify(payload) }),
  storage: () => request<StorageSettings>("/api/settings/storage"),
  saveStorage: (payload: { max_storage_mb: number }) =>
    request<StorageSettings>("/api/settings/storage", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  cleanupStorage: () =>
    request<StorageSettings>("/api/settings/storage/cleanup", { method: "POST" }),
  clearAllData: () =>
    request<{ ok: boolean }>("/api/settings/data/clear", { method: "POST" }),
  summary: () =>
    request<{
      people: number;
      activePeople: number;
      events: number;
      unknown: number;
      latest?: EventItem;
    }>("/api/summary"),
  dashboard: async () => {
    const data = await request<DashboardData>("/api/dashboard");
    return {
      ...data,
      summary: {
        ...data.summary,
        latest: data.summary.latest ? normalizeEvent(data.summary.latest) : data.summary.latest,
      },
      events: data.events.map(normalizeEvent),
    };
  },
  people: () => request<Person[]>("/api/people"),
  person: (id: string) => request<Person>(`/api/people/${id}`),
  createPerson: (payload: { name: string; alias?: string; notes: string; role?: Role }) =>
    request<Person>("/api/people", { method: "POST", body: JSON.stringify(payload) }),
  updatePerson: (
    id: string,
    payload: {
      name: string;
      alias?: string;
      notes: string;
      status: "Active" | "Disabled";
      role?: Role;
    },
  ) => request<Person>(`/api/people/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePerson: (id: string) => request<{ ok: boolean }>(`/api/people/${id}`, { method: "DELETE" }),
  uploadFace: (personId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ ok: boolean; face_id: string }>(`/api/people/${personId}/faces`, {
      method: "POST",
      body,
    });
  },
  deleteFace: (personId: string, faceId: string) =>
    request<{ ok: boolean }>(`/api/people/${personId}/faces/${faceId}`, { method: "DELETE" }),
  events: async (params?: {
    page?: number;
    limit?: number;
    event_type?: string;
    camera_id?: string;
    person_id?: string;
  }) => {
    const search = new URLSearchParams();
    if (params?.page) search.set("page", String(params.page));
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.event_type) search.set("event_type", params.event_type);
    if (params?.camera_id) search.set("camera_id", params.camera_id);
    if (params?.person_id) search.set("person_id", params.person_id);
    const suffix = search.toString() ? `?${search.toString()}` : "";
    const result = await request<PaginatedEvents>(`/api/events${suffix}`);
    return { ...result, items: result.items.map(normalizeEvent) };
  },
  event: async (id: string) => normalizeEvent(await request<EventItem>(`/api/events/${id}`)),
  deleteEvent: (id: string) => request<{ ok: boolean }>(`/api/events/${id}`, { method: "DELETE" }),
  trainEvent: async (eventId: string, personId: string) => {
    const result = await request<{ ok: boolean; face_id: string; event: EventItem }>(
      `/api/events/${eventId}/train/${personId}`,
      { method: "POST" },
    );
    return { ...result, event: normalizeEvent(result.event) };
  },
  recognize: (file: File, cameraName = "Manual upload", cameraId = "", notify = true) => {
    const body = new FormData();
    body.append("file", file);
    body.append("camera_name", cameraName);
    body.append("camera_id", cameraId);
    body.append("notify", String(notify));
    return request<EventItem>("/api/recognize", { method: "POST", body });
  },
  unknowns: async () => (await request<UnknownVisitor[]>("/api/unknowns")).map(normalizeUnknown),
  assignUnknown: (unknownId: string, personId: string) =>
    request<{ ok: boolean }>(`/api/unknowns/${unknownId}/assign/${personId}`, { method: "POST" }),
  deleteUnknown: (unknownId: string) =>
    request<{ ok: boolean }>(`/api/unknowns/${unknownId}`, { method: "DELETE" }),
  cameras: () => request<Camera[]>("/api/cameras"),
  createCamera: (payload: Record<string, unknown>) =>
    request<Camera>("/api/cameras", { method: "POST", body: JSON.stringify(payload) }),
  camera: (id: string) => request<Camera>(`/api/cameras/${id}`),
  updateCamera: (id: string, payload: Record<string, unknown>) =>
    request<Camera>(`/api/cameras/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteCamera: (id: string) =>
    request<{ ok: boolean }>(`/api/cameras/${id}`, { method: "DELETE" }),
  logs: (page = 1, limit?: number) => {
    const params = new URLSearchParams({ page: String(page) });
    if (limit) params.set("limit", String(limit));
    return request<PaginatedLogs>(`/api/logs?${params.toString()}`);
  },
  logsSettings: () => request<LogsSettings>("/api/settings/logs"),
  saveLogsSettings: (payload: { max_rows: number }) =>
    request<LogsSettings>("/api/settings/logs", { method: "PUT", body: JSON.stringify(payload) }),
};
