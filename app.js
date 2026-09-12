import { solveGraph, normalizeGraphJSON, engineStatus } from "./engine.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const STORE = "vertice.graph.v1";
const BACKUP = "vertice.graph.backup.v1";
const clone = (value) => structuredClone(value);
const blank = () => ({
  schema_version: 1,
  directed: false,
  nodes: [],
  edges: [],
});
const model = {
  graph: blank(),
  source: "",
  target: "",
  selection: null,
  tool: "select",
  connectSource: null,
  examples: [],
  undo: [],
  redo: [],
  result: null,
  frame: -1,
  playing: false,
  timer: null,
  request: 0,
  controller: null,
  busy: false,
  dragging: null,
  camera: { x: 0, y: 0, width: 1000, height: 600 },
  persisted: true,
  recoveryRaw: null,
  backup: null,
};
const graphSvg = $("graph");
let portrait = matchMedia("(max-width: 600px)").matches;
const projectPoint = (node) =>
  portrait ? { ...node, x: node.y, y: node.x } : node;
function graphScale() {
  const rect = graphSvg.getBoundingClientRect();
  return (
    Math.min(
      rect.width / model.camera.width,
      rect.height / model.camera.height,
    ) || 1
  );
}

function nodeName(id) {
  const node = model.graph.nodes.find((value) => value.id === id);
  return node?.label.trim() ? node.label : id;
}
function idToken(value) {
  return /^[A-Za-z0-9_-]{1,40}$/.test(value);
}
function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function canonicalWeight(value) {
  if (typeof value !== "string")
    throw new Error(
      "Guarda cada costo como texto decimal para conservar su precisión.",
    );
  const original = value.trim();
  const text = original.includes(".")
    ? original.replace(/0+$/, "").replace(/\.$/, "")
    : original;
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(text))
    throw new Error(
      "Usa un costo desde 0, con punto decimal y hasta 6 decimales.",
    );
  const [integer, fraction = ""] = text.split(".");
  if (
    BigInt(integer) * 1000000n + BigInt(fraction.padEnd(6, "0")) >
    1000000000000000000n
  )
    throw new Error("El costo máximo es 1 000 000 000 000.");
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
}
function validateGraph(value) {
  if (
    !object(value) ||
    value.schema_version !== 1 ||
    typeof value.directed !== "boolean" ||
    !Array.isArray(value.nodes) ||
    !Array.isArray(value.edges)
  )
    throw new Error(
      "El archivo debe incluir schema_version: 1, directed, nodes y edges.",
    );
  if (value.nodes.length > 500 || value.edges.length > 4000)
    throw new Error("El límite es 500 nodos y 4 000 conexiones.");
  const ids = new Set();
  const nodes = value.nodes.map((node) => {
    if (
      !object(node) ||
      typeof node.id !== "string" ||
      !idToken(node.id) ||
      ids.has(node.id)
    )
      throw new Error(
        "Cada nodo necesita un ID único de hasta 40 letras, números, guiones o guiones bajos.",
      );
    if (typeof node.label !== "string" || [...node.label].length > 80)
      throw new Error(
        `El nombre de ${node.id} debe ser texto de hasta 80 caracteres.`,
      );
    if (/[\u0000-\u001F\u007F-\u009F\uD800-\uDFFF]/u.test(node.label))
      throw new Error(
        `El nombre de ${node.id} no admite caracteres de control ni Unicode inválido.`,
      );
    for (const axis of ["x", "y"])
      if (
        typeof node[axis] !== "number" ||
        !Number.isFinite(node[axis]) ||
        Math.abs(node[axis]) > 10000
      )
        throw new Error(
          `La posición ${axis.toUpperCase()} de ${node.id} debe estar entre −10 000 y 10 000.`,
        );
    ids.add(node.id);
    return { id: node.id, label: node.label, x: node.x, y: node.y };
  });
  const edgeIds = new Set();
  const pairs = new Set();
  const edges = value.edges.map((edge) => {
    if (
      !object(edge) ||
      typeof edge.id !== "string" ||
      !idToken(edge.id) ||
      edgeIds.has(edge.id)
    )
      throw new Error("Cada conexión necesita un ID único válido.");
    if (!ids.has(edge.source) || !ids.has(edge.target))
      throw new Error(
        `La conexión ${edge.id} refiere a un nodo que no existe.`,
      );
    const pair = JSON.stringify(
      value.directed
        ? [edge.source, edge.target]
        : [edge.source, edge.target].sort(),
    );
    if (pairs.has(pair))
      throw new Error(
        "Ya existe una conexión entre esos nodos en esa dirección.",
      );
    pairs.add(pair);
    edgeIds.add(edge.id);
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      weight: canonicalWeight(edge.weight),
    };
  });
  return { schema_version: 1, directed: value.directed, nodes, edges };
}
function snapshot() {
  return {
    graph: clone(model.graph),
    source: model.source,
    target: model.target,
  };
}
function notify(text, tone = "error") {
  $("notice-text").textContent = text;
  $("notice").dataset.tone = tone;
  $("notice").hidden = false;
}
function clearNotice() {
  $("notice").hidden = true;
}
function pause() {
  model.playing = false;
  clearTimeout(model.timer);
  model.timer = null;
  renderPlayback();
}
function invalidate() {
  $("route-announcement").textContent = "";
  model.request += 1;
  model.controller?.abort();
  model.controller = null;
  model.busy = false;
  pause();
  model.result = null;
  model.frame = -1;
}
function validEndpoints() {
  const ids = new Set(model.graph.nodes.map((node) => node.id));
  if (!ids.has(model.source)) model.source = model.graph.nodes[0]?.id || "";
  if (!ids.has(model.target)) model.target = model.graph.nodes.at(-1)?.id || "";
}
function persist() {
  try {
    const before = localStorage.getItem(STORE);
    if (before) {
      try {
        const parsed = JSON.parse(before);
        validateGraph(parsed.graph);
        localStorage.setItem(BACKUP, before);
      } catch {
        localStorage.setItem(`${STORE}.recovery`, before);
      }
    }
    localStorage.setItem(
      STORE,
      JSON.stringify({
        version: 1,
        ...snapshot(),
        saved_at: new Date().toISOString(),
      }),
    );
    model.persisted = true;
  } catch {
    model.persisted = false;
    notify("El navegador no pudo guardar. Exporta tu grafo para conservarlo.");
  }
  $("save-status").textContent = model.persisted
    ? "Guardado en este equipo"
    : "Sin guardar · exporta una copia";
}
function commit(next, { message = "", fit = false, selected = null } = {}) {
  const verified = validateGraph(next.graph);
  model.undo.push(snapshot());
  if (model.undo.length > 60) model.undo.shift();
  model.redo = [];
  invalidate();
  model.graph = verified;
  model.source = next.source ?? model.source;
  model.target = next.target ?? model.target;
  model.selection = selected;
  model.connectSource = null;
  validEndpoints();
  $("example").value = "";
  if (fit) fitGraph();
  persist();
  render();
  if (message && model.persisted) notify(message, "success");
}
function edit(mutator, options = {}) {
  try {
    const next = snapshot();
    mutator(next);
    commit(next, options);
  } catch (error) {
    notify(error.message);
  }
}
function uniqueId(prefix, used) {
  let index = 1;
  while (used.has(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}
function addNode(label, x, y) {
  const id = uniqueId("N", new Set(model.graph.nodes.map((node) => node.id)));
  edit(
    (next) => {
      next.graph.nodes.push({ id, label, x, y });
    },
    { selected: { type: "node", id } },
  );
  tab("edit");
  return id;
}
function removeSelection(type) {
  if (model.selection?.type !== type) return;
  const id = model.selection.id;
  edit(
    (next) => {
      if (type === "node") {
        next.graph.nodes = next.graph.nodes.filter((node) => node.id !== id);
        next.graph.edges = next.graph.edges.filter(
          (edge) => edge.source !== id && edge.target !== id,
        );
      } else
        next.graph.edges = next.graph.edges.filter((edge) => edge.id !== id);
    },
    {
      message:
        type === "node"
          ? "Nodo y conexiones eliminados. Puedes deshacer."
          : "Conexión eliminada. Puedes deshacer.",
    },
  );
}
function history(direction) {
  const origin = direction === "undo" ? model.undo : model.redo;
  const destination = direction === "undo" ? model.redo : model.undo;
  if (!origin.length) return;
  destination.push(snapshot());
  const previous = origin.pop();
  invalidate();
  Object.assign(model, previous);
  model.selection = null;
  model.connectSource = null;
  validEndpoints();
  fitGraph();
  clearNotice();
  persist();
  render();
}
function select(type, id) {
  model.selection = { type, id };
  tab("edit");
  renderEditor();
  renderGraph();
}
function tab(name, { redraw = true } = {}) {
  model.panel = name;
  for (const key of ["edit", "result", "trace"]) {
    $("tab-" + key).setAttribute("aria-selected", String(key === name));
    $("tab-" + key).tabIndex = key === name ? 0 : -1;
    $("panel-" + key).hidden = key !== name;
  }
  if (redraw) renderGraph();
}
function setTool(tool) {
  model.tool = tool;
  model.connectSource = null;
  graphSvg.dataset.tool = tool;
  for (const value of ["select", "connect", "add"])
    $("tool-" + value).setAttribute("aria-pressed", String(value === tool));
  $("canvas-hint").textContent =
    tool === "connect"
      ? "Elige el primer nodo y después el segundo."
      : tool === "add"
        ? "Toca el lienzo para añadir un nodo."
        : "Selecciona un nodo o una conexión para editar.";
  renderGraph();
}
function optionList(selectElement, selected = "") {
  const fragment = document.createDocumentFragment();
  if (!model.graph.nodes.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Sin nodos";
    fragment.append(option);
  }
  for (const node of model.graph.nodes) {
    const option = document.createElement("option");
    option.value = node.id;
    option.textContent =
      nodeName(node.id) === node.id ? node.id : `${node.label} · ${node.id}`;
    fragment.append(option);
  }
  selectElement.replaceChildren(fragment);
  if (model.graph.nodes.some((node) => node.id === selected))
    selectElement.value = selected;
}
function renderEditor() {
  const selectedNode =
    model.selection?.type === "node"
      ? model.graph.nodes.find((node) => node.id === model.selection.id)
      : null;
  const selectedEdge =
    model.selection?.type === "edge"
      ? model.graph.edges.find((edge) => edge.id === model.selection.id)
      : null;
  $("clear-selection").hidden = !selectedNode && !selectedEdge;
  $("selection-type").textContent = selectedNode
    ? `NODO / ${selectedNode.id}`
    : selectedEdge
      ? `CONEXIÓN / ${selectedEdge.id}`
      : "EDITOR";
  $("selection-title").textContent = selectedNode
    ? nodeName(selectedNode.id)
    : selectedEdge
      ? `${selectedEdge.source} ${model.graph.directed ? "→" : "—"} ${selectedEdge.target}`
      : "Añadir nodo";
  $("node-label").value = selectedNode?.label || "";
  $("node-x").value =
    selectedNode?.x ??
    Math.round(
      portrait
        ? model.camera.y + model.camera.height / 2
        : model.camera.x + model.camera.width / 2,
    );
  $("node-y").value =
    selectedNode?.y ??
    Math.round(
      portrait
        ? model.camera.x + model.camera.width / 2
        : model.camera.y + model.camera.height / 2,
    );
  $("node-submit").textContent = selectedNode
    ? "Guardar nodo"
    : "Añadir nodo ＋";
  $("node-delete").hidden = !selectedNode;
  optionList(
    $("edge-source"),
    selectedEdge?.source || selectedNode?.id || model.source,
  );
  optionList($("edge-target"), selectedEdge?.target || model.target);
  $("edge-weight").value = selectedEdge?.weight ?? "1";
  $("edge-submit").textContent = selectedEdge
    ? "Guardar conexión"
    : "Conectar ↗";
  $("edge-delete").hidden = !selectedEdge;
  $("edge-submit").disabled = !model.graph.nodes.length;
  renderElementList();
}
function renderElementList() {
  if (!document.querySelector(".graph-list").open) {
    $("element-list").replaceChildren();
    return;
  }
  const list = document.createDocumentFragment();
  for (const node of model.graph.nodes) {
    const button = document.createElement("button");
    button.className = "list-item";
    button.type = "button";
    const id = document.createElement("span");
    id.className = "list-id";
    id.textContent = node.id;
    const label = document.createElement("span");
    label.textContent = nodeName(node.id);
    button.append(id, label);
    button.setAttribute(
      "aria-label",
      `Editar nodo ${nodeName(node.id)}, ${node.id}`,
    );
    button.addEventListener("click", () => {
      select("node", node.id);
      $("node-label").focus();
    });
    list.append(button);
  }
  for (const edge of model.graph.edges) {
    const button = document.createElement("button");
    button.className = "list-item";
    button.type = "button";
    const label = document.createElement("span");
    label.textContent = `${edge.source} ${model.graph.directed ? "→" : "—"} ${edge.target}`;
    const detail = document.createElement("span");
    detail.className = "list-detail";
    detail.textContent = `costo ${edge.weight}`;
    button.append(label, detail);
    button.setAttribute(
      "aria-label",
      `Editar conexión ${edge.source} a ${edge.target}, costo ${edge.weight}`,
    );
    button.addEventListener("click", () => {
      select("edge", edge.id);
      $("edge-weight").focus();
    });
    list.append(button);
  }
  $("element-list").replaceChildren(list);
}
function svgElement(name, attributes = {}, text = null) {
  const element = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes))
    element.setAttribute(key, value);
  if (text !== null) element.textContent = text;
  return element;
}
function fitGraph() {
  if (!model.graph.nodes.length)
    model.camera = { x: 0, y: 0, width: 1000, height: 600 };
  else {
    const projected = model.graph.nodes.map(projectPoint);
    const xs = projected.map((node) => node.x),
      ys = projected.map((node) => node.y);
    const width = Math.max(
        portrait ? 400 : 550,
        Math.max(...xs) - Math.min(...xs) + (portrait ? 170 : 220),
      ),
      height = Math.max(
        360,
        Math.max(...ys) - Math.min(...ys) + (portrait ? 300 : 200),
      );
    model.camera = {
      x: (Math.min(...xs) + Math.max(...xs) - width) / 2,
      y: (Math.min(...ys) + Math.max(...ys) - height) / 2,
      width,
      height,
    };
    if (portrait) model.camera.y = Math.min(...ys) - 100;
  }
  applyCamera();
}
function applyCamera() {
  const { x, y, width, height } = model.camera;
  graphSvg.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);
  for (const [key, value] of Object.entries({ x, y, width, height }))
    $("grid-rect").setAttribute(key, value);
}
function traceState() {
  const distances = new Map(),
    settled = new Set();
  let current = null,
    activeEdge = null;
  if (!model.result || model.frame < 0)
    return { distances, settled, current, activeEdge, finished: false };
  distances.set(model.result.source, "0");
  for (let index = 0; index <= model.frame; index += 1) {
    const event = model.result.trace[index];
    if (!event) break;
    current = event;
    activeEdge = event.edge || null;
    if (event.kind === "settle") {
      settled.add(event.node);
      if (event.cost !== undefined) distances.set(event.node, event.cost);
    }
    if (event.kind === "relax") distances.set(event.target, event.new_cost);
  }
  return {
    distances,
    settled,
    current,
    activeEdge,
    finished: model.frame === model.result.trace.length - 1,
  };
}
function edgeGeometry(edge, nodes, directions, radius) {
  const a = nodes.get(edge.source),
    b = nodes.get(edge.target);
  if (a.id === b.id)
    return {
      d: `M ${a.x - 18} ${a.y - 24} C ${a.x - 80} ${a.y - 130}, ${a.x + 80} ${a.y - 130}, ${a.x + 18} ${a.y - 24}`,
      x: a.x,
      y: a.y - 103,
    };
  const dx = b.x - a.x,
    dy = b.y - a.y,
    length = Math.hypot(dx, dy) || 1,
    ux = dx / length,
    uy = dy / length;
  const opposite =
    model.graph.directed &&
    directions.has(JSON.stringify([edge.target, edge.source]));
  const offset = opposite ? 35 : 0;
  const cx = (a.x + b.x) / 2 - uy * offset,
    cy = (a.y + b.y) / 2 + ux * offset;
  const adx = cx - a.x,
    ady = cy - a.y,
    al = Math.hypot(adx, ady) || 1;
  const bdx = cx - b.x,
    bdy = cy - b.y,
    bl = Math.hypot(bdx, bdy) || 1;
  const startX = a.x + (adx / al) * (radius + 3),
    startY = a.y + (ady / al) * (radius + 3),
    endX = b.x + (bdx / bl) * (radius + (model.graph.directed ? 9 : 3)),
    endY = b.y + (bdy / bl) * (radius + (model.graph.directed ? 9 : 3));
  return {
    d: `M ${startX} ${startY} Q ${cx} ${cy} ${endX} ${endY}`,
    x: 0.25 * startX + 0.5 * cx + 0.25 * endX,
    y: 0.25 * startY + 0.5 * cy + 0.25 * endY,
  };
}
function renderGraph() {
  const trace = traceState(),
    positions = new Map(
      model.graph.nodes.map((node) => [node.id, projectPoint(node)]),
    );
  const scale = graphScale();
  const readable = Math.min(2.5, Math.max(1, 1 / scale));
  const dense = model.graph.nodes.length > 100;
  const radius = dense
    ? Math.max(10, Math.min(30, 10 * readable))
    : Math.max(30, 22 * readable);
  graphSvg.classList.toggle("dense", dense);
  const directions = new Set(
    model.graph.edges.map((edge) => JSON.stringify([edge.source, edge.target])),
  );
  const routeNodes = new Set(trace.finished ? model.result?.path : []),
    routeEdges = new Set(trace.finished ? model.result?.edge_path : []);
  const edgeFragment = document.createDocumentFragment();
  for (const edge of model.graph.edges) {
    const geometry = edgeGeometry(edge, positions, directions, radius);
    const classes = [
      "edge",
      model.selection?.id === edge.id && model.selection?.type === "edge"
        ? "selected"
        : "",
      routeEdges.has(edge.id) ? "route" : "",
      !trace.finished && trace.activeEdge === edge.id ? "active" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const group = svgElement("g", {
      class: classes,
      tabindex: 0,
      role: "button",
      "data-edge": edge.id,
      "aria-label": `Conexión ${nodeName(edge.source)} a ${nodeName(edge.target)}, costo ${edge.weight}. Enter para editar.`,
    });
    const hit = svgElement("path", { d: geometry.d, class: "edge-hit" });
    const line = svgElement("path", { d: geometry.d, class: "edge-line" });
    if (model.graph.directed) line.setAttribute("marker-end", "url(#arrow)");
    const width = Math.max(34, edge.weight.length * 9 + 16) * readable;
    const background = svgElement("rect", {
      x: geometry.x - width / 2,
      y: geometry.y - 12 * readable,
      width,
      height: 24 * readable,
      rx: 7 * readable,
      class: "edge-label-bg",
    });
    const label = svgElement(
      "text",
      {
        x: geometry.x,
        y: geometry.y,
        class: "edge-label",
        style: `font-size:${16 * readable}px`,
      },
      edge.weight,
    );
    group.append(hit, line);
    if (
      model.graph.edges.length <= 150 ||
      classes.includes("selected") ||
      classes.includes("route") ||
      classes.includes("active")
    )
      group.append(background, label);
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      select("edge", edge.id);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select("edge", edge.id);
        focusGraphElement("edge", edge.id);
      }
    });
    edgeFragment.append(group);
  }
  $("edges").replaceChildren(edgeFragment);
  const nodeFragment = document.createDocumentFragment();
  for (const node of model.graph.nodes) {
    const classes = [
      "node",
      model.selection?.id === node.id && model.selection?.type === "node"
        ? "selected"
        : "",
      node.id === model.source ? "start" : "",
      node.id === model.target ? "target" : "",
      routeNodes.has(node.id)
        ? "route"
        : trace.settled.has(node.id)
          ? "settled"
          : trace.distances.has(node.id)
            ? "frontier"
            : "",
      model.connectSource === node.id ? "connect-source" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const projected = projectPoint(node);
    const group = svgElement("g", {
      class: classes,
      transform: `translate(${projected.x} ${projected.y})`,
      tabindex: 0,
      role: "button",
      "data-node": node.id,
      "aria-label": `Nodo ${nodeName(node.id)}, ${node.id}${node.id === model.source ? ", inicio" : ""}${node.id === model.target ? ", destino" : ""}. Enter para seleccionar; flechas para mover.`,
    });
    const showText = !dense || scale >= 0.65 || classes.includes("selected");
    group.append(
      svgElement("circle", { r: radius + 8 * readable, class: "node-halo" }),
      svgElement("circle", { r: radius, class: "node-body" }),
    );
    if (showText)
      group.append(
        svgElement(
          "text",
          {
            x: 0,
            y: 1,
            class: "node-id",
            style: `font-size:${(node.id.length > 4 ? 12 : 20) * readable}px`,
          },
          node.id.length > 6 ? `${node.id.slice(0, 5)}…` : node.id,
        ),
      );
    const labelCharacters = [...node.label];
    const label =
      nodeName(node.id) === node.id
        ? ""
        : labelCharacters.length > 22
          ? `${labelCharacters.slice(0, 21).join("")}…`
          : node.label;
    if (label && showText)
      group.append(
        svgElement(
          "text",
          {
            x: 0,
            y: radius + 23 * readable,
            class: "node-label",
            style: `font-size:${16 * readable}px`,
          },
          label,
        ),
      );
    if (showText && model.panel === "trace" && trace.distances.has(node.id))
      group.append(
        svgElement(
          "text",
          {
            x: 0,
            y: radius + (label ? 42 : 24) * readable,
            class: "node-cost",
            style: `font-size:${14 * readable}px`,
          },
          `${trace.distances.get(node.id)}${trace.settled.has(node.id) ? "" : " · tent."}`,
        ),
      );
    if (node.id === model.source || node.id === model.target) {
      const text =
        node.id === model.source && node.id === model.target
          ? "INICIO / FIN"
          : node.id === model.source
            ? "INICIO"
            : "DESTINO";
      const width = (text.length * 7 + 14) * readable;
      const badge = svgElement("g", { class: "node-badge" });
      badge.append(
        svgElement("rect", {
          x: -width / 2,
          y: -radius - 25 * readable,
          width,
          height: 19 * readable,
          rx: 5,
        }),
        svgElement(
          "text",
          {
            x: 0,
            y: -radius - 12 * readable,
            style: `font-size:${11 * readable}px`,
          },
          text,
        ),
      );
      group.append(badge);
    }
    group.addEventListener("pointerdown", (event) =>
      pointerNode(event, node.id),
    );
    group.addEventListener("keydown", (event) => keyboardNode(event, node.id));
    nodeFragment.append(group);
  }
  $("nodes").replaceChildren(nodeFragment);
  $("graph-count").textContent =
    `${model.graph.nodes.length} ${model.graph.nodes.length === 1 ? "nodo" : "nodos"} · ${model.graph.edges.length} ${model.graph.edges.length === 1 ? "conexión" : "conexiones"}`;
  $("empty-canvas").hidden = model.graph.nodes.length !== 0;
}
function focusGraphElement(type, id) {
  graphSvg
    .querySelector(`[data-${type}="${id}"]`)
    ?.focus({ preventScroll: true });
}
function point(event) {
  const value = graphSvg.createSVGPoint();
  value.x = event.clientX;
  value.y = event.clientY;
  const result = value.matrixTransform(graphSvg.getScreenCTM().inverse());
  return portrait ? { x: result.y, y: result.x } : result;
}
function clickNode(id) {
  if (model.tool === "connect") {
    if (!model.connectSource) {
      model.connectSource = id;
      $("canvas-hint").textContent =
        `Desde ${nodeName(id)}: elige el segundo nodo.`;
      renderGraph();
    } else {
      const first = model.connectSource;
      model.connectSource = null;
      model.selection = null;
      tab("edit");
      renderEditor();
      $("edge-source").value = first;
      $("edge-target").value = id;
      $("edge-weight").focus();
      $("canvas-hint").textContent = "Define el costo y pulsa Conectar.";
      renderGraph();
    }
  } else select("node", id);
}
function pointerNode(event, id) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  if (model.tool !== "select") {
    clickNode(id);
    return;
  }
  const start = point(event),
    node = model.graph.nodes.find((value) => value.id === id);
  model.dragging = {
    id,
    start,
    x: node.x,
    y: node.y,
    before: snapshot(),
    moved: false,
    pointerId: event.pointerId,
  };
  graphSvg.setPointerCapture(event.pointerId);
}
graphSvg.addEventListener("pointermove", (event) => {
  if (model.panning) {
    const pan = model.panning;
    const scale = graphScale();
    model.camera.x = pan.camera.x - (event.clientX - pan.x) / scale;
    model.camera.y = pan.camera.y - (event.clientY - pan.y) / scale;
    pan.moved ||= Math.hypot(event.clientX - pan.x, event.clientY - pan.y) > 3;
    applyCamera();
    return;
  }
  const drag = model.dragging;
  if (!drag) return;
  const now = point(event),
    dx = now.x - drag.start.x,
    dy = now.y - drag.start.y;
  if (!drag.moved && Math.hypot(dx, dy) < 4) return;
  if (!drag.moved) {
    invalidate();
    renderResult();
    renderPlayback();
    drag.moved = true;
    model.selection = { type: "node", id: drag.id };
  }
  const node = model.graph.nodes.find((value) => value.id === drag.id);
  node.x = Math.round(Math.max(-10000, Math.min(10000, drag.x + dx)));
  node.y = Math.round(Math.max(-10000, Math.min(10000, drag.y + dy)));
  renderGraph();
});
function endDrag(event, cancel = false) {
  if (model.panning) {
    const pan = model.panning;
    if (cancel) model.camera = pan.camera;
    model.suppressCanvasClick = pan.moved;
    model.panning = null;
    if (graphSvg.hasPointerCapture(event.pointerId))
      graphSvg.releasePointerCapture(event.pointerId);
    applyCamera();
    return;
  }
  const drag = model.dragging;
  if (!drag) return;
  model.dragging = null;
  if (graphSvg.hasPointerCapture(drag.pointerId))
    graphSvg.releasePointerCapture(drag.pointerId);
  if (cancel) {
    model.graph = drag.before.graph;
    render();
    return;
  }
  if (drag.moved) {
    model.undo.push(drag.before);
    if (model.undo.length > 60) model.undo.shift();
    model.redo = [];
    persist();
    render();
    tab("edit");
  } else clickNode(drag.id);
}
graphSvg.addEventListener("pointerup", (event) => endDrag(event));
graphSvg.addEventListener("pointercancel", (event) => endDrag(event, true));
graphSvg.addEventListener("pointerdown", (event) => {
  if (
    event.button !== 0 ||
    model.tool !== "select" ||
    (event.target !== graphSvg && event.target !== $("grid-rect"))
  )
    return;
  model.panning = {
    x: event.clientX,
    y: event.clientY,
    camera: { ...model.camera },
    moved: false,
  };
  graphSvg.setPointerCapture(event.pointerId);
});
graphSvg.addEventListener("click", (event) => {
  if (model.suppressCanvasClick) {
    model.suppressCanvasClick = false;
    return;
  }
  if (event.target !== graphSvg && event.target !== $("grid-rect")) return;
  if (model.tool === "add") {
    const position = point(event);
    const next = uniqueId(
      "N",
      new Set(model.graph.nodes.map((node) => node.id)),
    );
    addNode(next, Math.round(position.x), Math.round(position.y));
  } else {
    model.selection = null;
    model.connectSource = null;
    renderEditor();
    renderGraph();
  }
});
graphSvg.addEventListener("keydown", (event) => {
  if (event.target !== graphSvg) return;
  const direction = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }[event.key];
  if (!direction) return;
  event.preventDefault();
  model.camera.x += (direction[0] * model.camera.width) / 12;
  model.camera.y += (direction[1] * model.camera.height) / 12;
  applyCamera();
});
function keyboardNode(event, id) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    clickNode(id);
    focusGraphElement("node", id);
  }
  const directions = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  };
  if (directions[event.key]) {
    event.preventDefault();
    const distance = event.shiftKey ? 30 : 5;
    edit(
      (next) => {
        const node = next.graph.nodes.find((value) => value.id === id);
        node.x += directions[event.key][portrait ? 1 : 0] * distance;
        node.y += directions[event.key][portrait ? 0 : 1] * distance;
      },
      { selected: { type: "node", id } },
    );
    focusGraphElement("node", id);
  }
}
function renderPlayback() {
  const available = !!model.result?.trace?.length;
  const maximum = Math.max(0, (model.result?.trace?.length || 1) - 1);
  $("play").disabled = !available;
  $("play").setAttribute(
    "aria-label",
    model.playing ? "Pausar algoritmo" : "Reproducir algoritmo",
  );
  $("play").firstElementChild.textContent = model.playing ? "Ⅱ" : "▶";
  $("previous-step").disabled = !available || model.frame <= 0;
  $("next-step").disabled = !available || model.frame >= maximum;
  $("step-slider").disabled = !available;
  $("step-slider").max = maximum;
  $("step-slider").value = Math.max(0, model.frame);
  $("step-slider").setAttribute(
    "aria-valuetext",
    available
      ? `Paso ${model.frame + 1} de ${maximum + 1}`
      : "Calcula una ruta",
  );
  $("timeline-count").textContent = available
    ? `${model.frame + 1} / ${maximum + 1}`
    : "Calcula una ruta";
}
function eventText(event) {
  if (!event) return ["", ""];
  if (event.kind === "initialize")
    return [
      "Todo empieza en cero.",
      `${nodeName(model.source)} entra en la frontera con costo 0.`,
    ];
  if (event.kind === "settle")
    return [
      `${nodeName(event.node)} queda asentado.`,
      `Su costo ${event.cost ?? "conocido"} es definitivo. Sale de la frontera.`,
    ];
  if (event.kind === "consider")
    return [
      "Explorar una conexión.",
      `${nodeName(event.source)} → ${nodeName(event.target)}. Se comprueba si este recorrido mejora el costo conocido.`,
    ];
  if (event.kind === "relax")
    return [
      "Un camino mejor.",
      `${nodeName(event.target)}: ${event.old_cost ?? "∞"} → ${event.new_cost}. Su costo sigue siendo tentativo.`,
    ];
  if (event.kind === "stale")
    return [
      "Descartar una entrada antigua.",
      `Ya se conoce un costo mejor para ${nodeName(event.node)}.`,
    ];
  if (event.kind === "finish")
    return model.result.status === "ok"
      ? [
          "Destino alcanzado.",
          `La ruta mínima cuesta ${model.result.cost}. Los nodos no asentados conservan costos tentativos.`,
        ]
      : [
          "No existe una ruta.",
          "La frontera se agotó sin alcanzar el destino.",
        ];
  return ["Siguiente decisión.", ""];
}
function decimalUnits(value) {
  const [integer, fraction = ""] = String(value).split(".");
  return BigInt(integer) * 1000000n + BigInt(fraction.padEnd(6, "0"));
}
function renderResult() {
  const result = model.result;
  $("result-empty").hidden = !!result;
  $("result-content").hidden = !result;
  $("trace-empty").hidden = !!result;
  $("trace-content").hidden = !result;
  if (!result) return;
  $("result-label").textContent =
    result.status === "ok" ? "RUTA MÍNIMA" : "DESTINO INALCANZABLE";
  $("result-cost").textContent =
    result.status === "ok" ? result.cost : "Sin ruta";
  $("cost-caption").textContent =
    result.status === "ok"
      ? "costo total"
      : `${nodeName(result.source)} → ${nodeName(result.target)}`;
  const path = document.createDocumentFragment();
  result.path.forEach((id, index) => {
    if (index) {
      const arrow = document.createElement("span");
      arrow.className = "path-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      path.append(arrow);
    }
    const stop = document.createElement("span");
    stop.className = "path-stop";
    stop.textContent = nodeName(id);
    path.append(stop);
  });
  $("result-path").replaceChildren(path);
  $("result-settled").textContent = result.stats.settled;
  $("result-relaxations").textContent = result.stats.relaxations;
  $("result-note").textContent =
    result.source === result.target
      ? "Inicio y destino coinciden. El recorrido no necesita conexiones."
      : result.status === "no_path"
        ? "Conecta ambos componentes o cambia el sentido de las conexiones."
        : "El costo suma pesos; la posición de los nodos no lo modifica.";
  const state = traceState(),
    [title, description] = eventText(state.current);
  $("event-title").textContent = title;
  $("event-description").textContent = description;
  $("step-count").textContent = `${model.frame + 1} / ${result.trace.length}`;
  const rows = document.createDocumentFragment();
  const sorted = [...model.graph.nodes].sort((a, b) => {
    const da = state.distances.get(a.id),
      db = state.distances.get(b.id);
    if (da === undefined && db !== undefined) return 1;
    if (db === undefined && da !== undefined) return -1;
    if (da !== undefined && db !== undefined) {
      const difference = decimalUnits(da) - decimalUnits(db);
      if (difference) return difference < 0n ? -1 : 1;
    }
    return a.id.localeCompare(b.id);
  });
  for (const node of sorted) {
    const row = document.createElement("tr"),
      name = document.createElement("th"),
      cost = document.createElement("td"),
      status = document.createElement("td"),
      badge = document.createElement("span");
    name.scope = "row";
    name.textContent = node.id;
    name.title = node.label;
    cost.textContent = state.distances.get(node.id) ?? "∞";
    badge.className = `state-badge ${state.settled.has(node.id) ? "settled" : state.distances.has(node.id) ? "frontier" : ""}`;
    badge.textContent = state.settled.has(node.id)
      ? "Asentado"
      : state.distances.has(node.id)
        ? "Frontera"
        : "Sin visitar";
    status.append(badge);
    row.append(name, cost, status);
    rows.append(row);
  }
  $("distance-rows").replaceChildren(rows);
}
function render({ editor = true } = {}) {
  optionList($("source"), model.source);
  optionList($("target"), model.target);
  $("directed").checked = model.graph.directed;
  $("solve").disabled = model.busy || !model.graph.nodes.length;
  $("solve").firstElementChild.textContent = model.busy
    ? "Calculando…"
    : "Calcular ruta";
  $("solve").setAttribute("aria-busy", String(model.busy));
  $("swap").disabled = !model.graph.nodes.length;
  $("undo").disabled = !model.undo.length;
  $("redo").disabled = !model.redo.length;
  $("save-status").textContent = model.persisted
    ? "Guardado en este equipo"
    : "Sin guardar · exporta una copia";
  renderGraph();
  if (editor) renderEditor();
  renderResult();
  renderPlayback();
}
function validateResult(result) {
  const error = () => {
    throw new Error(
      "El motor devolvió un resultado incompleto. Vuelve a calcular.",
    );
  };
  const ids = new Set(model.graph.nodes.map((node) => node.id));
  const edgeIds = new Set(model.graph.edges.map((edge) => edge.id));
  const validCost = (value) =>
    typeof value === "string" && /^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(value);
  if (
    !object(result) ||
    !["ok", "no_path"].includes(result.status) ||
    result.source !== model.source ||
    result.target !== model.target
  )
    error();
  if (
    !Array.isArray(result.path) ||
    !Array.isArray(result.edge_path) ||
    !Array.isArray(result.settled) ||
    !Array.isArray(result.trace) ||
    !result.trace.length ||
    !object(result.stats) ||
    !object(result.distances)
  )
    error();
  if (
    !result.path.every((id) => ids.has(id)) ||
    !result.edge_path.every((id) => edgeIds.has(id)) ||
    !result.settled.every((id) => ids.has(id))
  )
    error();
  if (
    result.status === "ok" &&
    (!validCost(result.cost) ||
      result.path[0] !== model.source ||
      result.path.at(-1) !== model.target ||
      result.edge_path.length !== result.path.length - 1)
  )
    error();
  if (
    result.status === "no_path" &&
    (result.cost !== null || result.path.length || result.edge_path.length)
  )
    error();
  if (
    !["settled", "relaxations"].every(
      (key) => Number.isInteger(result.stats[key]) && result.stats[key] >= 0,
    )
  )
    error();
  const kinds = new Set([
    "initialize",
    "settle",
    "consider",
    "relax",
    "stale",
    "finish",
  ]);
  for (const [index, event] of result.trace.entries()) {
    if (!object(event) || event.step !== index || !kinds.has(event.kind))
      error();
    if (
      event.kind === "settle" &&
      (!ids.has(event.node) || !validCost(event.cost))
    )
      error();
    if (
      event.kind === "relax" &&
      (!ids.has(event.target) || !validCost(event.new_cost))
    )
      error();
  }
  return result;
}
async function solve() {
  if (!model.graph.nodes.length) return;
  invalidate();
  clearNotice();
  model.busy = true;
  const request = model.request;
  const controller = new AbortController();
  model.controller = controller;
  render({ editor: false });
  try {
    const result = await solveGraph(
      {
        graph: clone(model.graph),
        source: model.source,
        target: model.target,
        trace: true,
      },
      { signal: controller.signal },
    );
    if (request !== model.request || controller.signal.aborted) return;
    validateResult(result);
    model.result = result;
    model.frame = result.trace.length - 1;
    model.busy = false;
    model.controller = null;
    tab("result", { redraw: false });
    render({ editor: false });
    $("route-announcement").textContent =
      result.status === "ok"
        ? `Ruta calculada. Costo ${result.cost}.`
        : "No existe una ruta al destino.";
  } catch (error) {
    if (request !== model.request || error.name === "AbortError") return;
    model.busy = false;
    model.controller = null;
    render({ editor: false });
    notify(
      error.message ||
        "No se pudo ejecutar Python. Revisa la conexión y vuelve a intentarlo.",
    );
  }
}
function setFrame(frame) {
  if (!model.result) return;
  model.frame = Math.max(0, Math.min(model.result.trace.length - 1, frame));
  renderGraph();
  renderResult();
  renderPlayback();
}
function tick() {
  if (!model.playing || !model.result) return;
  if (model.frame >= model.result.trace.length - 1) {
    pause();
    return;
  }
  model.timer = setTimeout(
    () => {
      if (!model.playing) return;
      setFrame(model.frame + 1);
      tick();
    },
    Number($("speed").value),
  );
}
function download(name, contents, type = "application/json") {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function setMenu(open) {
  if (!open && $("file-menu").contains(document.activeElement))
    $("file-menu-button").focus();
  $("file-menu").hidden = !open;
  $("file-menu-button").setAttribute("aria-expanded", String(open));
}
function updateEngine(detail = engineStatus()) {
  $("engine-status").dataset.state = detail.state;
  $("engine-status").lastElementChild.textContent = detail.label;
  $("engine-help").textContent =
    detail.mode === "local"
      ? "Python se ejecuta en el servidor local de este equipo."
      : "Python se ejecuta en este navegador. La primera carga requiere Internet para preparar el motor.";
}

$("node-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const label = $("node-label").value,
    x = Number($("node-x").value),
    y = Number($("node-y").value);
  if (model.selection?.type === "node") {
    const id = model.selection.id;
    edit(
      (next) =>
        Object.assign(
          next.graph.nodes.find((node) => node.id === id),
          { label, x, y },
        ),
      { selected: { type: "node", id }, message: "Nodo actualizado." },
    );
  } else addNode(label, x, y);
});
$("edge-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const source = $("edge-source").value,
    target = $("edge-target").value,
    weight = $("edge-weight").value;
  const selected = model.selection?.type === "edge";
  const id = selected
    ? model.selection.id
    : uniqueId("E", new Set(model.graph.edges.map((edge) => edge.id)));
  edit(
    (next) => {
      const edge = { id, source, target, weight: canonicalWeight(weight) };
      if (selected)
        Object.assign(
          next.graph.edges.find((value) => value.id === id),
          edge,
        );
      else next.graph.edges.push(edge);
    },
    {
      selected: { type: "edge", id },
      message: selected ? "Conexión actualizada." : "Conexión añadida.",
    },
  );
});
$("node-delete").addEventListener("click", () => removeSelection("node"));
document
  .querySelector(".graph-list")
  .addEventListener("toggle", renderElementList);
