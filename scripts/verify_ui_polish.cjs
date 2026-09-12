/* Focused regression checks for the final review findings; run before and after fixes. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..");
const BASE = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
const phase = process.env.SDV_POLISH_PHASE || "after";
const evidence = { at: new Date().toISOString(), phase, checks: [] };
function check(name, passed, details = {}) {
  evidence.checks.push({ name, passed: !!passed, ...details });
}
const pause = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));
(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.querySelectorAll("#nodes .node").length === 8,
    );
    await page.locator('[data-node="A"] .node-body').click();
    check(
      "A direct pointer click keeps the node selected for editing",
      (await page.locator("#node-label").inputValue()) === "A" &&
        (await page.locator("#node-delete").isVisible()),
    );
    const graph = {
      schema_version: 1,
      directed: false,
      nodes: [{ id: "LIMIT", label: "Límite exacto", x: 100, y: 100 }],
      edges: [],
    };
    const json = JSON.stringify(graph);
    const limit = 2 * 1024 * 1024;
    const exact = Buffer.concat([
      Buffer.from(json, "utf8"),
      Buffer.from(" ".repeat(limit - Buffer.byteLength(json, "utf8"))),
    ]);
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "exact-limit.json",
        mimeType: "application/json",
        buffer: exact,
      });
    await page.waitForFunction(
      () => !document.querySelector("#import-button").disabled,
    );
    check(
      "A valid graph at exactly 2 MiB imports through Python",
      (await page.locator('[data-node="LIMIT"]').count()) === 1,
      {
        bytes: exact.length,
        message: await page.locator("#notice-text").textContent(),
      },
    );
    const before = await page.locator("#graph-count").textContent();
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "over-limit.json",
        mimeType: "application/json",
        buffer: Buffer.concat([exact, Buffer.from(" ")]),
      });
    await page.waitForFunction(
      () => !document.querySelector("#import-button").disabled,
    );
    check(
      "A graph exceeding 2 MiB is rejected without changing data",
      (await page.locator("#graph-count").textContent()) === before &&
        (await page.locator("#notice-text").textContent()).includes("2 MiB"),
      {
        bytes: exact.length + 1,
        message: await page.locator("#notice-text").textContent(),
      },
    );
    await page.locator("#example").selectOption("desvio");
    await page.locator("#tab-edit").click();
    for (const [name, label, valid] of [
      ["empty label", "", true],
      ["only spaces", "   ", true],
      ["preserved outer spaces", "  Punto A  ", true],
      ["80 Unicode emoji", "🧭".repeat(80), true],
      ["81 ASCII characters", "A".repeat(81), false],
      ["81 Unicode emoji", "🧭".repeat(81), false],
      ["C0 control", "A\u0001", false],
      ["C1 control", "A\u0085", false],
      ["unpaired surrogate", "A\ud800", false],
    ]) {
      await page.locator('[data-node="A"]').focus();
      await page.keyboard.press("Enter");
      const storedBefore = await page.evaluate(
        () =>
          JSON.parse(localStorage.getItem("vertice.graph.v1")).graph.nodes.find(
            (node) => node.id === "A",
          ).label,
      );
      if (name === "unpaired surrogate")
        await page.locator("#node-label").evaluate((input) => {
          input.value = "A" + String.fromCharCode(0xd800);
        });
      else await page.locator("#node-label").fill(label);
      await page.locator("#node-submit").click();
      const storedAfter = await page.evaluate(
        () =>
          JSON.parse(localStorage.getItem("vertice.graph.v1")).graph.nodes.find(
            (node) => node.id === "A",
          ).label,
      );
      check(
        `Manual label: ${name} ${valid ? "preserved exactly" : "rejected without changing graph"}`,
        valid
          ? storedAfter === label
          : storedAfter === storedBefore &&
              (await page.locator("#notice").isVisible()),
        {
          stored_code_points: [...storedAfter].length,
          notice: await page.locator("#notice-text").textContent(),
        },
      );
    }
    const omitted = {
      schema_version: 1,
      directed: false,
      nodes: [{ id: "MISSING", x: 0, y: 0 }],
      edges: [],
    };
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "omitted-label.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(omitted)),
      });
    await page.waitForFunction(
      () => !document.querySelector("#import-button").disabled,
    );
    const missingNode = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("vertice.graph.v1")).graph.nodes.find(
        (node) => node.id === "MISSING",
      ),
    );
    check(
      "Omitted optional label canonicalizes to empty text and displays its ID",
      missingNode?.label === "" &&
        (await page.locator("#source option").textContent()) === "MISSING",
    );
    await page.locator("#example").selectOption("desvio");
    await page.locator("#tab-edit").click();
    await page.locator(".graph-list summary").click();
    await page
      .getByRole("button", { name: "Editar nodo A, A", exact: true })
      .focus();
    await page.keyboard.press("Enter");
    check(
      "Keyboard selection from node list moves focus to node form",
      await page
        .locator("#node-label")
        .evaluate((element) => element === document.activeElement),
    );
    await page
      .getByRole("button", {
        name: "Editar conexión S a A, costo 4",
        exact: true,
      })
      .focus();
    await page.keyboard.press("Enter");
    check(
      "Keyboard selection from edge list moves focus to edge form",
      await page
        .locator("#edge-weight")
        .evaluate((element) => element === document.activeElement),
    );
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await pause(100);
      const bounds = await page.evaluate(() => {
        const graph = document.querySelector("#graph").getBoundingClientRect();
        const meta = document
          .querySelector(".canvas-meta")
          .getBoundingClientRect();
        return {
          graph_bottom: graph.bottom,
          metadata_top: meta.top,
          reserved_pixels: meta.top - graph.bottom,
        };
      });
      check(
        `Metadata has its own area outside the SVG at ${width}px`,
        bounds.graph_bottom <= bounds.metadata_top,
        bounds,
      );
      await page.screenshot({
        path: path.join(
          ROOT,
          "output",
          "playwright",
          `sdv-polish-${phase}-${width}.png`,
        ),
        fullPage: true,
      });
    }
    await context.close();
  } catch (error) {
    evidence.error = error.stack || String(error);
  } finally {
    evidence.passed = evidence.checks.filter((check) => check.passed).length;
    evidence.failed =
      evidence.checks.filter((check) => !check.passed).length +
      (evidence.error ? 1 : 0);
    fs.writeFileSync(
      path.join(ROOT, "evidence", "ui", `polish-${phase}.json`),
      JSON.stringify(evidence, null, 2) + "\n",
    );
    await browser.close();
  }
  console.log(JSON.stringify(evidence));
  if (evidence.failed) process.exitCode = 1;
})();
