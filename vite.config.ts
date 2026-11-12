// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, nitro (build-only using cloudflare as a default target),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Chunk preloads must follow the page's base path, so the same build works both at
// http://host:8080/ and under Home Assistant ingress (/api/hassio_ingress/<token>/).
const ingressAwareAssetUrl = (filename: string) =>
  `((globalThis.location && globalThis.location.pathname.match(/^\\/api\\/hassio_ingress\\/[^/]+/)) || [""])[0] + ${JSON.stringify(`/${filename}`)}`;

export default defineConfig({
  vite: {
    logLevel: "error",
    experimental: {
      renderBuiltUrl(filename: string, { hostType, ssr }: { hostType: string; ssr: boolean }) {
        if (ssr || hostType !== "js") return undefined;
        return { runtime: ingressAwareAssetUrl(filename) };
      },
    },
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  nitro: false,
});