$("edge-delete").addEventListener("click", () => removeSelection("edge"));
$("clear-selection").addEventListener("click", () => {
  model.selection = null;
  renderEditor();
  renderGraph();
  $("node-label").focus();
});
for (const name of ["edit", "result", "trace"]) {
  $("tab-" + name).addEventListener("click", () => tab(name));
  $("tab-" + name).addEventListener("keydown", (event) => {
    const names = ["edit", "result", "trace"];
    const index = names.indexOf(name);
    let next = null;
    if (event.key === "ArrowRight") next = names[(index + 1) % 3];
    if (event.key === "ArrowLeft") next = names[(index + 2) % 3];
    if (event.key === "Home") next = names[0];
    if (event.key === "End") next = names[2];
    if (next) {
      event.preventDefault();
      tab(next);
      $("tab-" + next).focus();
    }
  });
}
for (const tool of ["select", "connect", "add"])
  $("tool-" + tool).addEventListener("click", () => setTool(tool));
$("fit").addEventListener("click", () => {
  fitGraph();
  renderGraph();
});
function zoom(factor) {
  const nextWidth = model.camera.width * factor;
  if (nextWidth < 50 || nextWidth > 50000) return;
  model.camera.x += (model.camera.width * (1 - factor)) / 2;
  model.camera.y += (model.camera.height * (1 - factor)) / 2;
  model.camera.width *= factor;
  model.camera.height *= factor;
  applyCamera();
  renderGraph();
}
$("zoom-in").addEventListener("click", () => zoom(0.75));
$("zoom-out").addEventListener("click", () => zoom(1 / 0.75));
$("empty-add").addEventListener("click", () => {
  addNode("Primer nodo", 500, 300);
  $("node-label").focus();
  $("node-label").select();
});
for (const endpoint of ["source", "target"])
  $(endpoint).addEventListener("change", () =>
    edit((next) => {
      next[endpoint] = $(endpoint).value;
    }),
  );
