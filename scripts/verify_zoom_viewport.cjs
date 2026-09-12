/* Real pointer regression for SVG content escaping its viewport into controls. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const BASE = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
const PHASE = process.env.SDV_ZOOM_PHASE || "after";
if (!["before", "after"].includes(PHASE)) throw new Error("Use before or after.");
const OUT = path.join(ROOT, "evidence", "ui", "zoom-viewport");
fs.mkdirSync(OUT, { recursive: true });
const report = {
  started_at: new Date().toISOString(),
  phase: PHASE,
  scope: "Actual headless Chrome pointer clicks and hit testing; real Python import, solve and trace. No force clicks or synthetic event dispatch.",
  code_hashes: {},
  cases: [],
  checks: [],
  errors: [],
};
for (const file of ["web/style.css", "web/app.js", "web/index.html", "scripts/verify_zoom_viewport.cjs"])
  report.code_hashes[file] = crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT, file))).digest("hex");
if (PHASE === "before" && !fs.existsSync(path.join(OUT, "style-before.css")))
  fs.copyFileSync(path.join(ROOT, "web/style.css"), path.join(OUT, "style-before.css"));
function graph(count) {
  const nodes = Array.from({ length: count }, (_, i) => ({ id: "N" + i, label: "N" + i, x: (i % 15) * 90, y: Math.floor(i / 15) * 90 }));
  const edges = [];
  for (let i = 0; i < count; i++) for (let offset = 1; offset <= 3; offset++)
    edges.push({ id: "E" + edges.length, source: "N" + i, target: "N" + ((i + offset) % count), weight: String(offset) });
  return { schema_version: 1, directed: true, nodes, edges };
}
function check(caseName, name, passed, details = {}) {
  report.checks.push({ case: caseName, name, passed: !!passed, ...details });
  if (!passed) throw new Error(name);
}
async function viewBox(page) { return (await page.locator("#graph").getAttribute("viewBox")).split(/\s+/).map(Number); }
async function clickControl(page, caseName, id, ordinal) {
  const control = page.locator("#" + id);
  await control.scrollIntoViewIfNeeded();
  const hit = await control.evaluate((element) => {
    const r = element.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const front = document.elementFromPoint(x, y);
    return { owns_center: !!front && (front === element || element.contains(front)), x, y, front: front?.outerHTML.slice(0, 300) };
  });
  // Always attempt the same ordinary click, so the before evidence records the actual timeout.
  let error = null;
  try { await control.click({ timeout: 1800 }); } catch (caught) { error = caught.message; }
  check(caseName, `${id} pointer action ${ordinal}`, hit.owns_center && !error, { hit, error });
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || "chrome", headless: true });
  try {
    for (const width of [390, 768, 1440]) for (const count of [90, 150]) {
      const name = `${width}px-${count}nodes`, info = { name, width, nodes: count, passed: false };
      report.cases.push(info);
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      page.on("pageerror", (error) => report.errors.push({ case: name, message: error.message }));
      try {
        await page.goto(BASE + "?engine=browser");
        await page.waitForFunction(() => document.querySelectorAll("#nodes .node").length === 8);
        await page.locator("#import-file").setInputFiles({ name: name + ".json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(graph(count))) });
        await page.waitForFunction((expected) => document.querySelectorAll("#nodes .node").length === expected && !document.querySelector("#import-button").disabled, count, { timeout: 65000 });
        await page.locator("#source").selectOption("N0");
        await page.locator("#target").selectOption("N" + (count - 1));
        await page.locator("#solve").click();
        await page.locator("#result-content").waitFor({ state: "visible", timeout: 65000 });
        check(name, "Real browser Python returns expected route", await page.locator("#result-cost").textContent() === String(count - 1));
        await page.locator("#explore-trace").click();
        await page.locator("#step-slider").focus();
        await page.keyboard.press("End");
        await page.keyboard.press("ArrowLeft");
        await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 });
        await page.locator("#fit").click();
        const fitted = await viewBox(page);
        for (let i = 1; i <= 6; i++) {
          const previous = await viewBox(page);
          await clickControl(page, name, "zoom-in", i);
          check(name, `Zoom ${i} changes the camera`, (await viewBox(page))[2] < previous[2]);
        }
        for (const id of ["tool-add", "tool-connect", "tool-select"]) {
          await clickControl(page, name, id, 1);
          check(name, `${id} changes tool mode`, await page.locator("#" + id).getAttribute("aria-pressed") === "true");
        }
        // Sampling immediately outside the SVG proves graph geometry cannot intercept the toolbar,
        // reserved metadata, or lateral boundaries even when projected nodes lie beyond the viewBox.
        await page.locator("#graph").scrollIntoViewIfNeeded();
        const escaped = await page.evaluate(() => {
          const svg = document.querySelector("#graph"), r = svg.getBoundingClientRect(), hits = [];
          for (const ratio of [0.1, 0.3, 0.5, 0.7, 0.9]) {
            const x = r.left + r.width * ratio, y = r.top + r.height * ratio;
            for (const [px, py] of [[x, r.top - 2], [x, r.bottom + 2], [r.left - 2, y], [r.right + 2, y]]) {
              if (px < 0 || py < 0 || px >= innerWidth || py >= innerHeight) continue;
              const target = document.elementFromPoint(px, py);
              if (target && svg.contains(target)) hits.push({ x: px, y: py, target: target.outerHTML.slice(0, 200) });
            }
          }
          return hits;
        });
        check(name, "Graph hit testing is clipped to its viewport", escaped.length === 0, { escaped });
        await page.locator("#zoom-in").scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(OUT, `${PHASE}-${name}-zoomed.png`) });
        for (let i = 1; i <= 3; i++) {
          const previous = await viewBox(page);
          await clickControl(page, name, "zoom-out", i);
          check(name, `Zoom out ${i} changes the camera`, (await viewBox(page))[2] > previous[2]);
        }
        await clickControl(page, name, "fit", 1);
        check(name, "Center restores the fitted camera", JSON.stringify(await viewBox(page)) === JSON.stringify(fitted));
        // Resize back across the portrait breakpoint and repeat the exact failed two-click sequence.
        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.setViewportSize({ width: 390, height: 844 });
        await clickControl(page, name, "zoom-in", "resize-1");
        await clickControl(page, name, "zoom-in", "resize-2");
        await clickControl(page, name, "fit", "resize");
        check(name, "Viewport has no horizontal document overflow", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        info.passed = true;
      } catch (error) {
        info.error = error.message;
        await page.screenshot({ path: path.join(OUT, `${PHASE}-${name}-failure.png`) }).catch(() => {});
      } finally { await context.close(); }
    }
  } finally {
    await browser.close();
    report.finished_at = new Date().toISOString();
    report.passed = report.checks.filter((item) => item.passed).length;
    report.failed = report.checks.filter((item) => !item.passed).length;
    report.completed = report.cases.every((item) => item.passed) && !report.errors.length;
    fs.writeFileSync(path.join(OUT, PHASE + ".json"), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify({ phase: PHASE, cases: report.cases, passed: report.passed, failed: report.failed, errors: report.errors, completed: report.completed }));
    process.exitCode = report.completed ? 0 : 1;
  }
})();
