import { clientBasepath } from "@/lib/basepath";

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

const defaultApiBase =
  typeof window === "undefined"
    ? ""
    : window.location.port === "5173"
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : `${window.location.origin}${clientBasepath()}`;

export const API_BASE = trimTrailingSlash(import.meta.env.VITE_API_URL || defaultApiBase);

export const apiUrl = (path: string) => {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
};

export class ApiError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code: string | undefined;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        message = body.detail.message ?? message;
        code = body.detail.code;
      }
    } catch {
      // keep status message
    }
    throw new ApiError(message, code);
  }
  return response.json() as Promise<T>;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers =
    options?.body instanceof FormData ? undefined : { "content-type": "application/json" };
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      headers: { ...headers, ...options?.headers },
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Python backend is not reachable at ${API_BASE}. Start it with: npm run api`);
    }
    throw error;
  }
  return parseResponse<T>(response);
}