$("swap").addEventListener("click", () =>
  edit((next) => {
    [next.source, next.target] = [next.target, next.source];
  }),
);
$("directed").addEventListener("change", () => {
  const directed = $("directed").checked;
  try {
    const next = snapshot();
    if (directed) {
      const used = new Set(next.graph.edges.map((edge) => edge.id));
      const reversed = [];
      for (const edge of next.graph.edges)
        if (edge.source !== edge.target) {
          const id = uniqueId("E", used);
          used.add(id);
          reversed.push({
            id,
            source: edge.target,
            target: edge.source,
            weight: edge.weight,
          });
        }
      if (next.graph.edges.length + reversed.length > 4000)
        throw new Error(
          "Convertir a dirigido superaría 4 000 conexiones. Reduce el grafo primero.",
        );
      next.graph.edges.push(...reversed);
    } else {
      const pairs = new Map();
      for (const edge of next.graph.edges) {
        const pair = JSON.stringify([edge.source, edge.target].sort());
        if (pairs.has(pair) && pairs.get(pair).weight !== edge.weight)
          throw new Error(
            `Las conexiones ${edge.source} ↔ ${edge.target} tienen costos distintos. Iguala sus costos o elimina una antes de quitar la dirección.`,
          );
        if (!pairs.has(pair)) pairs.set(pair, edge);
      }
      next.graph.edges = [...pairs.values()];
    }
    next.graph.directed = directed;
    commit(next, {
      message: directed
        ? "Cada conexión ahora tiene ambos sentidos. Puedes editar cada dirección."
        : "Conexiones opuestas de igual costo unidas. Puedes deshacer.",
    });
  } catch (error) {
    $("directed").checked = model.graph.directed;
    notify(error.message);
  }
});
$("solve").addEventListener("click", solve);
$("undo").addEventListener("click", () => history("undo"));
$("redo").addEventListener("click", () => history("redo"));
$("explore-trace").addEventListener("click", () => {
  pause();
  setFrame(0);
  tab("trace");
  $("play").focus({ preventScroll: true });
});
$("play").addEventListener("click", () => {
  if (model.playing) pause();
  else {
    if (!model.result) return;
    if (model.frame >= model.result.trace.length - 1) setFrame(0);
    model.playing = true;
    tab("trace");
    renderPlayback();
    tick();
  }
});
$("previous-step").addEventListener("click", () => {
  pause();
  setFrame(model.frame - 1);
  tab("trace");
});
$("next-step").addEventListener("click", () => {
  pause();
  setFrame(model.frame + 1);
  tab("trace");
});
$("step-slider").addEventListener("input", () => {
  const frame = Number($("step-slider").value);
  pause();
  setFrame(frame);
  tab("trace");
});
$("speed").addEventListener("change", () => {
  if (model.playing) {
    clearTimeout(model.timer);
    tick();
  }
});
$("notice-dismiss").addEventListener("click", clearNotice);
$("file-menu-button").addEventListener("click", () =>
  setMenu($("file-menu").hidden),
);
document.addEventListener("click", (event) => {
  if (!event.target.closest(".header-actions")) setMenu(false);
});
$("import-button").addEventListener("click", () => {
  setMenu(false);
  $("import-file").click();
});
$("import-file").addEventListener("change", async () => {
  const file = $("import-file").files[0];
  $("import-file").value = "";
  if (!file) return;
  const version = model.request;
  $("import-button").disabled = true;
  notify("Validando archivo en Python…", "success");
  try {
    if (file.size > 2 * 1024 * 1024)
      throw new Error(
        "El archivo supera 2 MiB. Importa un grafo de hasta 500 nodos y 4 000 conexiones.",
      );
    let raw;
    try {
      raw = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
    } catch {
      throw new Error(
        "El archivo debe usar texto UTF-8 válido. Tu grafo sigue intacto.",
      );
    }
    const graph = validateGraph(await normalizeGraphJSON(raw));
    if (version !== model.request) {
      notify(
        "El grafo cambió durante la importación. Vuelve a importar el archivo.",
      );
      return;
    }
    commit(
      {
        graph,
        source: graph.nodes[0]?.id || "",
        target: graph.nodes.at(-1)?.id || "",
      },
      { fit: true, message: "Grafo importado. Puedes deshacer." },
    );
  } catch (error) {
    notify(
      error instanceof SyntaxError
        ? "El archivo no contiene JSON válido. Tu grafo sigue intacto."
        : error.message,
    );
  } finally {
    $("import-button").disabled = false;
  }
});
$("export-button").addEventListener("click", () => {
  setMenu(false);
  download("vertice-grafo.json", JSON.stringify(model.graph, null, 2) + "\n");
});
$("new-button").addEventListener("click", () => {
  setMenu(false);
  commit(
    { graph: blank(), source: "", target: "" },
    {
      fit: true,
      message: "Lienzo vacío. Puedes recuperar el grafo anterior con Deshacer.",
    },
  );
  tab("edit");
});
$("example").addEventListener("change", () => {
  const example = model.examples.find(
    (value) => value.id === $("example").value,
  );
  if (!example) return;
  try {
    commit(
      { graph: example.graph, source: example.source, target: example.target },
      { fit: true },
    );
    $("example").value = example.id;
    if (model.persisted) clearNotice();
  } catch (error) {
    notify(error.message);
  }
});
$("help-button").addEventListener("click", () => $("help-dialog").showModal());
$("help-close").addEventListener("click", () => $("help-dialog").close());
$("menu-help").addEventListener("click", () => {
  setMenu(false);
  $("help-dialog").showModal();
});
$("help-dialog").addEventListener("click", (event) => {
  if (event.target === $("help-dialog")) {
    const rect = $("help-dialog").getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    )
      $("help-dialog").close();
  }
});
document.addEventListener("keydown", (event) => {
  const editing = event.target.matches(
    "input,textarea,select,[contenteditable=true]",
  );
  if (event.key === "Escape") {
    setMenu(false);
    model.connectSource = null;
    setTool("select");
  }
  if (
    (event.ctrlKey || event.metaKey) &&
    !editing &&
    event.key.toLowerCase() === "z"
  ) {
    event.preventDefault();
    history(event.shiftKey ? "redo" : "undo");
  }
});
window.addEventListener("vertice-engine", (event) =>
  updateEngine(event.detail || engineStatus()),
);
window.addEventListener("beforeunload", (event) => {
  if (!model.persisted) {
    event.preventDefault();
    event.returnValue = "";
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) pause();
});
window.addEventListener("resize", () => {
  const next = matchMedia("(max-width: 600px)").matches;
  if (next !== portrait) {
    portrait = next;
    fitGraph();
  }
  renderGraph();
});
$("dismiss-recovery").addEventListener("click", () => {
  $("recovery").hidden = true;
});
$("download-recovery").addEventListener("click", () =>
  download("vertice-recuperacion.json", model.recoveryRaw || ""),
);
$("recover-button").addEventListener("click", () => {
  if (model.backup) {
    commit(model.backup, { fit: true, message: "Copia anterior recuperada." });
    $("recovery").hidden = true;
  }
});

