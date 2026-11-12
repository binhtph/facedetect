// Drives headless Chrome through the IRIS UI under the emulated HA ingress path and
// through the direct :8080 port, failing on any request that escapes the prefix.
import puppeteer from "puppeteer-core";

const INGRESS = "/api/hassio_ingress/Tok3n_ABCdef-123";
const targets = [
  { name: "ingress", base: `http://127.0.0.1:8123${INGRESS}` },
  { name: "direct :8080", base: "http://127.0.0.1:8080" },
];
const pages = ["/", "/people", "/events", "/analytics", "/mqtt", "/settings", "/test", "/logs"];

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
});
let failures = 0;
const fail = (msg) => {
  failures += 1;
  console.log(`FAIL  ${msg}`);
};

for (const target of targets) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const bad = [];
  const errors = [];
  page.on("response", (r) => {
    const url = new URL(r.url());
    if (url.hostname !== "127.0.0.1") return;
    if (url.pathname.endsWith("/favicon.ico")) return; // requested by the browser itself, IRIS has none
    if (r.status() >= 400) bad.push(`${r.status()} ${url.pathname}`);
    if (target.name === "ingress" && url.port === "8123" && !url.pathname.startsWith(INGRESS))
      bad.push(`escaped prefix: ${url.pathname}`);
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });

  for (const path of pages) {
    await page.goto(`${target.base}${path}`, { waitUntil: "networkidle0", timeout: 60000 });
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes("Signal lost")) fail(`[${target.name}] ${path} rendered the 404 page`);
  }
  // Client-side navigation through the sidebar keeps the prefix
  await page.goto(`${target.base}/`, { waitUntil: "networkidle0" });
  const sidebarHrefs = await page.$$eval("a[href]", (as) => as.map((a) => a.getAttribute("href")));
  const appLinks = sidebarHrefs.filter((h) => h && h.startsWith("/") && !h.startsWith("//"));
  if (target.name === "ingress") {
    const leaking = appLinks.filter((h) => !h.startsWith(INGRESS));
    if (leaking.length) fail(`[ingress] links without prefix: ${leaking.join(", ")}`);
  }
  await page.click('a[href$="/analytics"]');
  await page.waitForFunction(
    () =>
      document.body.innerText.includes("Recognitions per day") ||
      document.body.innerText.includes("No recognition events"),
    { timeout: 20000 },
  );
  const afterNav = page.url();
  if (target.name === "ingress" && !new URL(afterNav).pathname.startsWith(`${INGRESS}/analytics`))
    fail(`[ingress] sidebar navigation went to ${afterNav}`);
  await page.click('a[href$="/mqtt"]');
  await page.waitForFunction(() => document.body.innerText.includes("MQTT monitor"), {
    timeout: 20000,
  });
  // Reload deep link (SSR under prefix) and go back in history
  await page.reload({ waitUntil: "networkidle0" });
  if (!(await page.evaluate(() => document.body.innerText.includes("MQTT monitor"))))
    fail(`[${target.name}] reload of /mqtt failed`);
  await page.goBack({ waitUntil: "networkidle0" });
  if (!new URL(page.url()).pathname.endsWith("/analytics"))
    fail(`[${target.name}] history back went to ${page.url()}`);
  // A data request through the API base
  const apiOk = await page.evaluate(
    async (base) => (await fetch(`${base}/api/health`)).ok,
    target.base,
  );
  if (!apiOk) fail(`[${target.name}] API health through base failed`);

  const hydration = errors.filter((e) => /hydrat/i.test(e));
  if (hydration.length)
    fail(`[${target.name}] hydration errors: ${hydration.slice(0, 2).join(" | ")}`);
  if (bad.length)
    fail(`[${target.name}] bad requests: ${[...new Set(bad)].slice(0, 8).join(", ")}`);
  const otherErrors = errors.filter(
    (e) => !/hydrat/i.test(e) && !/fonts\.googleapis|Failed to load resource/i.test(e),
  );
  if (otherErrors.length)
    console.log(`note  [${target.name}] console errors: ${otherErrors.slice(0, 3).join(" | ")}`);
  await page.screenshot({ path: `./shot-${target.name.replace(/\W+/g, "_")}.png` });
  console.log(`done  [${target.name}] ${pages.length} pages + navigation checked`);
  await page.close();
}
await browser.close();
console.log(failures ? `${failures} problem(s)` : "browser checks passed");
process.exit(failures ? 1 : 0);
