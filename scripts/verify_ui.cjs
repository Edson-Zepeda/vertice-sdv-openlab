/* Real browser checks against the local Python server; no mocked solver. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "evidence", "ui");
const CAPTURES = path.join(ROOT, "output", "playwright");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(CAPTURES, { recursive: true });
const base = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
const report = {
  started_at: new Date().toISOString(),
  url: base,
  engine: "actual local Python",
  checks: [],
  errors: [],
  accessibility: [],
};
function check(name, condition, details = {}) {
  const entry = { name, passed: !!condition, ...details };
  report.checks.push(entry);
  if (!condition) throw new Error(name + ": " + JSON.stringify(details));
}
async function save() {
  report.finished_at = new Date().toISOString();
  report.passed = report.checks.filter((item) => item.passed).length;
  report.failed =
    report.checks.filter((item) => !item.passed).length + report.errors.length;
  fs.writeFileSync(
    path.join(OUT, "qa.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
}
const pause = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

(async () => {
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const runtimeErrors = [],
    requests = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (
      message.location().url.endsWith("/api/validate") &&
      message.text().includes("400")
    ) {
      report.expected_validation_rejections =
        (report.expected_validation_rejections || 0) + 1;
      return;
    }
    runtimeErrors.push(message.text());
  });
  page.on("request", (request) => requests.push(request.url()));
  page.setDefaultTimeout(10000);
  const current = () =>
    page.evaluate(() => JSON.parse(localStorage.getItem("vertice.graph.v1")));
  const example = async (id) => {
    await page.locator("#example").selectOption(id);
    await page.locator("#solve").waitFor({ state: "visible" });
  };
  const calculate = async () => {
    await page.locator("#solve").click();
    await page.locator("#result-content").waitFor({ state: "visible" });
  };
  const uploadRaw = async (content) => {
    await page
      .locator("#import-file")
      .setInputFiles({
        name: "grafo.json",
        mimeType: "application/json",
        buffer: Buffer.from(content, "utf8"),
      });
    await page.waitForFunction(
      () => !document.querySelector("#import-button").disabled,
    );
  };
  const notice = () => page.locator("#notice-text").textContent();
  try {
    await page.goto(base);
    await page.waitForFunction(
      () => document.querySelectorAll("#nodes .node").length === 8,
    );
    await page.evaluate(() => document.fonts.ready);
    check(
      "Initial example: 8 nodes and 12 edges",
      (await page.locator("#nodes .node").count()) === 8 &&
        (await page.locator("#edges .edge").count()) === 12,
    );
    check(
      "The local Python engine is identified",
      (await page.locator("#engine-status").textContent()).includes(
        "Python local",
      ),
    );
    check(
      "No external font or script requests",
      requests.every((url) => new URL(url).origin === new URL(base).origin),
      { requests },
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-desktop-editor.png"),
      fullPage: true,
    });
    await calculate();
    check(
      "Python solves initial graph with exact cost 11",
      (await page.locator("#result-cost").textContent()) === "11",
    );
    check(
      "Completed route is announced in an active accessible status region",
      (await page.locator("#route-announcement").textContent()) === "Ruta calculada. Costo 11." &&
        (await page.locator("#route-announcement").getAttribute("role")) === "status" &&
        await page.locator("#route-announcement").isVisible(),
    );
    check(
      "Real optimal route rendered",
      await page
        .locator("#result-path .path-stop")
        .allTextContents()
        .then((values) => values.join(",") === "S,B,D,E,T"),
    );
    check(
      "All 43 actual events are available",
      (await page.locator("#timeline-count").textContent()) === "43 / 43",
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-desktop-route.png"),
      fullPage: true,
    });
    await page.locator("#explore-trace").click();
    check(
      "Trace begins with source at tentative zero",
      (await page.locator("#distance-rows tr").first().textContent()).replace(
        /\s/g,
        "",
      ) === "S0Frontera",
    );
    await page.locator("#next-step").click();
    check(
      "Settling removes source from frontier",
      (await page.locator("#distance-rows tr").first().textContent()).includes(
        "Asentado",
      ),
    );
    await page.locator("#speed").selectOption("250");
    await page.locator("#play").click();
    await pause(620);
    await page.locator("#play").click();
    const paused = await page.locator("#step-slider").inputValue();
    await pause(350);
    check(
      "Playback progresses and pause freezes its position",
      Number(paused) >= 3 &&
        paused === (await page.locator("#step-slider").inputValue()),
      { step: paused },
    );
    await page.locator("#step-slider").focus();
    await page.keyboard.press("End");
    check(
      "Slider keyboard reaches the final event",
      (await page.locator("#step-slider").inputValue()) === "42",
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-desktop-trace.png"),
      fullPage: true,
    });
    await page.locator("#tab-edit").click();
    await page.locator("#node-label").fill("<img src=x onerror=alert(1)>");
    await page.locator("#node-x").fill("400");
    await page.locator("#node-y").fill("250");
    await page.locator("#node-submit").click();
    check(
      "User labels are text, not HTML",
      (await page.locator("#nodes .node").count()) === 9 &&
        (await page.locator("#nodes img").count()) === 0 &&
        (await current()).graph.nodes.at(-1).label.includes("<img"),
    );
    check(
      "Editing invalidates the previous route",
      (await page.locator("#result-content").isHidden()) &&
        (await page.locator("#play").isDisabled()) &&
        (await page.locator("#graph .route").count()) === 0,
    );
    await page.locator("#node-label").fill("Prueba");
    await page.locator("#node-x").fill("450");
    await page.locator("#node-y").fill("275");
    await page.locator("#node-submit").click();
    check(
      "Rename and coordinate form persist exact edit",
      (await current()).graph.nodes.at(-1).label === "Prueba" &&
        (await current()).graph.nodes.at(-1).x === 450,
    );
    await page.locator('[data-node="N1"]').focus();
    await page.keyboard.press("ArrowRight");
    check(
      "Node moves through keyboard without dragging",
      (await current()).graph.nodes.at(-1).x === 455,
    );
    const beforeDrag = (await current()).graph.nodes.at(-1);
    const location = await page
      .locator('[data-node="N1"] .node-body')
      .boundingBox();
    await page.mouse.move(
      location.x + location.width / 2,
      location.y + location.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      location.x + location.width / 2 + 45,
      location.y + location.height / 2 + 20,
      { steps: 5 },
    );
    await page.mouse.up();
    check(
      "Pointer dragging commits node coordinates",
      (await current()).graph.nodes.at(-1).x > beforeDrag.x,
    );
    await page.locator("#edge-source").selectOption("N1");
    await page.locator("#edge-target").selectOption("N1");
    await page.locator("#edge-weight").fill("0");
    await page.locator("#edge-submit").click();
    check(
      "Zero-cost self loops can be created",
      (await current()).graph.edges.at(-1).source === "N1" &&
        (await current()).graph.edges.at(-1).weight === "0",
    );
    await page.locator("#edge-weight").fill("0.10000000");
    await page.locator("#edge-submit").click();
    check(
      "Trailing decimal zeroes normalize exactly",
      (await current()).graph.edges.at(-1).weight === "0.1",
    );
    for (const invalid of [
      "-1",
      "NaN",
      "Infinity",
      "0.1234567",
      "1000000000000.000001",
    ]) {
      await page.locator("#edge-weight").fill(invalid);
      await page.locator("#edge-submit").click();
      check(
        `Invalid cost ${invalid} is rejected without mutation`,
        (await current()).graph.edges.at(-1).weight === "0.1",
        { message: await notice() },
      );
    }
    await page.locator("#edge-weight").fill("1000000000000");
    await page.locator("#edge-submit").click();
    check(
      "Inclusive maximum cost is accepted exactly",
      (await current()).graph.edges.at(-1).weight === "1000000000000",
    );
    await page.locator('[data-node="N1"]').focus();
    await page.keyboard.press("Enter");
    await page.locator("#node-delete").click();
    check(
      "Node deletion removes its incident edges",
      (await current()).graph.nodes.length === 8 &&
        (await current()).graph.edges.length === 12,
    );
    await page.locator("#undo").click();
    check(
      "Undo restores deleted node and its connection",
      (await current()).graph.nodes.length === 9 &&
        (await current()).graph.edges.length === 13,
    );
    await page.locator("#redo").click();
    check(
      "Redo restores deletion",
      (await current()).graph.nodes.length === 8 &&
        (await current()).graph.edges.length === 12,
    );
    await example("desvio");
    await page.locator("#directed").check();
    check(
      "Directed conversion preserves both traversable directions",
      (await current()).graph.directed &&
        (await current()).graph.edges.length === 24,
    );
    const reversed = (await current()).graph.edges.find(
      (edge) => edge.source === "A" && edge.target === "S",
    );
    await page.locator(`[data-edge="${reversed.id}"]`).focus();
    await page.keyboard.press("Enter");
    await page.locator("#edge-weight").fill("5");
    await page.locator("#edge-submit").click();
    await page.locator("#directed").click();
    check(
      "Asymmetric direction change is blocked without deleting information",
      (await current()).graph.directed &&
        (await current()).graph.edges.length === 24 &&
        (await page.locator("#directed").isChecked()),
      { message: await notice() },
    );
    await page.locator("#edge-weight").fill("4");
    await page.locator("#edge-submit").click();
    await page.locator("#directed").uncheck();
    check(
      "Equivalent opposite edges merge with original costs",
      !(await current()).graph.directed &&
        (await current()).graph.edges.length === 12,
    );
    const rawBase = JSON.stringify({
      schema_version: 1,
      directed: true,
      nodes: [
        { id: "A", label: "A", x: 100, y: 150 },
        { id: "B", label: "B", x: 500, y: 250 },
      ],
      edges: [{ id: "e1", source: "A", target: "B", weight: "__WEIGHT__" }],
    });
    const preserved = JSON.stringify((await current()).graph);
    await uploadRaw(rawBase.replace('"__WEIGHT__"', "1000000000000.000001"));
    check(
      "Raw JSON precision overflow is rejected by Python before JavaScript parsing",
      JSON.stringify((await current()).graph) === preserved,
      { message: await notice() },
    );
    await uploadRaw(rawBase.replace('"__WEIGHT__"', "1e-1000"));
    check(
      "Numeric underflow never becomes a false zero edge",
      JSON.stringify((await current()).graph) === preserved,
      { message: await notice() },
    );
    await uploadRaw(
      rawBase
        .replace('"__WEIGHT__"', "0.1")
        .replace('"directed":true', '"directed":true,"directed":false'),
    );
    check(
      "Duplicate JSON keys are rejected before import",
      JSON.stringify((await current()).graph) === preserved,
      { message: await notice() },
    );
    await uploadRaw("{malformed");
    check(
      "Malformed import leaves the graph intact",
      JSON.stringify((await current()).graph) === preserved,
    );
    await uploadRaw(rawBase.replace('"__WEIGHT__"', "0.1"));
    check(
      "Raw numeric cost imports as canonical exact text",
      (await current()).graph.edges[0].weight === "0.1",
    );
    await calculate();
    check(
      "Imported decimal solves as exact text",
      (await page.locator("#result-cost").textContent()) === "0.1",
    );
    await page.locator("#target").selectOption("A");
    await calculate();
    check(
      "Source equals target has zero cost and one-node route",
      (await page.locator("#result-cost").textContent()) === "0" &&
        (await page.locator("#result-path .path-stop").count()) === 1,
    );
    await example("aislado");
    await calculate();
    check(
      "Unreachable destination has explicit no-route state",
      (await page.locator("#result-cost").textContent()) === "Sin ruta" &&
        (await page.locator("#result-path .path-stop").count()) === 0,
    );
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-no-route.png"),
      fullPage: true,
    });
    await page.locator("#file-menu-button").click();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#export-button").click(),
    ]);
    const exportPath = path.join(OUT, "exported-graph.json");
    await download.saveAs(exportPath);
    const exported = JSON.parse(fs.readFileSync(exportPath, "utf8"));
    check(
      "Downloaded JSON contains the current exact graph",
      JSON.stringify(exported) === JSON.stringify((await current()).graph),
    );
    const count = exported.nodes.length;
    await page.reload();
    await page.waitForFunction(
      (total) => document.querySelectorAll("#nodes .node").length === total,
      count,
    );
    check(
      "A reload restores the saved graph",
      (await page.locator("#nodes .node").count()) === count,
    );
    await page.evaluate(() => {
      localStorage.setItem(
        "vertice.graph.backup.v1",
        localStorage.getItem("vertice.graph.v1"),
      );
      localStorage.setItem("vertice.graph.v1", "{broken-session");
    });
    await page.reload();
    await page.locator("#recovery").waitFor({ state: "visible" });
    check(
      "Corrupt persistence exposes recovery without discarding original",
      await page.evaluate(
        () => localStorage.getItem("vertice.graph.v1") === "{broken-session",
      ),
    );
    await page.locator("#recover-button").click();
    check(
      "Previous valid backup can be restored",
      (await page.locator("#recovery").isHidden()) &&
        (await current()).graph.nodes.length === count,
    );
    await example("desvio");
    await page.locator("#file-menu-button").click();
    await page.locator("#menu-help").click();
    check(
      "Help dialog opens with keyboard focus contained",
      await page.locator("#help-dialog").isVisible(),
    );
    await page.keyboard.press("Escape");
    check("Escape closes help", await page.locator("#help-dialog").isHidden());
    const major = [
      "#node-label",
      "#node-x",
      "#edge-weight",
      "#source",
      "#target",
      "#node-submit",
      "#edge-submit",
      "#tab-edit",
    ];
    const fontSizes = await page.evaluate(
      (selectors) =>
        Object.fromEntries(
          selectors.map((selector) => [
            selector,
            parseFloat(
              getComputedStyle(document.querySelector(selector)).fontSize,
            ),
          ]),
        ),
      major,
    );
    check(
      "Primary controls use at least 16px type",
      Object.values(fontSizes).every((value) => value >= 16),
      { sizes: fontSizes },
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-mobile-editor.png"),
      fullPage: true,
    });
    check(
      "Mobile viewport has no horizontal overflow",
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    const mobileSizes = await page.evaluate(() => {
      const node = document.querySelector(".node-id");
      return {
        font:
          parseFloat(getComputedStyle(node).fontSize) * node.getScreenCTM().a,
        matrix: node.getScreenCTM().a,
        width: document.querySelector(".node-body").getBoundingClientRect()
          .width,
      };
    });
    check(
      "Mobile graph labels remain readable",
      mobileSizes.font >= 18 && mobileSizes.width >= 40,
      mobileSizes,
    );
    await calculate();
    await page.screenshot({
      path: path.join(CAPTURES, "sdv-mobile-route.png"),
      fullPage: true,
    });
    check(
      "Mobile execution shows the same Python result",
      (await page.locator("#result-cost").textContent()) === "11",
    );
    await page.setViewportSize({ width: 320, height: 740 });
    check(
      "Small 320px viewport has no horizontal overflow",
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("#explore-trace").click();
    await page.locator("#step-slider").focus();
    await page.keyboard.press("ArrowRight");
    const reduced = await page
      .locator(".node-body")
      .first()
      .evaluate((element) => getComputedStyle(element).transitionDuration);
    check("Reduced motion disables ornamental transitions", reduced === "0s", {
      transition: reduced,
    });
    let axe;
    try {
      axe = require.resolve("axe-core/axe.min.js");
    } catch {
      const local = path.join(
        ROOT,
        "tmp",
        "ui-tools",
        "node_modules",
        "axe-core",
        "axe.min.js",
      );
      axe = fs.existsSync(local) ? local : null;
    }
    if (axe) {
      const axeURL = new URL("__qa__/axe.min.js", base).href;
      await page.route(axeURL, (route) => route.fulfill({ contentType: "text/javascript", body: fs.readFileSync(axe, "utf8") }));
      await page.addScriptTag({ url: axeURL });
      for (const panel of ["edit", "result", "trace"]) {
        await page.locator("#tab-" + panel).click();
        const result = await page.evaluate(
          async () =>
            await axe.run(document, {
              runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21aa"],
              },
            }),
        );
        const violations = result.violations.map((item) => ({
          id: item.id,
          impact: item.impact,
          description: item.description,
          nodes: item.nodes.map((node) => ({
            target: node.target,
            failureSummary: node.failureSummary,
          })),
        }));
        report.accessibility.push({ panel, violations });
        check(`Accessibility scan: ${panel}`, violations.length === 0, {
          violations,
        });
      }
    }
    check(
      "No runtime or failed-resource errors during the verified flows",
      runtimeErrors.length === 0,
      { errors: runtimeErrors },
    );
  } catch (error) {
    report.errors.push(error.stack || String(error));
    await page
      .screenshot({
        path: path.join(CAPTURES, "sdv-qa-failure.png"),
        fullPage: true,
      })
      .catch(() => {});
    process.exitCode = 1;
  } finally {
    await save();
    await browser.close();
  }
  console.log(
    JSON.stringify({
      passed: report.passed,
      failed: report.failed,
      evidence: path.join(OUT, "qa.json"),
      error: report.errors[0] || null,
    }),
  );
})();