async function initialize() {
  let loaded = false;
  try {
    const raw = localStorage.getItem(STORE);
    if (raw) {
      try {
        const saved = JSON.parse(raw);
        if (saved.version !== 1) throw new Error("Versión desconocida");
        model.graph = validateGraph(saved.graph);
        model.source = saved.source || "";
        model.target = saved.target || "";
        validEndpoints();
        loaded = true;
      } catch {
        model.recoveryRaw = raw;
        $("recovery").hidden = false;
        $("recovery-text").textContent =
          "La sesión guardada no se pudo abrir. Conservamos el original para recuperarlo.";
        try {
          const backup = JSON.parse(localStorage.getItem(BACKUP));
          if (backup) {
            validateGraph(backup.graph);
            model.backup = backup;
          }
        } catch {
          /* The damaged original remains available for download. */
        }
        $("recover-button").hidden = !model.backup;
      }
    }
  } catch {
    model.persisted = false;
    notify(
      "El almacenamiento está bloqueado. Puedes editar y exportar tu grafo.",
    );
  }
  render();
  updateEngine();
  try {
    const response = await fetch("data/examples.json");
    if (!response.ok) throw new Error("No se pudieron cargar los ejemplos.");
    const examples = await response.json();
    if (!Array.isArray(examples))
      throw new Error("El catálogo de ejemplos no es válido.");
    model.examples = examples.map((example) => ({
      ...example,
      graph: validateGraph(example.graph),
    }));
    for (const example of model.examples) {
      const option = document.createElement("option");
      option.value = example.id;
      option.textContent = example.name;
      $("example").append(option);
    }
    if (!loaded && model.examples.length && model.undo.length === 0) {
      const first = model.examples[0];
      model.graph = clone(first.graph);
      model.source = first.source;
      model.target = first.target;
      validEndpoints();
      $("example").value = first.id;
    }
  } catch (error) {
    notify(`${error.message} Puedes crear o importar un grafo.`);
  }
  fitGraph();
  render();
}
initialize();
