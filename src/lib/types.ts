export type Role = "Family" | "Friend" | "Employee" | "Guest";
export type Severity = "info" | "warn" | "error";
export type EventType =
  | "known"
  | "unknown"
  | "review"
  | "no_face"
  | "skipped"
  | "error"
  | "processing";

export interface Person {
  id: string;
  name: string;
  alias: string;
  displayName: string;
  role: Role;
  notes: string;
  photos: number;
  lastSeen: string;
  status: "Active" | "Disabled";
  indexedFaces: number;
  totalRecognitions: number;
  faceId: string;
  latest_image_path?: string;
  faces?: PersonFace[];
  events?: EventItem[];
}

export interface PersonFace {
  id: string;
  person_id: string;
  face_id: string;
  image_path: string;
  created_at: string;
}

export interface Camera {
  id: string;
  name: string;
  model: string;
  status: "online" | "offline";
  stream_url: string;
  still_url: string;
  trigger_slug: string;
  trigger_path: string;
  latest_image_path: string;
  last_detection?: string;
  lastDetection?: string;
  face_detection: number;
  motion: number;
  cooldown: number;
  min_face: number;
  min_confidence: number;
}

export interface EventItem {
  id: string;
  person_id?: string;
  personId?: string;
  person_name: string;
  personName?: string;
  confidence: number;
  camera_id?: string;
  cameraId?: string;
  camera_name: string;
  cameraName?: string;
  event_time: string;
  time?: string;
  type: EventType;
  face_id?: string;
  faceId?: string;
  inference_id: string;
  inferenceId?: string;
  processing_ms: number;
  face_bounding_box?: string;
  face_details_json?: string;
  image_path?: string;
  thumb_path?: string;
  face_crop_path?: string;
  original_deleted_at?: string;
  is_trained?: boolean;
  isTrained?: boolean;
  /** Present on /api/recognize responses: events for the other faces in the same image. */
  additional_events?: EventItem[];
  unknown_id?: string | null;
}

export interface UnknownVisitor {
  id: string;
  camera_id?: string;
  cameraId?: string;
  camera_name: string;
  cameraName?: string;
  image_path: string;
  created_at: string;
  time?: string;
  detections: number;
}

export interface LogEntry {
  id: string;
  time: string;
  created_at: string;
  service: "InsightFace" | "UniFi" | "Recognition" | "Notification" | "System";
  severity: Severity;
  message: string;
}

export interface Settings {
  insightface_configured: boolean;
  model_name: string;
  provider:
    | "CPUExecutionProvider"
    | "CUDAExecutionProvider"
    | "OpenVINOAUTO"
    | "OpenVINOCPU"
    | "OpenVINOGPU"
    | "OpenVINONPU";
  det_size: number;
  age_gender_enabled: boolean;
  max_faces: number;
  thresholds: { match: number; auto_accept: number };
  storage: { max_storage_mb: number };
  telegram_configured: boolean;
}

export interface ModelDownloadStatus {
  model_name: "antelopev2" | "buffalo_l" | "buffalo_m" | "buffalo_s";
  status: "idle" | "downloading" | "completed" | "error";
  progress: number;
  size_bytes: number;
  downloaded: boolean;
  error: string | null;
}

export interface ModelRebuildStatus {
  status: "idle" | "running" | "completed" | "error";
  model_name: string;
  processed: number;
  total: number;
  progress: number;
  error: string | null;
}

export interface StorageSettings {
  used_bytes: number;
  max_bytes: number;
  used_mb: number;
  max_storage_mb: number;
  percent: number;
  protected_unknown: number;
  protected_faces: number;
  cleanup?: {
    ok: boolean;
    deleted_files: number;
    deleted_bytes: number;
    used_bytes: number;
    max_bytes: number;
  };
}

export interface MqttSettings {
  configured: boolean;
  host: string;
  port: number;
  username: string;
  password_configured: boolean;
  discovery_prefix: string;
  base_topic: string;
  device_id: string;
  device_name: string;
  use_tls: boolean;
}

export interface TelegramSettings {
  configured: boolean;
  bot_token_configured: boolean;
  chat_id: string;
}

export interface LogsSettings {
  max_rows: number;
}

export interface PaginatedEvents {
  items: EventItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface PaginatedLogs {
  items: LogEntry[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface DashboardData {
  summary: {
    people: number;
    activePeople: number;
    events: number;
    unknown: number;
    latest?: EventItem | null;
  };
  events: EventItem[];
  local_inference: {
    indexed_faces: number;
    model: string;
    provider: string;
    average_processing_ms: number;
  };
  services: {
    system: boolean;
    insightface: boolean;
    mqtt: boolean;
    telegram: boolean;
  };
}

export interface AnalyticsData {
  days: number;
  summary: {
    total: number;
    known: number;
    review: number;
    unknown: number;
    no_face: number;
    unique_people: number;
    recognized_rate: number;
    avg_known_confidence: number;
    avg_processing_ms: number;
  };
  daily: Array<{
    date: string;
    total: number;
    known: number;
    review: number;
    unknown: number;
    no_face: number;
  }>;
  hourly: Array<{ hour: number; count: number }>;
  top_people: Array<{
    person_id: string;
    person_name: string;
    count: number;
    avg_confidence: number;
    last_seen: string;
  }>;
  cameras: Array<{ camera_name: string; count: number }>;
}

export interface MqttStatus {
  configured: boolean;
  connected: boolean;
  host: string;
  port: number;
  client_id: string;
  last_connected_at: string;
  last_disconnected_at: string;
  last_error: string;
}

export interface MqttMessage {
  time: string;
  direction: "out" | "in" | "system";
  topic: string;
  payload: string;
  retain: boolean;
  qos: number;
  status: string;
}
