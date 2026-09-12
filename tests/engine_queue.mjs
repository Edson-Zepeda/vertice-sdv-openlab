/**
 * Contract tests for the REAL engine.js module. Worker/fetch are controlled
 * doubles; this is not a browser, WASM, Python or network compatibility test.
 * Run: node --test tests/engine_queue.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let moduleNumber = 0;
const tick = () => new Promise(resolve => setImmediate(resolve));
const aborted = () => new DOMException('Cancelado en transporte controlado.', 'AbortError');

function tracked(promise) {
  const item = { state: 'pending' };
  item.done = Promise.resolve(promise).then(value => {
    item.state = 'fulfilled'; item.value = value;
  }, error => {
    item.state = 'rejected'; item.error = error;
  });
  return item;
}

async function until(predicate, label = 'condición asíncrona') {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.ok(predicate(), `No se alcanzó: ${label}`);
}

async function harness(mode = 'browser') {
  const workers = [], requests = [], events = [];
  const settings = { closed: false, throwConstructor: false, throwPost: false };
  globalThis.window = new EventTarget();
  globalThis.location = { hostname: 'localhost', search: mode === 'browser' ? '?engine=browser' : '' };
  window.addEventListener('vertice-engine', event => events.push(event.detail));
  globalThis.Worker = class ControlledWorker {
    constructor(url, options) {
      if (settings.closed || settings.throwConstructor) {
        settings.throwConstructor = false;
        throw new Error('Constructor de worker no disponible.');
      }
      this.url = String(url); this.options = options; this.messages = []; this.terminated = false;
      workers.push(this);
    }
    postMessage(message) {
      if (settings.throwPost) {
        settings.throwPost = false;
        throw new DOMException('Fallo de postMessage.', 'DataCloneError');
      }
      this.messages.push(structuredClone(message));
    }
    terminate() { this.terminated = true; }
    reply(message, result = { status: 'ok' }) {
      this.onmessage?.({ data: { id: message.id, ok: true, result } });
    }
    fail(message, kind = 'engine') {
      this.onmessage?.({ data: { id: message.id, ok: false, kind, error: 'Fallo controlado.' } });
    }
    crash() { this.onerror?.(new Error('Fallo del worker controlado.')); }
  };
  globalThis.fetch = async (url, options = {}) => {
    if (url === './api/health') {
      return { ok: true, json: async () => mode === 'local'
        ? { project: 'vertice-sdv', engine: 'python' } : { project: 'otro-proyecto' } };
    }
    if (settings.closed) throw new Error('Transporte cerrado.');
    return new Promise((resolve, reject) => {
      const request = { url, options, cancelled: false };
      const cancel = () => { request.cancelled = true; reject(aborted()); };
      request.reply = (body = { status: 'ok' }, status = 200) => {
        options.signal?.removeEventListener('abort', cancel);
        resolve({ ok: status >= 200 && status < 300, status, json: async () => body });
      };
      request.reject = reject;
      requests.push(request);
      if (options.signal?.aborted) cancel();
      else options.signal?.addEventListener('abort', cancel, { once: true });
    });
  };
  const url = pathToFileURL(path.join(root, 'web', 'engine.js'));
  url.searchParams.set('test-module', String(++moduleNumber));
  const engine = await import(url.href);
  await tick();
  return {
    workers, requests, events, settings, engine,
    async initialize(index = workers.length - 1) {
      await until(() => workers[index]?.messages.some(message => message.type === 'initialize'), 'mensaje initialize');
      const worker = workers[index];
      worker.reply(worker.messages.find(message => message.type === 'initialize'), { python: 'controlled-test' });
      await tick();
      return worker;
    },
    async close() {
      settings.closed = true;
      for (const worker of workers) worker.crash();
      for (const request of requests) request.reject(new Error('Fin de prueba.'));
      await tick(); await tick();
    },
  };
}

function caseTest(name, callback, mode = 'browser') {
  test(name, { concurrency: false }, async () => {
    const h = await harness(mode);
    try { await callback(h); }
    finally { await h.close(); }
  });
}

caseTest('inicializa Python una vez y entrega el resultado de solve', async h => {
  const task = tracked(h.engine.solveGraph({ source: 'A' }));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  const solve = worker.messages.find(message => message.type === 'solve');
  assert.equal(solve.payload.source, 'A');
  worker.reply(solve, { status: 'ok', cost: '0.1' });
  await task.done;
  assert.equal(task.value.cost, '0.1');
  assert.equal(h.engine.engineStatus().state, 'ready');
  assert.equal(worker.messages.filter(message => message.type === 'initialize').length, 1);
});

caseTest('FIFO mantiene una sola operación en vuelo y el orden de tres solicitudes', async h => {
  const tasks = ['A', 'B', 'C'].map(source => tracked(h.engine.solveGraph({ source })));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  for (let index = 0; index < tasks.length; index += 1) {
    await until(() => worker.messages.filter(message => message.type === 'solve').length === index + 1);
    const messages = worker.messages.filter(message => message.type === 'solve');
    assert.equal(messages.at(-1).payload.source, ['A', 'B', 'C'][index]);
    assert.equal(tasks[index].state, 'pending');
    worker.reply(messages.at(-1), { source: messages.at(-1).payload.source });
    await tasks[index].done;
  }
  assert.deepEqual(tasks.map(item => item.value.source), ['A', 'B', 'C']);
});

caseTest('la instantánea se toma al solicitar, antes de esperar carga o cola', async h => {
  const payload = { graph: { nodes: [{ id: 'A' }] } };
  const first = tracked(h.engine.solveGraph(payload));
  const second = tracked(h.engine.solveGraph(payload));
  payload.graph.nodes[0].id = 'MUTADO';
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  const initial = worker.messages.find(message => message.type === 'solve');
  assert.equal(initial.payload.graph.nodes[0].id, 'A');
  worker.reply(initial);
  await first.done; await tick();
  const next = worker.messages.filter(message => message.type === 'solve').at(-1);
  assert.equal(next.payload.graph.nodes[0].id, 'A');
  worker.reply(next); await second.done;
});

caseTest('cancelar una espera rechaza de inmediato y no termina la carga activa', async h => {
  const first = tracked(h.engine.solveGraph({ source: 'A' }));
  const cancel = new AbortController();
  const second = tracked(h.engine.solveGraph({ source: 'B' }, { signal: cancel.signal }));
  await until(() => h.workers.length === 1);
  cancel.abort(); await second.done;
  assert.equal(second.error.name, 'AbortError');
  assert.equal(first.state, 'pending');
  assert.equal(h.workers[0].terminated, false);
  const worker = await h.initialize();
  worker.reply(worker.messages.find(message => message.type === 'solve'));
  await first.done; await tick();
  assert.equal(worker.messages.filter(message => message.type === 'solve').length, 1);
});

caseTest('cancelar la carga activa permite iniciar al siguiente consumidor', async h => {
  const cancel = new AbortController();
  const first = tracked(h.engine.solveGraph({ source: 'A' }, { signal: cancel.signal }));
  const second = tracked(h.engine.solveGraph({ source: 'B' }));
  await until(() => h.workers.length === 1);
  cancel.abort(); await first.done;
  await until(() => h.workers.length === 2);
  assert.equal(h.workers[0].terminated, true);
  assert.equal(second.state, 'pending');
  const worker = await h.initialize(1);
  const request = worker.messages.find(message => message.type === 'solve');
  assert.equal(request.payload.source, 'B');
  worker.reply(request); await second.done;
  assert.equal(second.state, 'fulfilled');
});

caseTest('cancelar un cálculo activo no cancela la siguiente solicitud', async h => {
  const cancel = new AbortController();
  const first = tracked(h.engine.solveGraph({ source: 'A' }, { signal: cancel.signal }));
  const second = tracked(h.engine.solveGraph({ source: 'B' }));
  await until(() => h.workers.length === 1);
  await h.initialize();
  cancel.abort(); await first.done;
  await until(() => h.workers.length === 2);
  const worker = await h.initialize(1);
  worker.reply(worker.messages.find(message => message.type === 'solve'), { source: 'B' });
  await second.done;
  assert.equal(first.error.name, 'AbortError');
  assert.equal(second.value.source, 'B');
});

caseTest('señal cancelada antes de solicitar no crea worker ni tráfico solve', async h => {
  const cancel = new AbortController(); cancel.abort();
  await assert.rejects(h.engine.solveGraph({}, { signal: cancel.signal }), { name: 'AbortError' });
  assert.equal(h.workers.length, 0);
  assert.equal(h.requests.length, 0);
});

caseTest('errores y mensajes tardíos de un worker retirado no dañan al sucesor', async h => {
  const cancel = new AbortController();
  const first = tracked(h.engine.solveGraph({}, { signal: cancel.signal }));
  await until(() => h.workers.length === 1);
  const oldWorker = await h.initialize();
  cancel.abort(); await first.done;
  const second = tracked(h.engine.solveGraph({ source: 'new' }));
  await until(() => h.workers.length === 2);
  const newWorker = await h.initialize(1);
  const request = newWorker.messages.find(message => message.type === 'solve');
  oldWorker.crash();
  oldWorker.reply(request, { source: 'stale-forged-id' });
  await tick();
  assert.equal(newWorker.terminated, false);
  assert.equal(second.state, 'pending');
  newWorker.reply(request, { source: 'new' }); await second.done;
  assert.equal(second.value.source, 'new');
});

caseTest('una falla de inicialización permite un reintento limpio', async h => {
  const first = tracked(h.engine.solveGraph({}));
  await until(() => h.workers.length === 1);
  const old = h.workers[0];
  old.fail(old.messages[0]); await first.done;
  assert.equal(old.terminated, true);
  const second = tracked(h.engine.solveGraph({ source: 'retry' }));
  await until(() => h.workers.length === 2);
  const worker = await h.initialize(1);
  worker.reply(worker.messages.find(message => message.type === 'solve'), { source: 'retry' });
  await second.done; assert.equal(second.state, 'fulfilled');
});

caseTest('un error de worker no elimina solicitudes todavía en cola', async h => {
  const first = tracked(h.engine.solveGraph({ source: 'A' }));
  const second = tracked(h.engine.solveGraph({ source: 'B' }));
  await until(() => h.workers.length === 1);
  const old = await h.initialize(); old.crash(); await first.done;
  await until(() => h.workers.length === 2);
  const worker = await h.initialize(1);
  worker.reply(worker.messages.find(message => message.type === 'solve'), { source: 'B' });
  await second.done; assert.equal(second.value.source, 'B');
});

caseTest('error de validación conserva el runtime para la siguiente operación', async h => {
  const first = tracked(h.engine.solveGraph({ source: 'invalid' }));
  const second = tracked(h.engine.solveGraph({ source: 'valid' }));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  worker.fail(worker.messages.find(message => message.type === 'solve'), 'validation');
  await first.done; await tick();
  assert.equal(first.error.name, 'ValidationError');
  assert.equal(worker.terminated, false);
  worker.reply(worker.messages.filter(message => message.type === 'solve').at(-1));
  await second.done; assert.equal(second.state, 'fulfilled');
  assert.equal(h.workers.length, 1);
});

caseTest('normalización transmite el texto JSON original sin convertir números', async h => {
  const text = '{"weight":1000000000000.000001,"other":1e-1000,"weight":0}';
  const task = tracked(h.engine.normalizeGraphJSON(text));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  const request = worker.messages.find(message => message.type === 'validate');
  assert.equal(request.payload, text);
  worker.fail(request, 'validation'); await task.done;
  assert.equal(task.error.name, 'ValidationError');
});

caseTest('normalización rechaza tipo incorrecto y más de 2 MiB antes de cargar Python', async h => {
  await assert.rejects(h.engine.normalizeGraphJSON({}), TypeError);
  await assert.rejects(h.engine.normalizeGraphJSON('x'.repeat(2 * 1024 * 1024 + 1)));
  assert.equal(h.workers.length, 0);
});

caseTest('cancelar una solicitud finalizada no afecta al siguiente cálculo', async h => {
  const cancel = new AbortController();
  const first = tracked(h.engine.solveGraph({}, { signal: cancel.signal }));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  worker.reply(worker.messages.find(message => message.type === 'solve')); await first.done;
  const second = tracked(h.engine.solveGraph({ source: 'next' })); await tick();
  cancel.abort(); await tick();
  assert.equal(worker.terminated, false);
  worker.reply(worker.messages.filter(message => message.type === 'solve').at(-1)); await second.done;
  assert.equal(second.state, 'fulfilled');
});

caseTest('si falla el constructor del worker, una solicitud posterior puede reintentar', async h => {
  h.settings.throwConstructor = true;
  const first = tracked(h.engine.solveGraph({})); await first.done;
  assert.equal(first.state, 'rejected');
  const second = tracked(h.engine.solveGraph({}));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  worker.reply(worker.messages.find(message => message.type === 'solve')); await second.done;
  assert.equal(second.state, 'fulfilled');
});

caseTest('el modo local usa FIFO y transmite texto crudo a validate', async h => {
  const raw = '{"weight":1000000000000.000001}';
  const first = tracked(h.engine.solveGraph({ source: 'A' }));
  const second = tracked(h.engine.normalizeGraphJSON(raw));
  await until(() => h.requests.length === 1);
  assert.equal(h.requests[0].url, './api/solve');
  assert.equal(JSON.parse(h.requests[0].options.body).source, 'A');
  h.requests[0].reply(); await first.done;
  await until(() => h.requests.length === 2);
  assert.equal(h.requests[1].url, './api/validate');
  assert.equal(h.requests[1].options.body, raw);
  h.requests[1].reply({ error: 'Peso fuera de límites.' }, 400); await second.done;
  assert.equal(second.error.name, 'ValidationError');
  assert.equal(h.workers.length, 0);
}, 'local');

caseTest('cancelación HTTP afecta al activo y permite continuar la cola', async h => {
  const cancel = new AbortController();
  const first = tracked(h.engine.solveGraph({ source: 'A' }, { signal: cancel.signal }));
  const second = tracked(h.engine.solveGraph({ source: 'B' }));
  await until(() => h.requests.length === 1);
  cancel.abort(); await first.done;
  await until(() => h.requests.length === 2);
  assert.equal(h.requests[0].cancelled, true);
  assert.equal(h.requests[1].cancelled, false);
  h.requests[1].reply({ source: 'B' }); await second.done;
  assert.equal(second.value.source, 'B');
}, 'local');

caseTest('HTTP 413 es error de validación recuperable', async h => {
  const task = tracked(h.engine.solveGraph({}));
  await until(() => h.requests.length === 1);
  h.requests[0].reply({ error: 'Demasiado grande.' }, 413); await task.done;
  assert.equal(task.error.name, 'ValidationError');
  assert.equal(h.engine.engineStatus().state, 'ready');
}, 'local');

caseTest('health de otro proyecto no autoriza el transporte HTTP local', async h => {
  const task = tracked(h.engine.solveGraph({}));
  await until(() => h.workers.length === 1);
  const worker = await h.initialize();
  worker.reply(worker.messages.find(message => message.type === 'solve')); await task.done;
  assert.equal(h.requests.length, 0);
  assert.equal(h.engine.engineStatus().mode, 'browser');
}, 'wrong-health');

caseTest('datos no clonables rechazan con una Promise según el contrato', async h => {
  let promise;
  assert.doesNotThrow(() => { promise = h.engine.solveGraph({ invalid: () => {} }); });
  assert.equal(typeof promise?.then, 'function');
  await assert.rejects(promise, { name: 'DataCloneError' });
});

caseTest('cancelación síncrona desde estado running no deja HTTP bloqueando la cola', async h => {
  const cancel = new AbortController();
  const listener = event => {
    if (event.detail.state === 'running') {
      window.removeEventListener('vertice-engine', listener);
      cancel.abort();
    }
  };
  window.addEventListener('vertice-engine', listener);
  const first = tracked(h.engine.solveGraph({ source: 'A' }, { signal: cancel.signal }));
  const second = tracked(h.engine.solveGraph({ source: 'B' }));
  await first.done;
  await until(() => h.requests.some(request => JSON.parse(request.options.body).source === 'B'),
    'la cancelación previa al fetch debe liberar la cola');
  const active = h.requests.find(request => JSON.parse(request.options.body).source === 'B');
  active.reply({ source: 'B' }); await second.done;
  assert.equal(second.value.source, 'B');
}, 'local');
