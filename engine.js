let status = { mode: 'pending', state: 'idle', label: 'Preparando motor' };
let worker;
let workerReady;
let counter = 0;
let active = false;
const pending = new Map();
const queue = [];

export function engineStatus() { return { ...status }; }
function report(mode, state, label) {
  status = { mode, state, label };
  window.dispatchEvent(new CustomEvent('vertice-engine', { detail: engineStatus() }));
}
function abortError() { return new DOMException('Cálculo cancelado.', 'AbortError'); }
function disposeWorker(error = abortError(), expected = worker) {
  // Late errors from a replaced worker must not terminate its successor.
  if (worker !== expected) return;
  worker?.terminate();
  worker = null;
  workerReady = null;
  for (const job of [...pending.values()]) job.reject(error);
  pending.clear();
}
async function chooseMode() {
  const forcedBrowser = new URLSearchParams(location.search).get('engine') === 'browser';
  if (!forcedBrowser && ['localhost', '127.0.0.1'].includes(location.hostname)) {
    try {
      const response = await fetch('./api/health', { signal: AbortSignal.timeout(1800), cache: 'no-store' });
      const health = response.ok && await response.json();
      if (health?.project === 'vertice-sdv' && health?.engine === 'python') return 'local';
    } catch { /* A static server is also supported on localhost. */ }
  }
  return 'browser';
}
function workerRequest(type, payload, signal, timeoutMs = 20000) {
  if (signal.aborted) return Promise.reject(abortError());
  const activeWorker = worker;
  const id = ++counter;
  return new Promise((resolve, reject) => {
    let timer;
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', aborted);
      pending.delete(id);
    };
    const aborted = () => disposeWorker(abortError(), activeWorker);
    pending.set(id, {
      resolve: result => { clean(); resolve(result); },
      reject: error => { clean(); reject(error); },
    });
    timer = setTimeout(() => disposeWorker(new Error('Python tardó demasiado. Inténtalo de nuevo.'), activeWorker), timeoutMs);
    signal.addEventListener('abort', aborted, { once: true });
    try { activeWorker.postMessage({ id, type, payload }); }
    catch (error) { pending.get(id)?.reject(error); }
  });
}
async function ensureWorker(signal) {
  if (!worker) {
    report('browser', 'loading', 'Cargando Python');
    const instance = new Worker(new URL('./python-worker.js', import.meta.url), { type: 'module' });
    worker = instance;
    instance.onmessage = ({ data }) => {
      if (worker !== instance) return;
      const job = pending.get(data.id);
      if (!job) return;
      if (data.ok) job.resolve(data.result);
      else {
        const error = new Error(data.error);
        error.name = data.kind === 'validation' ? 'ValidationError' : 'EngineError';
        job.reject(error);
      }
    };
    instance.onerror = () => disposeWorker(new Error('No se pudo iniciar Python. Recarga la página.'), instance);
    workerReady = workerRequest('initialize', null, signal, 60000).catch(error => {
      disposeWorker(error, instance);
      throw error;
    });
  }
  await workerReady;
  if (signal.aborted) throw abortError();
}
async function localRequest(type, payload, signal) {
  if (signal.aborted) throw abortError();
  const controller = new AbortController();
  const cancelled = () => controller.abort();
  signal.addEventListener('abort', cancelled, { once: true });
  let expired = false;
  const timer = setTimeout(() => { expired = true; controller.abort(); }, 20000);
  try {
    if (signal.aborted) throw abortError();
    const response = await fetch(`./api/${type}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: type === 'validate' ? payload : JSON.stringify(payload),
      signal: controller.signal, cache: 'no-store',
    });
    const body = await response.json();
    if (!response.ok) {
      const error = new Error(body.error || 'No se pudo completar la operación.');
      error.name = response.status === 400 || response.status === 413 ? 'ValidationError' : 'EngineError';
      throw error;
    }
    return body;
  } catch (error) {
    if (expired && !signal.aborted) throw new Error('El motor no respondió a tiempo. Inténtalo de nuevo.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancelled);
  }
}
async function execute(type, payload, signal) {
  if (signal.aborted) throw abortError();
  const mode = await modePromise;
  if (signal.aborted) throw abortError();
  try {
    let result;
    if (mode === 'local') {
      report(mode, 'running', type === 'solve' ? 'Calculando' : 'Validando grafo');
      result = await localRequest(type, payload, signal);
    } else {
      await ensureWorker(signal);
      report(mode, 'running', type === 'solve' ? 'Calculando' : 'Validando grafo');
      result = await workerRequest(type, payload, signal);
    }
    if (signal.aborted) throw abortError();
    report(mode, 'ready', 'Python listo');
    return result;
  } catch (error) {
    const state = error.name === 'AbortError' ? 'idle' : error.name === 'ValidationError' ? 'ready' : 'error';
    report(mode, state, state === 'error' ? 'Motor no disponible' : state === 'idle' ? 'Python disponible' : 'Python listo');
    throw error;
  }
}
async function pump() {
  if (active) return;
  active = true;
  try {
    while (queue.length) {
      const job = queue.shift();
      if (job.cancelled) continue;
      job.started = true;
      try { job.resolve(await execute(job.type, job.payload, job.controller.signal)); }
      catch (error) { job.reject(error); }
    }
  } finally { active = false; }
}
function enqueue(type, payload, { signal } = {}) {
  if (signal?.aborted) return Promise.reject(abortError());
  // Snapshot before enqueue: callers may edit while another task is running.
  let snapshot;
  try { snapshot = type === 'validate' ? payload : structuredClone(payload); }
  catch (error) { return Promise.reject(error); }
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const finish = callback => value => { signal?.removeEventListener('abort', cancel); callback(value); };
    const job = { type, payload: snapshot, controller, cancelled: false, started: false,
      resolve: finish(resolve), reject: finish(reject) };
    const cancel = () => {
      job.cancelled = true;
      controller.abort();
      job.reject(abortError()); // Queued cancellation is immediate and independent.
    };
    signal?.addEventListener('abort', cancel, { once: true });
    queue.push(job);
    void pump();
  });
}
export function solveGraph(payload, options = {}) { return enqueue('solve', payload, options); }
export function normalizeGraphJSON(rawText, options = {}) {
  if (typeof rawText !== 'string') return Promise.reject(new TypeError('Se requiere texto JSON.'));
  if (new TextEncoder().encode(rawText).length > 2 * 1024 * 1024) {
    return Promise.reject(new Error('El archivo JSON excede 2 MiB.'));
  }
  return enqueue('validate', rawText, options);
}
// Probe is cheap; WebAssembly loads only when first needed. No external requests.
const modePromise = chooseMode().then(mode => {
  report(mode, 'idle', mode === 'local' ? 'Python local' : 'Python en navegador');
  return mode;
});
