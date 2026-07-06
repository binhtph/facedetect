import { apiUrl } from "@/lib/http";

export const uploadUrl = (path?: string) => {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path)) return path;

  const normalizedPath = path.replaceAll("\\", "/").replace(/^\/+/, "");
  if (normalizedPath.startsWith("api/uploads/")) {
    return apiUrl(`/${normalizedPath}`);
  }
  if (normalizedPath.startsWith("uploads/")) {
    return apiUrl(`/api/${normalizedPath}`);
  }
  return apiUrl(`/api/uploads/${normalizedPath}`);
};

export const cameraSnapshotUrl = (cameraId: string, cacheKey: number | string = Date.now()) =>
  apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/snapshot?ts=${cacheKey}`);
