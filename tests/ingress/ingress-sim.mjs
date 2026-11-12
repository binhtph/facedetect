// Emulates the two proxies that sit in front of IRIS inside Home Assistant:
//  - :8123  Home Assistant ingress: /api/hassio_ingress/<token>/<rest> -> add-on /<rest>
//           (prefix stripped, X-Ingress-Path header added) — like the Supervisor does.
//  - :8080  the add-on's nginx (docker/nginx.conf): /api -> uvicorn :8000,
//           /assets -> dist/client/assets, everything else -> SSR node :3000 with the
//           same sub_filter rewrite of "/assets/ in HTML.
import { createServer, request as httpRequest } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";

const DIST = process.argv[2];
const TOKEN = "Tok3n_ABCdef-123";
const INGRESS = `/api/hassio_ingress/${TOKEN}`;
const types = {
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function forward(req, res, port, path, extraHeaders = {}, rewriteHtml) {
  const upstream = httpRequest(
    {
      host: "127.0.0.1",
      port,
      method: req.method,
      path,
      headers: { ...req.headers, ...extraHeaders, "accept-encoding": "" },
    },
    (up) => {
      const isHtml = String(up.headers["content-type"] || "").includes("text/html");
      if (!rewriteHtml || !isHtml) {
        res.writeHead(up.statusCode, up.headers);
        up.pipe(res);
        return;
      }
      const chunks = [];
      up.on("data", (c) => chunks.push(c));
      up.on("end", () => {
        const body = rewriteHtml(Buffer.concat(chunks).toString("utf8"));
        const headers = { ...up.headers };
        delete headers["content-length"];
        res.writeHead(up.statusCode, headers);
        res.end(body);
      });
    },
  );
  upstream.on("error", (e) => {
    res.writeHead(502);
    res.end(String(e));
  });
  req.pipe(upstream);
}

// add-on nginx
createServer(async (req, res) => {
  const url = new URL(req.url, "http://addon");
  if (url.pathname.startsWith("/api/")) return forward(req, res, 8000, req.url);
  if (url.pathname.startsWith("/assets/")) {
    try {
      const data = await readFile(join(DIST, "client", url.pathname));
      res.writeHead(200, {
        "content-type": types[extname(url.pathname)] || "application/octet-stream",
      });
      return res.end(data);
    } catch {
      res.writeHead(404);
      return res.end("not found");
    }
  }
  const ingressPath = req.headers["x-ingress-path"] || "";
  return forward(req, res, 3000, req.url, {}, (html) =>
    html.split('"/assets/').join(`"${ingressPath}/assets/`),
  );
}).listen(8080, "127.0.0.1");

// Home Assistant ingress
createServer((req, res) => {
  if (!req.url.startsWith(`${INGRESS}/`) && req.url !== INGRESS) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end(`HA 404 for ${req.url}`);
    return;
  }
  const rest = req.url.slice(INGRESS.length) || "/";
  forward(req, res, 8080, rest, { "x-ingress-path": INGRESS });
}).listen(8123, "127.0.0.1", () =>
  console.log(`ingress sim ready: http://127.0.0.1:8123${INGRESS}/`),
);
