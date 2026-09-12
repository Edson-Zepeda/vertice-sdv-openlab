/* Summarize recorded UI work without treating elapsed time alone as a pass. */
const fs = require('node:fs');
const path = require('node:path');
const ROOT = path.resolve(__dirname, '..');
const name = process.argv[2] || 'soak';
if (!/^[a-z0-9_-]+$/i.test(name)) throw new Error('Use a simple evidence directory name.');
const directory = path.join(ROOT, 'evidence', 'ui', name);
const report = JSON.parse(fs.readFileSync(path.join(directory, 'report.json'), 'utf8'));
const rawLines = fs.readFileSync(path.join(directory, 'activity.jsonl'), 'utf8').split(/\r?\n/).filter(Boolean);
const records = rawLines.map((line) => JSON.parse(line));
const successfulActions = records.filter((record) => record.passed === true);
const isSolve = (record) => /compute|run medium-density browser solve/i.test(record.action);
const allSolves = successfulActions.filter(isSolve);
const median = (values) => {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
};
const range = (values) => values.length ? { minimum: Math.min(...values), maximum: Math.max(...values) } : null;
const hashesEqual = report.code_hashes_after && Object.entries(report.code_hashes).every(([file, hash]) => report.code_hashes_after[file] === hash);
const countsMatch = successfulActions.length === report.actions && allSolves.length === report.solves;
const durationReached = Number.isFinite(report.elapsed_minutes) && report.elapsed_minutes >= report.requested_minutes;
const completed = report.completed === true && !report.interrupted && report.failures.length === 0 && hashesEqual && countsMatch && durationReached;
const summary = {
  generated_at: new Date().toISOString(),
  source: `evidence/ui/${name}/report.json`,
  status: completed ? 'completed_without_recorded_failure' : report.interrupted ? 'deliberately_interrupted' : report.finished_at ? 'incomplete_or_failed' : 'in_progress',
  started_at: report.started_at,
  finished_at: report.finished_at || null,
  requested_minutes: report.requested_minutes,
  elapsed_minutes: report.elapsed_minutes || null,
  actions: successfulActions.length,
  cycles: report.cycles,
  real_python_solves: allSolves.length,
  journal_matches_report_counts: countsMatch,
  initial_and_final_source_hashes_match: !!hashesEqual,
  failures: report.failures,
  interruption: report.interruption || null,
  phases: report.phases.map((phase) => {
    const actions = successfulActions.filter((record) => record.phase === phase.name);
    const solves = actions.filter(isSolve);
    const checkpoints = report.checkpoints.filter((point) => point.phase === phase.name);
    return {
      name: phase.name,
      engine: phase.engine,
      actions: actions.length,
      real_python_solves: solves.length,
      solve_action_latency_ms: { median: median(solves.map((record) => record.elapsed_ms)), ...range(solves.map((record) => record.elapsed_ms)) },
      renderer_heap_after_gc_bytes: range(checkpoints.map((point) => point.javascript_heap_bytes_after_gc)),
      renderer_documents: range(checkpoints.map((point) => point.documents)),
      observations: checkpoints.map((point) => ({
        elapsed_minutes: point.elapsed_minutes,
        graph_nodes: point.graph_nodes ?? null,
        graph_edges: point.graph_edges ?? null,
        live_elements: point.live_elements ?? null,
        dom_nodes: point.dom_nodes,
        event_listeners: point.event_listeners,
      })),
    };
  }),
  limits: [
    'Solve-action latency includes the UI action, real engine result, rendering and the engine-mode verification; it is not pure algorithm time.',
    'The first browser solve includes Python/Wasm initialization; compare warmed runs separately.',
    'CDP metrics cover the main UI renderer, not direct worker/Wasm or whole-process memory.',
    'Graphs, panel state and viewport vary by phase; raw DOM and listener counts are not directly comparable between different graph states.',
    'A completed run only supports the exercised workflows on the recorded environment and does not prove absence of every memory leak or accessibility issue.',
  ],
};
fs.writeFileSync(path.join(directory, 'analysis.json'), JSON.stringify(summary, null, 2) + '\n');
const columns = ['elapsed_minutes', 'phase', 'actions', 'cycles', 'solves', 'javascript_heap_bytes_after_gc', 'dom_nodes', 'live_elements', 'graph_nodes', 'graph_edges', 'documents', 'event_listeners', 'solve_last_50_median_ms', 'solve_last_50_max_ms'];
const csv = [columns.join(','), ...report.checkpoints.map((point) => columns.map((key) => point[key] ?? '').join(','))].join('\n') + '\n';
fs.writeFileSync(path.join(directory, 'checkpoints.csv'), csv);
console.log(JSON.stringify({ status: summary.status, actions: summary.actions, solves: summary.real_python_solves, countsMatch, hashesEqual: !!hashesEqual, output: path.join(directory, 'analysis.json') }));
