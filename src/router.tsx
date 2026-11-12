import { QueryClient } from "@tanstack/react-query";
import { createRouter, type LocationRewrite } from "@tanstack/react-router";
import { createIsomorphicFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import { routeTree } from "./routeTree.gen";
import { clientBasepath, ingressPathFrom } from "./lib/basepath";

// Under Home Assistant ingress the page lives at /api/hassio_ingress/<token>/...
// The web server re-adds that prefix to the SSR request URL, so both sides agree.
// TanStack Start forces the build-time `basepath`, so the dynamic prefix is applied with
// a location rewrite instead.
const routerBasepath = createIsomorphicFn()
  .server(() => ingressPathFrom(new URL(getRequest().url).pathname))
  .client(() => clientBasepath());

const ingressRewrite = (basepath: string): LocationRewrite | undefined =>
  basepath
    ? {
        input: ({ url }) => {
          if (url.pathname === basepath) url.pathname = "/";
          else if (url.pathname.startsWith(`${basepath}/`))
            url.pathname = url.pathname.slice(basepath.length);
          return url;
        },
        output: ({ url }) => {
          if (!url.pathname.startsWith(`${basepath}/`) && url.pathname !== basepath) {
            url.pathname = `${basepath}${url.pathname.startsWith("/") ? "" : "/"}${url.pathname}`;
          }
          return url;
        },
      }
    : undefined;

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    rewrite: ingressRewrite(routerBasepath()),
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
