import { loadPyodide } from './vendor/pyodide/pyodide.mjs';

let solveJson;
let normalizeJson;
let initialization;
const names = new Set(['__init__.py', 'graph.py', 'dijkstra.py', 'codec.py']);

async function initialize() {
  const pyodide = await loadPyodide({ indexURL: new URL('./vendor/pyodide/', import.meta.url).href });
  const response = await fetch(new URL('./python/manifest.json', import.meta.url), { cache: 'no-cache' });
  if (!response.ok) throw new Error('No se pudo abrir el motor Python.');
  const manifest = await response.json();
  if (manifest.package !== 'vertice' || manifest.files?.length !== names.size ||
      new Set(manifest.files.map(file => file.name)).size !== names.size) {
    throw new Error('El paquete Python está incompleto.');
  }
  pyodide.FS.mkdirTree('/app/vertice');
  await Promise.all(manifest.files.map(async (file) => {
    if (!names.has(file.name)) throw new Error('Archivo de motor no reconocido.');
    const fetched = await fetch(new URL(`./python/vertice/${file.name}`, import.meta.url), { cache: 'no-cache' });
    if (!fetched.ok) throw new Error('Falta un archivo del motor Python.');
    const bytes = new Uint8Array(await fetched.arrayBuffer());
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map(value => value.toString(16).padStart(2, '0')).join('');
    if (digest !== file.sha256) throw new Error('El motor cambió durante la carga. Recarga la página.');
    pyodide.FS.writeFile(`/app/vertice/${file.name}`, bytes);
  }));
  // Constant code only: user data is passed as an argument to solve_json below.
  pyodide.runPython("import sys, json\nsys.path.insert(0, '/app')\nfrom vertice.codec import solve_json, load_json\nfrom vertice.graph import Graph\ndef normalize_graph_json(text):\n    return json.dumps(Graph.from_dict(load_json(text)).to_dict(), ensure_ascii=False, allow_nan=False)\n");
  solveJson = pyodide.globals.get('solve_json');
  normalizeJson = pyodide.globals.get('normalize_graph_json');
  return { python: pyodide.runPython('sys.version.split()[0]'), core: manifest.files };
}

self.onmessage = async ({ data }) => {
  const { id, type, payload } = data;
  try {
    initialization ??= initialize();
    const metadata = await initialization;
    if (type === 'initialize') {
      self.postMessage({ id, ok: true, result: metadata });
    } else if (type === 'solve') {
      const result = JSON.parse(solveJson(JSON.stringify(payload)));
      self.postMessage({ id, ok: true, result });
    } else if (type === 'validate') {
      self.postMessage({ id, ok: true, result: JSON.parse(normalizeJson(payload)) });
    } else throw new Error('Operación desconocida.');
  } catch (error) {
    const detail = String(error?.message || error);
    const validation = detail.match(/ValidationError: ([^\n]+)/);
    self.postMessage({ id, ok: false,
      error: validation ? validation[1] : 'No se pudo ejecutar Python. Recarga e inténtalo de nuevo.',
      kind: validation ? 'validation' : 'engine' });
    if (!validation) console.error(detail);
  }
};
