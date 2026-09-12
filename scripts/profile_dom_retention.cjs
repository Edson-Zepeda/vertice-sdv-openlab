/* Control experiment: distinguish native input/automation retention from graph rendering. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..");
const BASE = process.env.VERTICE_URL || "http://127.0.0.1:8770/";
const OUT = path.join(ROOT, "evidence", "ui", "dom-retention.json");
const report = {
  started_at: new Date().toISOString(),
  scope:
    "Small controlled comparison after the paced endurance run. CDP renderer metrics after forced GC; excludes direct worker heap measurement.",
  series: [],
};
async function metrics(page, cdp, cycle) {
  await cdp.send("HeapProfiler.collectGarbage");
  const result = Object.fromEntries(
    (await cdp.send("Performance.getMetrics")).metrics.map((item) => [
      item.name,
      item.value,
    ]),
  );
  return {
    cycle,
    heap: result.JSHeapUsedSize,
    cdp_nodes: result.Nodes,
    live_elements: await page.evaluate(
      () => document.querySelectorAll("*").length,
    ),
    documents: result.Documents,
    listeners: result.JSEventListeners,
  };
}
(async () => {
  const browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  try {
    for (const mode of [
      "native-form-control",
      "graph-render-only",
      "graph-form-edits",
    ]) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      if (mode === "native-form-control") {
        await page.route("**/__qa__/native.html", (route) =>
          route.fulfill({
            contentType: "text/html",
            body: '<!doctype html><html lang="es"><title>Control de campos nativos</title><body><label>Nombre<input id="name"></label><label>X<input id="x" type="number" value="250"></label><button id="save">Guardar</button><p id="label"></p><script>document.querySelector("#save").onclick=()=>{document.querySelector("#label").textContent=document.querySelector("#name").value;document.querySelector("#name").value=document.querySelector("#name").value;document.querySelector("#x").value=document.querySelector("#x").value;};</script></body></html>',
          }),
        );
        await page.goto(BASE + "__qa__/native.html");
      } else {
        await page.goto(BASE);
        await page.waitForFunction(
          () => document.querySelectorAll("#nodes .node").length === 8,
        );
      }
      const cdp = await context.newCDPSession(page);
      await cdp.send("Performance.enable");
      const series = { mode, observations: [await metrics(page, cdp, 0)] };
      report.series.push(series);
      for (let cycle = 1; cycle <= 50; cycle++) {
        if (mode === "native-form-control") {
          await page.locator("#name").fill("Nodo A · sesión " + cycle);
          await page.locator("#x").fill(String(250 + (cycle % 30)));
          await page.locator("#save").click();
        } else if (mode === "graph-render-only") {
          await page.locator("#solve").click();
          await page.locator("#result-content").waitFor({ state: "visible" });
          await page.locator("#explore-trace").click();
          await page.locator("#step-slider").focus();
          await page.keyboard.press("End");
        } else {
          await page.locator('[data-node="A"]').focus();
          await page.keyboard.press("Enter");
          await page.locator("#node-label").fill("Nodo A · sesión " + cycle);
          await page.locator("#node-x").fill(String(250 + (cycle % 30)));
          await page.locator("#node-submit").click();
        }
        if (cycle % 10 === 0)
          series.observations.push(await metrics(page, cdp, cycle));
      }
      await page.goto("about:blank");
      series.after_navigation = await metrics(page, cdp, 50);
      await context.close();
    }
  } catch (error) {
    report.error = error.stack || String(error);
    process.exitCode = 1;
  } finally {
    report.finished_at = new Date().toISOString();
    fs.writeFileSync(OUT, JSON.stringify(report, null, 2) + "\n");
    await browser.close();
  }
  console.log(JSON.stringify(report));
})();
