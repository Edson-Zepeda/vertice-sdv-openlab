/* Transport-failure fixtures are explicit; all successful solves use the real Python API. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "evidence", "ui");
const CAPTURES = path.join(ROOT, "output", "playwright");
const BASE = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(CAPTURES, { recursive: true });
const evidence = {
  started_at: new Date().toISOString(),
  url: BASE,
  methodology:
    "Real local Python. Explicit network delays, HTTP error, and storage-quota fixtures test recovery; no simulated successful algorithm result.",
  environment: {
    platform: os.platform(),
    architecture: os.arch(),
    node: process.version,
    cpu: os.cpus()[0]?.model,
  },
  checks: [],
  observations: {},
};
function check(name, passed, details = {}) {
  evidence.checks.push({ name, passed: !!passed, ...details });
  if (!passed) throw new Error(name + ": " + JSON.stringify(details));
}
const wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));
async function upload(page, buffer) {
  await page
    .locator("#import-file")
    .setInputFiles({
      name: "graph.json",
      mimeType: "application/json",
      buffer: Buffer.isBuffer(buffer) ? buffer : Buffer.from(buffer),
    });
  await page.waitForFunction(
    () => !document.querySelector("#import-button").disabled,
  );
}
async function ready(page) {
  await page.goto(BASE);
  await page.waitForFunction(
    () => document.querySelectorAll("#nodes .node").length === 8,
  );
}
async function solve(page) {
  await page.locator("#solve").click();
  await page.locator("#result-content").waitFor({ state: "visible" });
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({
      channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    await ready(page);
    let delayedFinished = false;
    await page.route("**/api/solve", async (route) => {
      const response = await route.fetch();
      await wait(1100);
      try {
        await route.fulfill({ response });
      } catch {
        /* Abort is the expected safe outcome. */
      }
      delayedFinished = true;
    });
    await page.locator("#solve").click();
    await page.locator("#target").selectOption("A");
    await wait(1400);
    check(
      "Late successful response cannot replace an edited graph",
      delayedFinished &&
        (await page.locator("#result-content").isHidden()) &&
        (await page.locator("#target").inputValue()) === "A",
    );
    check(
      "Editing cancels the busy state without trapping the main action",
      await page.locator("#solve").isEnabled(),
    );
    await page.unroute("**/api/solve");
    await solve(page);
    check(
      "A fresh computation succeeds after cancellation",
      (await page.locator("#result-cost").textContent()) === "3",
    );
    await page.route("**/api/solve", async (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: "Fallo de transporte simulado para verificar recuperación.",
        }),
      }),
    );
    await page.locator("#solve").click();
    await page.locator("#notice").waitFor({ state: "visible" });
    check(
      "A failed engine request displays its error and no old route",
      (await page.locator("#notice-text").textContent()).includes(
        "Fallo de transporte simulado",
      ) &&
        (await page.locator("#result-content").isHidden()) &&
        (await page.locator("#solve").isEnabled()),
    );
    await page.unroute("**/api/solve");
    await solve(page);
    check(
      "Retry recovers after a transport error",
      (await page.locator("#result-cost").textContent()) === "3",
    );
    await page.route("**/api/solve", async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          source: "S",
          target: "A",
          trace: [],
        }),
      }),
    );
    await page.locator("#solve").click();
    await page.locator("#notice").waitFor({ state: "visible" });
    check(
      "Malformed successful response shows a recoverable error",
      (await page.locator("#notice-text").textContent()).includes(
        "resultado incompleto",
      ) &&
        (await page.locator("#result-content").isHidden()) &&
        (await page.locator("#solve").isEnabled()),
    );
    await page.unroute("**/api/solve");
    await page.locator("#example").selectOption("desvio");
    const oneNode = {
      schema_version: 1,
      directed: false,
      nodes: [{ id: "X", label: "X", x: 100, y: 100 }],
      edges: [],
    };
    await page.route("**/api/validate", async (route) => {
      const response = await route.fetch();
      await wait(1000);
      await route.fulfill({ response });
    });
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "late.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(oneNode)),
      });
    await page.locator("#example").selectOption("cero");
    await page.waitForFunction(
      () => !document.querySelector("#import-button").disabled,
    );
    check(
      "Late import does not overwrite edits made while validation runs",
      (await page.locator('[data-node="X"]').count()) === 0 &&
        (await page.locator("#notice-text").textContent()).includes(
          "cambió durante la importación",
        ),
    );
    await page.unroute("**/api/validate");
    const before = await page.locator("#graph-count").textContent();
    await upload(page, Buffer.from([0x7b, 0xff, 0x7d]));
    check(
      "Invalid UTF-8 never silently mutates imported labels",
      (await page.locator("#notice-text").textContent()).includes("UTF-8") &&
        (await page.locator("#graph-count").textContent()) === before,
    );
    await upload(
      page,
      JSON.stringify({
        ...oneNode,
        nodes: Array.from({ length: 501 }, (_, index) => ({
          id: "N" + index,
          label: "N" + index,
          x: index,
          y: index,
        })),
      }),
    );
    check(
      "Oversized node count is rejected without changing the graph",
      (await page.locator("#graph-count").textContent()) === before,
      { message: await page.locator("#notice-text").textContent() },
    );
    await page.locator("#example").selectOption("desvio");
    const cameraBefore = await page.locator("#graph").getAttribute("viewBox");
    await page.locator("#zoom-in").click();
    const cameraZoom = await page.locator("#graph").getAttribute("viewBox");
    check(
      "Zoom changes the view without changing graph data",
      cameraBefore !== cameraZoom &&
        (await page.locator("#graph-count").textContent()).includes("8 nodos"),
    );
    await page.locator("#graph").focus();
    await page.keyboard.press("ArrowRight");
    check(
      "Focused canvas pans through keyboard",
      (await page.locator("#graph").getAttribute("viewBox")) !== cameraZoom,
    );
    await page.locator("#fit").click();
    check(
      "Center view restores the fitted camera",
      (await page.locator("#graph").getAttribute("viewBox")) === cameraBefore,
    );
    await page.locator("#tab-edit").focus();
    await page.keyboard.press("ArrowRight");
    check(
      "Tabs support arrow-key navigation",
      (await page.locator("#tab-result").getAttribute("aria-selected")) ===
        "true",
    );
    await page.keyboard.press("End");
    check(
      "Tabs support End navigation",
      (await page.locator("#tab-trace").getAttribute("aria-selected")) ===
        "true",
    );
    await page.locator("#file-menu-button").click();
    await page.locator("#export-button").focus();
    await page.keyboard.press("Escape");
    check(
      "Closing the file disclosure returns focus to its trigger",
      (await page.locator("#file-menu").isHidden()) &&
        (await page
          .locator("#file-menu-button")
          .evaluate((element) => element === document.activeElement)),
    );
    const cdp = await context.newCDPSession(page);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 720,
      height: 500,
      deviceScaleFactor: 2,
      mobile: false,
    });
    await page.locator("#tab-edit").click();
    check(
      "200 percent equivalent viewport reflows without horizontal overflow",
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      {
        CSS_viewport: "720 x 500",
        physical_capture: "1440 x 1000",
        scope:
          "Browser device emulation of the 200 percent layout; not an operating-system zoom claim.",
      },
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-200-percent-reflow.png"),
      fullPage: true,
    });
    await cdp.send("Emulation.clearDeviceMetricsOverride");
    await page.setViewportSize({ width: 1440, height: 1000 });
    const large = { schema_version: 1, directed: true, nodes: [], edges: [] };
    for (let index = 0; index < 500; index++)
      large.nodes.push({
        id: "N" + index,
        label: "N" + index,
        x: (index % 25) * 85,
        y: Math.floor(index / 25) * 85,
      });
    for (let index = 0; index < 500; index++)
      for (let offset = 1; offset <= 8; offset++)
        large.edges.push({
          id: "E" + large.edges.length,
          source: "N" + index,
          target: "N" + ((index + offset) % 500),
          weight: String(offset),
        });
    const startImport = performance.now();
    await upload(page, JSON.stringify(large));
    const importMilliseconds = performance.now() - startImport;
    check(
      "Maximum supported graph imports and renders every element",
      (await page.locator("#nodes .node").count()) === 500 &&
        (await page.locator("#edges .edge").count()) === 4000,
      { nodes: 500, edges: 4000, elapsed_ms: Math.round(importMilliseconds) },
    );
    await page.locator('#source').selectOption('N0');
    await page.locator('#target').selectOption('N499');
    const expected = await page.request
      .post(BASE + "api/solve", {
        data: { graph: large, source: "N0", target: "N499", trace: false },
      })
      .then((response) => response.json());
    const startSolve = performance.now();
    await solve(page);
    const solveMilliseconds = performance.now() - startSolve;
    check(
      "Maximum graph yields the same cost as the direct Python call",
      (await page.locator("#result-cost").textContent()) === expected.cost,
      {
        cost: expected.cost,
        elapsed_ms: Math.round(solveMilliseconds),
        settled: expected.stats.settled,
      },
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-large-graph.png"),
      fullPage: true,
    });
    await page.locator("#zoom-in").click();
    check(
      "Large-graph view remains interactive after solving",
      await page.locator("#zoom-in").isEnabled(),
    );
    await page.locator("#example").selectOption("desvio");
    await page.locator("#tab-edit").click();
    await context.close();
    const quotaContext = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
    await quotaContext.addInitScript(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key.startsWith("vertice.graph"))
          throw new DOMException("Quota fixture", "QuotaExceededError");
        return original.call(this, key, value);
      };
    });
    const quota = await quotaContext.newPage();
    quota.setDefaultTimeout(15000);
    await ready(quota);
    await quota.locator("#node-label").fill("Sin almacenamiento");
    await quota.locator("#node-submit").click();
    check(
      "Storage failure keeps edits available in memory",
      (await quota.locator("#nodes .node").count()) === 9 &&
        (await quota.locator("#save-status").textContent()).includes(
          "Sin guardar",
        ),
    );
    check(
      "Storage failure explicitly offers export recovery",
      (await quota.locator("#notice-text").textContent()).includes(
        "Exporta tu grafo",
      ),
    );
    await quota.locator("#file-menu-button").click();
    const [download] = await Promise.all([
      quota.waitForEvent("download"),
      quota.locator("#export-button").click(),
    ]);
    const exportPath = path.join(OUT, "quota-recovery-graph.json");
    await download.saveAs(exportPath);
    check(
      "Export preserves unsaved edits after a storage failure",
      JSON.parse(fs.readFileSync(exportPath, "utf8")).nodes.length === 9,
    );
    await quota.screenshot({
      path: path.join(CAPTURES, "sdv-storage-recovery.png"),
      fullPage: true,
    });
    await quotaContext.close();
  } catch (error) {
    evidence.error = error.stack || String(error);
    process.exitCode = 1;
  } finally {
    evidence.finished_at = new Date().toISOString();
    evidence.passed = evidence.checks.filter((item) => item.passed).length;
    evidence.failed =
      evidence.checks.filter((item) => !item.passed).length +
      (evidence.error ? 1 : 0);
    fs.writeFileSync(
      path.join(OUT, "adversarial.json"),
      JSON.stringify(evidence, null, 2) + "\n",
    );
    await browser?.close();
  }
  console.log(
    JSON.stringify({
      passed: evidence.passed,
      failed: evidence.failed,
      error: evidence.error || null,
    }),
  );
})();
