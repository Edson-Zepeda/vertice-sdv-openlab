/* Sustained, paced interaction with real Python engines. Every cycle performs actual UI work. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const evidenceName = process.env.SDV_SOAK_EVIDENCE || "soak";
if (!/^[a-z0-9_-]+$/i.test(evidenceName))
  throw new Error("Use a simple evidence directory name.");
const OUT = path.join(ROOT, "evidence", "ui", evidenceName);
const BASE = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
const MINUTES = Number(process.env.SDV_SOAK_MINUTES || 75);
if (!Number.isFinite(MINUTES) || MINUTES < 1 || MINUTES > 180)
  throw new Error("SDV_SOAK_MINUTES must be between 1 and 180.");
fs.mkdirSync(OUT, { recursive: true });
const started = Date.now();
const end = started + MINUTES * 60000;
const report = {
  started_at: new Date(started).toISOString(),
  requested_minutes: MINUTES,
  scope:
    "Paced UI endurance, real local Python and browser Pyodide; no idle-duration claim and no simulated successful solver results.",
  metric_scope:
    "CDP Performance metrics describe the main UI renderer. Worker/Wasm heap size is not directly measured; results do not assert a global process-memory leak proof.",
  code_hashes: {},
  phases: [],
  checkpoints: [],
  failures: [],
  actions: 0,
  cycles: 0,
  solves: 0,
  engine_modes: [],
  completed: false,
};
for (const name of [
  "web/app.js",
  "web/engine.js",
  "web/python-worker.js",
  "web/index.html",
  "web/style.css",
  "server.py",
  "vertice/__init__.py",
  "vertice/codec.py",
  "vertice/graph.py",
  "vertice/dijkstra.py",
  "web/python/manifest.json",
  "web/python/vertice/__init__.py",
  "web/python/vertice/codec.py",
  "web/python/vertice/graph.py",
  "web/python/vertice/dijkstra.py",
])
  report.code_hashes[name] = crypto
    .createHash("sha256")
    .update(fs.readFileSync(path.join(ROOT, name)))
    .digest("hex");
const journal = fs.createWriteStream(path.join(OUT, "activity.jsonl"));
const stopFile = path.join(OUT, "stop.flag");
let stopReason = null;
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => {
    stopReason = `Requested through ${signal}`;
  });
function stopIfRequested() {
  if (!stopReason && fs.existsSync(stopFile)) {
    stopReason =
      fs.readFileSync(stopFile, "utf8").trim().slice(0, 500) ||
      "Requested through stop.flag";
  }
  if (stopReason) {
    const error = new Error(stopReason);
    error.name = "GracefulStop";
    throw error;
  }
}
const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));
const latencies = [];
const phaseNames = [
  "local-editor-history",
  "browser-real-traces",
  "local-import-persistence",
  "browser-moderate-density",
  "local-mixed-session",
];
let actionCounter = 0,
  nextCheckpoint = started,
  currentPhase = -1;
function writeReport() {
  fs.writeFileSync(
    path.join(OUT, "report.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
}
async function action(name, perform, { pace = true } = {}) {
  stopIfRequested();
  const t = performance.now();
  await perform();
  report.actions++;
  journal.write(
    JSON.stringify({
      at: new Date().toISOString(),
      phase: phaseNames[currentPhase],
      action: name,
      elapsed_ms: Math.round(performance.now() - t),
      passed: true,
    }) + "\n",
  );
  if (pace) await sleep([1100, 1500, 2100][actionCounter++ % 3]);
  stopIfRequested();
}
function expect(value, message) {
  if (!value) throw new Error(message);
}
function graphForCycle(cycle) {
  const count = 90;
  const nodes = Array.from({ length: count }, (_, i) => ({
    id: "N" + i,
    label: i === 0 ? "Inicio " + cycle : "N" + i,
    x: (i % 15) * 90,
    y: Math.floor(i / 15) * 90,
  }));
  const edges = [];
  for (let i = 0; i < count; i++)
    for (let offset = 1; offset <= 3; offset++)
      edges.push({
        id: "E" + edges.length,
        source: "N" + i,
        target: "N" + ((i + offset) % count),
        weight: String(offset),
      });
  return { schema_version: 1, directed: true, nodes, edges };
}

(async () => {
  let browser, context, page, cdp;
  try {
    browser = await chromium.launch({
      channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
      headless: true,
    });
    context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    page = await context.newPage();
    page.setDefaultTimeout(30000);
    cdp = await context.newCDPSession(page);
    await cdp.send("Performance.enable");
    page.on("pageerror", (error) => {
      report.failures.push({
        at: new Date().toISOString(),
        kind: "pageerror",
        message: error.message,
      });
    });
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.querySelectorAll("#nodes .node").length === 8,
    );
    async function calculate(expected) {
      const start = performance.now();
      await page.locator("#solve").click();
      await page
        .locator("#result-content")
        .waitFor({ state: "visible", timeout: 65000 });
      const cost = await page.locator("#result-cost").textContent();
      if (expected !== undefined)
        expect(
          cost === expected,
          `Expected cost ${expected}, received ${cost}`,
        );
      latencies.push(performance.now() - start);
      report.solves++;
      const mode = await page.evaluate(() =>
        import("./engine.js").then((engine) => engine.engineStatus().mode),
      );
      expect(
        mode === ([1, 3].includes(currentPhase) ? "browser" : "local"),
        "Unexpected engine mode during phase",
      );
      return { cost, label: mode };
    }
    async function checkpoint() {
      await cdp.send("HeapProfiler.collectGarbage");
      const metrics = Object.fromEntries(
        (await cdp.send("Performance.getMetrics")).metrics.map((metric) => [
          metric.name,
          metric.value,
        ]),
      );
      const ordered = latencies.slice(-50).sort((a, b) => a - b);
      const checkpoint = {
        at: new Date().toISOString(),
        elapsed_minutes: +(Date.now() - started).toFixed(0) / 60000,
        phase: phaseNames[currentPhase],
        actions: report.actions,
        cycles: report.cycles,
        solves: report.solves,
        javascript_heap_bytes_after_gc: metrics.JSHeapUsedSize,
        dom_nodes: metrics.Nodes,
        live_elements: await page.evaluate(() => document.querySelectorAll('*').length),
        graph_nodes: await page.locator('#nodes .node').count(),
        graph_edges: await page.locator('#edges .edge').count(),
        documents: metrics.Documents,
        event_listeners: metrics.JSEventListeners,
        solve_last_50_median_ms: ordered.length
          ? Math.round(ordered[Math.floor(ordered.length / 2)])
          : null,
        solve_last_50_max_ms: ordered.length
          ? Math.round(ordered.at(-1))
          : null,
      };
      report.checkpoints.push(checkpoint);
      writeReport();
      console.log(JSON.stringify({ checkpoint }));
      nextCheckpoint = Date.now() + 5 * 60000;
    }
    while (Date.now() < end) {
      const phase = Math.min(
        4,
        Math.floor((Date.now() - started) / ((end - started) / 5)),
      );
      if (phase !== currentPhase) {
        currentPhase = phase;
        const browserMode = phase === 1 || phase === 3;
        await page.goto(BASE + (browserMode ? "?engine=browser" : ""));
        await page.locator("#example").selectOption("desvio");
        report.phases.push({
          name: phaseNames[phase],
          began_at: new Date().toISOString(),
          engine: browserMode
            ? "actual browser Pyodide"
            : "actual local Python",
        });
        report.engine_modes.push(browserMode ? "browser" : "local");
        writeReport();
      }
      const cycle = report.cycles++;
      if (phase === 0 || phase === 4) {
        await action("Open didactic graph", () =>
          page.locator("#example").selectOption("desvio"),
        );
        await action("Open node editor", async () => {
          await page.locator('[data-node="A"]').focus();
          await page.keyboard.press("Enter");
        });
        await action("Rename and move a node through form", async () => {
          await page.locator("#node-label").fill("Nodo A · sesión " + cycle);
          await page.locator("#node-x").fill(String(250 + (cycle % 30)));
          await page.locator("#node-submit").click();
        });
        await action("Undo the edit", () => page.locator("#undo").click());
        await action("Redo the edit", () => page.locator("#redo").click());
        await action("Compute with real Python after edit history", () =>
          calculate("11"),
        );
        await action("Explore actual initialization", () =>
          page.locator("#explore-trace").click(),
        );
        await action(
          "Advance actual settled and considered events",
          async () => {
            await page.locator("#next-step").click();
            await page.locator("#next-step").click();
          },
        );
        await action("Seek final trace event through keyboard", async () => {
          await page.locator("#step-slider").focus();
          await page.keyboard.press("End");
          expect(
            (await page.locator("#step-slider").inputValue()) ===
              (await page.locator("#step-slider").getAttribute("max")),
            "Slider lost its position",
          );
        });
        if (phase === 4 && cycle % 4 === 0)
          await action("Persist and reload edited graph", async () => {
            await page.reload();
            await page.locator("#solve").waitFor();
            expect(
              (await page.locator("#source").inputValue()) === "S",
              "Persistence lost source",
            );
          });
      } else if (phase === 1) {
        const id = ["desvio", "empate", "cero", "direccion", "malla"][
          cycle % 5
        ];
        await action("Change graph for browser Python", () =>
          page.locator("#example").selectOption(id),
        );
        await action("Compute with browser Pyodide", () => calculate());
        await action("Open actual Python trace", () =>
          page.locator("#explore-trace").click(),
        );
        await action("Run paced trace playback", async () => {
          await page.locator("#speed").selectOption("250");
          await page.locator("#play").click();
          await sleep(1800);
          await page.locator("#play").click();
        });
        await action("Inspect frontier table", async () => {
          expect(
            (await page.locator("#distance-rows tr").count()) > 0,
            "Frontier table disappeared",
          );
          await page.locator(".table-scroll").focus();
          await page.keyboard.press("ArrowDown");
        });
        await action("Seek to final event and back one event", async () => {
          await page.locator("#step-slider").focus();
          await page.keyboard.press("End");
          await page.locator("#previous-step").click();
        });
        await action("Inspect route and zoom", async () => {
          await page.locator("#tab-result").click();
          await page.locator("#zoom-in").click();
          await page.locator("#fit").click();
        });
      } else if (phase === 2) {
        await action(
          "Import canonical graph through Python validation",
          async () => {
            const graph = graphForCycle(cycle);
            await page
              .locator("#import-file")
              .setInputFiles({
                name: "session.json",
                mimeType: "application/json",
                buffer: Buffer.from(JSON.stringify(graph)),
              });
            await page.waitForFunction(
              () => !document.querySelector("#import-button").disabled,
            );
            expect(
              (await page.locator("#nodes .node").count()) === 90,
              "Import lost nodes",
            );
            await page.locator("#source").selectOption("N0");
            await page.locator("#target").selectOption("N89");
          },
        );
        await action("Compute imported graph", () => calculate("89"));
        await action("Export current graph as a real download", async () => {
          await page.locator("#file-menu-button").click();
          const [download] = await Promise.all([
            page.waitForEvent("download"),
            page.locator("#export-button").click(),
          ]);
          expect((await download.failure()) === null, "Export download failed");
        });
        await action("Reload persisted graph", async () => {
          await page.reload();
          await page.waitForFunction(
            () => document.querySelectorAll("#nodes .node").length === 90,
          );
        });
        await action("Compute after persistence restore", () =>
          calculate("89"),
        );
        await action("Modify endpoints then undo", async () => {
          await page.locator("#target").selectOption("N45");
          await page.locator("#undo").click();
          expect(
            (await page.locator("#target").inputValue()) === "N89",
            "Undo did not restore destination",
          );
        });
      } else {
        await action(
          "Import medium-density graph through browser Python",
          async () => {
            await page
              .locator("#import-file")
              .setInputFiles({
                name: "density.json",
                mimeType: "application/json",
                buffer: Buffer.from(JSON.stringify(graphForCycle(cycle))),
              });
            await page.waitForFunction(
              () => !document.querySelector("#import-button").disabled,
            );
            expect(
              (await page.locator("#edges .edge").count()) === 270,
              "Import lost edges",
            );
            await page.locator("#source").selectOption("N0");
            await page.locator("#target").selectOption("N89");
          },
        );
        await action("Run medium-density browser solve", () => calculate("89"));
        await action("Inspect trace at different positions", async () => {
          await page.locator("#explore-trace").click();
          await page.locator("#step-slider").focus();
          await page.keyboard.press("End");
          await page.keyboard.press("ArrowLeft");
        });
        await action("Change viewport to mobile portrait", async () => {
          await page.setViewportSize({ width: 390, height: 844 });
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
            "Mobile overflow during sustained use",
          );
        });
        await action("Zoom and recenter mobile graph", async () => {
          await page.locator("#zoom-in").click();
          await page.locator("#zoom-in").click();
          await page.locator("#fit").click();
        });
        await action("Restore desktop viewport", () =>
          page.setViewportSize({ width: 1440, height: 1000 }),
        );
        await action("Undo and redo imported graph", async () => {
          await page.locator("#undo").click();
          await page.locator("#redo").click();
          expect(
            (await page.locator("#nodes .node").count()) === 90,
            "History lost dense graph",
          );
        });
      }
      if (Date.now() >= nextCheckpoint) await checkpoint();
      if (report.failures.length)
        throw new Error("A browser runtime exception was observed.");
    }
    await checkpoint();
    report.completed = true;
  } catch (error) {
    if (error.name === "GracefulStop") {
      report.interrupted = true;
      report.interruption = {
        at: new Date().toISOString(),
        reason: error.message,
      };
      journal.write(
        JSON.stringify({
          at: report.interruption.at,
          phase: phaseNames[currentPhase],
          action: "Requested graceful stop",
          reason: error.message,
        }) + "\n",
      );
    } else {
      report.failures.push({
        at: new Date().toISOString(),
        kind: "test-failure",
        message: error.stack || String(error),
      });
      process.exitCode = 1;
    }
  } finally {
    report.finished_at = new Date().toISOString();
    report.elapsed_minutes = (Date.now() - started) / 60000;
    report.code_hashes_after = {};
    for (const name of Object.keys(report.code_hashes))
      report.code_hashes_after[name] = crypto
        .createHash("sha256")
        .update(fs.readFileSync(path.join(ROOT, name)))
        .digest("hex");
    writeReport();
    journal.end();
    await browser?.close();
  }
  console.log(
    JSON.stringify({
      completed: report.completed,
      minutes: report.elapsed_minutes,
      actions: report.actions,
      cycles: report.cycles,
      solves: report.solves,
      failures: report.failures,
    }),
  );
})();
