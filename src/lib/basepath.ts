// Home Assistant ingress serves the add-on under /api/hassio_ingress/<token>/ and strips
// that prefix before the request reaches IRIS. The browser still sees the prefix, so
// every URL the UI builds (router links, API calls, uploads) must include it.
export const INGRESS_PATH_PATTERN = /^\/api\/hassio_ingress\/[^/]+/;

export const ingressPathFrom = (pathname: string | undefined | null): string =>
  pathname?.match(INGRESS_PATH_PATTERN)?.[0] ?? "";

export const clientBasepath = (): string =>
  typeof window === "undefined" ? "" : ingressPathFrom(window.location.pathname);

export const appPath = (path: string): string =>
  `${clientBasepath()}${path.startsWith("/") ? path : `/${path}`}`;
