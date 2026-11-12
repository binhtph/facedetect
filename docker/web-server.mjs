import { createServer } from "node:http";
import serverEntry from "../dist/server/server.js";

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "127.0.0.1";

const server = createServer(async (req, res) => {
  try {
    // Home Assistant ingress strips /api/hassio_ingress/<token> before proxying and sends it
    // in X-Ingress-Path. Put it back so the SSR router renders links with the right prefix.
    const ingressHeader = String(req.headers["x-ingress-path"] || "");
    const ingressPath = /^\/api\/hassio_ingress\/[A-Za-z0-9_-]+$/.test(ingressHeader)
      ? ingressHeader
      : "";
    const url = new URL(
      `${ingressPath}${req.url || "/"}`,
      `http://${req.headers.host || `${host}:${port}`}`,
    );
    const body = req.method === "GET" || req.method === "HEAD" ? undefined : req;
    const request = new Request(url, {
      method: req.method,
      headers: req.headers,
      body,
      duplex: body ? "half" : undefined,
    });
    const response = await serverEntry.fetch(request, {}, {});

    res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
    if (req.method === "HEAD" || !response.body) {
      res.end();
      return;
    }
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(Buffer.from(value));
    }
    res.end();
  } catch (error) {
    console.error(error);
    res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    res.end("Internal Server Error");
  }
});

server.listen(port, host, () => {
  console.log(`Web server listening on http://${host}:${port}`);
});
