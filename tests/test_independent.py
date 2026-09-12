"""Black-box and object-invariant audit derived from the written contract."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, localcontext
import json
from itertools import product
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from independent_oracle import arcs, bellman_ford, decimal_text, floyd_warshall, graph, micros, named_cases, seeded_graphs
from vertice import Edge, Graph, Node, ValidationError
from vertice.codec import solve_json, solve_payload
from vertice.dijkstra import DijkstraSolver

AUDIT_COUNTS = {'named_queries': 0, 'seeded_graphs': 0, 'seeded_queries': 0,
                'exhaustive_graphs': 0, 'exhaustive_queries': 0, 'trace_events': 0}


def request(data=None, source='A', target='B', trace=True):
    return {'graph': data or graph(['A', 'B'], [('A', 'B', '1')]),
            'source': source, 'target': target, 'trace': trace}


class IndependentAlgorithmTests(unittest.TestCase):
    def assert_result(self, payload, result, check_trace=True):
        data, source, target = payload['graph'], payload['source'], payload['target']
        oracle = bellman_ford(data, source)
        expected = oracle[target]
        ids = {node['id'] for node in data['nodes']}
        arc_map = {(u, v, edge): cost for u, v, cost, edge in arcs(data)}
        self.assertEqual(result['status'], 'ok' if expected is not None else 'no_path')
        self.assertEqual(result['source'], source)
        self.assertEqual(result['target'], target)
        self.assertEqual(result['cost'], decimal_text(expected))
        self.assertEqual(set(result['distances']), ids)
        self.assertEqual(len(result['settled']), len(set(result['settled'])))
        self.assertTrue(set(result['settled']) <= ids)
        self.assertEqual(result['settled'][0], source)
        self.assertEqual(result['stats']['settled'], len(result['settled']))
        if expected is None:
            self.assertEqual(result['path'], [])
            self.assertEqual(result['edge_path'], [])
            self.assertNotIn(target, result['settled'])
        else:
            path = result['path']
            self.assertEqual(path[0], source)
            self.assertEqual(path[-1], target)
            self.assertEqual(len(path), len(set(path)), 'A cheapest simple path must not contain a cycle')
            self.assertEqual(len(result['edge_path']), len(path) - 1)
            self.assertEqual(result['settled'][-1], target, 'Stop only after settling the destination')
            total = 0
            for u, v, edge in zip(path, path[1:], result['edge_path']):
                self.assertIn((u, v, edge), arc_map, 'Reported path must use real edges in the allowed direction')
                total += arc_map[u, v, edge]
            self.assertEqual(total, expected)
        settled_costs = []
        for node, distance in result['distances'].items():
            if node in result['settled']:
                self.assertEqual(distance, decimal_text(oracle[node]), f'Only settled distances are definitive: {node}')
                settled_costs.append(micros(distance))
            elif distance is not None:
                self.assertIsNotNone(oracle[node])
                self.assertGreaterEqual(micros(distance), oracle[node], 'Tentative estimates cannot undercut the optimum')
        ordered_costs = [micros(result['distances'][node]) for node in result['settled']]
        self.assertEqual(ordered_costs, sorted(ordered_costs))
        for key, value in result['stats'].items():
            self.assertIsInstance(value, int, key)
            self.assertGreaterEqual(value, 0, key)
        self.assertEqual(result['stats']['heap_pops'], len(result['settled']) + result['stats']['stale_pops'])
        self.assertEqual(result['stats']['heap_pushes'], result['stats']['relaxations'] + 1)
        # Serialization must reject non-standard floating-point literals in any field.
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        if check_trace:
            self.assert_trace(payload, result, arc_map)

    def assert_trace(self, payload, result, arc_map):
        events = result['trace']
        self.assertTrue(events)
        self.assertEqual(events[0]['kind'], 'initialize')
        self.assertEqual(events[-1]['kind'], 'finish')
        self.assertEqual(events[-1]['status'], result['status'])
        known = {node['id']: None for node in payload['graph']['nodes']}
        known[payload['source']] = 0
        settled = []
        relaxations = 0
        stale = 0
        current = None
        considered = set()
        for index, event in enumerate(events):
            self.assertEqual(event['step'], index)
            kind = event['kind']
            self.assertIn(kind, ('initialize', 'settle', 'consider', 'relax', 'stale', 'finish'))
            if kind == 'settle':
                node = event['node']
                self.assertNotIn(node, settled)
                self.assertEqual(micros(event['cost']), known[node])
                frontier = [(cost, candidate) for candidate, cost in known.items()
                            if candidate not in settled and cost is not None]
                self.assertEqual((known[node], node), min(frontier), 'Settle the current minimum, then ID for ties')
                settled.append(node)
                current = node
            elif kind in ('consider', 'relax'):
                u, v, edge = event['source'], event['target'], event['edge']
                self.assertEqual(u, current)
                self.assertIn(u, settled)
                self.assertIn((u, v, edge), arc_map)
                if kind == 'consider':
                    self.assertNotIn((u, v, edge), considered)
                    considered.add((u, v, edge))
                    self.assertEqual(event['old_cost'], decimal_text(known[v]))
                    self.assertEqual(micros(event['new_cost']), known[u] + arc_map[u, v, edge])
                if kind == 'relax':
                    self.assertNotIn(v, settled, 'A settled estimate must never be relaxed again')
                    old, new = event['old_cost'], micros(event['new_cost'])
                    self.assertEqual(old, decimal_text(known[v]))
                    self.assertEqual(new, known[u] + arc_map[u, v, edge])
                    self.assertTrue(known[v] is None or new < known[v])
                    known[v] = new
                    relaxations += 1
            elif kind == 'stale':
                stale += 1
                self.assertIn(event['node'], known)
                self.assertTrue(event['node'] in settled or micros(event['cost']) > known[event['node']])
            elif kind == 'initialize':
                self.assertEqual(index, 0)
            elif kind == 'finish':
                self.assertEqual(index, len(events) - 1)
        self.assertEqual(settled, result['settled'])
        self.assertEqual({node: decimal_text(cost) for node, cost in known.items()}, result['distances'])
        self.assertEqual(relaxations, result['stats']['relaxations'])
        self.assertEqual(stale, result['stats']['stale_pops'])
        # Each arc is considered at most once; each consideration relaxes at most once.
        self.assertLessEqual(len(events), 2 + len(known) + 3 * len(arc_map))
        AUDIT_COUNTS['trace_events'] += len(events)

    def test_named_contract_scenarios(self):
        for case in named_cases():
            with self.subTest(case=case['id']):
                result = solve_payload(copy.deepcopy(case['payload']))
                self.assert_result(case['payload'], result)
                if 'path' in case['expected']:
                    self.assertEqual(result['path'], case['expected']['path'])
                AUDIT_COUNTS['named_queries'] += 1

    def test_seeded_graphs_against_independent_oracle(self):
        for fixture in seeded_graphs():
            for source, target in fixture['queries']:
                with self.subTest(graph=fixture['id'], source=source, target=target):
                    payload = request(fixture['graph'], source, target)
                    self.assert_result(payload, solve_payload(copy.deepcopy(payload)))
                    AUDIT_COUNTS['seeded_queries'] += 1
            AUDIT_COUNTS['seeded_graphs'] += 1

    def test_oracle_cross_check_with_floyd_warshall(self):
        # This validates reference calculations, not an extra product pass per pair.
        for fixture in seeded_graphs(count=40):
            expected = floyd_warshall(fixture['graph'])
            for source, _ in fixture['queries']:
                self.assertEqual(bellman_ford(fixture['graph'], source), expected[source])

    def test_exhaustive_three_node_directed_graphs(self):
        ids = ['A', 'B', 'C']
        pairs = [(source, target) for source in ids for target in ids if source != target]
        # Exactly 3^6 graphs: each possible directed arc is absent, zero or one.
        # Self loops are exercised separately; this bounded domain is not a general proof.
        for configuration in product((None, '0', '1'), repeat=len(pairs)):
            edges = [(source, target, weight) for (source, target), weight in zip(pairs, configuration)
                     if weight is not None]
            data = graph(ids, edges, True)
            for source, target in product(ids, repeat=2):
                with self.subTest(configuration=configuration, source=source, target=target):
                    payload = request(data, source, target)
                    self.assert_result(payload, solve_payload(payload))
                    AUDIT_COUNTS['exhaustive_queries'] += 1
            AUDIT_COUNTS['exhaustive_graphs'] += 1

    def test_positive_scaling_preserves_unique_route(self):
        payload = copy.deepcopy(named_cases()[2]['payload'])
        original = solve_payload(payload)
        for edge in payload['graph']['edges']:
            edge['weight'] = decimal_text(micros(edge['weight']) * 7)
        scaled = solve_payload(payload)
        self.assertEqual(scaled['path'], original['path'])
        self.assertEqual(micros(scaled['cost']), micros(original['cost']) * 7)

    def test_disconnected_extension_cannot_change_existing_solution(self):
        payload = copy.deepcopy(named_cases()[4]['payload'])
        original = solve_payload(payload)
        payload['graph']['nodes'].extend([{'id': 'X'}, {'id': 'Y'}])
        payload['graph']['edges'].append({'id': 'xy', 'source': 'X', 'target': 'Y', 'weight': '0'})
        extended = solve_payload(payload)
        self.assertEqual((extended['cost'], extended['path']), (original['cost'], original['path']))
        self.assertEqual(extended['distances']['X'], None)

    def test_bijective_renaming_preserves_optimal_cost(self):
        payload = copy.deepcopy(named_cases()[13]['payload'])
        before = solve_payload(payload)
        mapping = {'S': 'z', 'A': 'y', 'B': 'a', 'T': 'b'}
        for node in payload['graph']['nodes']:
            node['id'] = mapping[node['id']]
        for edge in payload['graph']['edges']:
            edge['source'], edge['target'] = mapping[edge['source']], mapping[edge['target']]
        payload['source'], payload['target'] = mapping[payload['source']], mapping[payload['target']]
        self.assertEqual(solve_payload(payload)['cost'], before['cost'])

    def test_tentative_distance_is_not_replaced_by_final_oracle_value(self):
        case = next(case for case in named_cases() if case['id'] == 'tentative_is_not_final')
        result = solve_payload(case['payload'])
        self.assertEqual(result['settled'], ['S', 'T'])
        self.assertEqual(result['distances']['X'], '50')
        self.assertEqual(bellman_ford(case['payload']['graph'], 'S')['X'], 3_000_000)

    def test_input_order_does_not_change_tie_route_or_trace(self):
        case = next(case for case in named_cases() if case['id'] == 'deterministic_tie')
        payload = copy.deepcopy(case['payload'])
        expected = solve_payload(payload)
        payload['graph']['nodes'].reverse()
        payload['graph']['edges'].reverse()
        self.assertEqual(solve_payload(payload), expected)

    def test_solve_does_not_mutate_input_and_results_are_isolated(self):
        payload = copy.deepcopy(named_cases()[2]['payload'])
        original = copy.deepcopy(payload)
        result = solve_payload(payload)
        result['path'].clear()
        result['distances']['A'] = '999'
        self.assertEqual(payload, original)
        self.assertEqual(solve_payload(payload)['cost'], '3')
        self.assertEqual(solve_payload(payload)['path'], ['A', 'B', 'C', 'D'])

    def test_trace_disabled_keeps_same_solution_without_events(self):
        payload = copy.deepcopy(named_cases()[5]['payload'])
        with_trace = solve_payload(payload)
        payload['trace'] = False
        without_trace = solve_payload(payload)
        self.assertEqual(without_trace['trace'], [])
        self.assertEqual({k: v for k, v in with_trace.items() if k != 'trace'},
                         {k: v for k, v in without_trace.items() if k != 'trace'})

    def test_decimal_context_cannot_change_route_or_cost(self):
        payload = copy.deepcopy(next(case for case in named_cases() if case['id'] == 'large_exact')['payload'])
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = True
            result = solve_payload(payload)
        self.assertEqual(result['cost'], '1999999999999.999999')

    def test_decimal_context_cannot_erase_micro_difference(self):
        data = graph(['A', 'B', 'C'], [('A', 'C', '999999999999.999999'),
                                     ('A', 'B', '999999999999.999997'), ('B', 'C', '0.000001')], True)
        with localcontext() as context:
            context.prec = 4
            result = solve_payload(request(data, 'A', 'C'))
        self.assertEqual(result['cost'], '999999999999.999998')
        self.assertEqual(result['path'], ['A', 'B', 'C'])

    def test_json_round_trip_preserves_exact_decimal_result(self):
        for case in named_cases():
            with self.subTest(case=case['id']):
                encoded = json.dumps(case['payload'], ensure_ascii=False, allow_nan=False)
                self.assertEqual(json.loads(solve_json(encoded)), solve_payload(case['payload']))


class ValidationBoundaryTests(unittest.TestCase):
    def assert_bad(self, payload):
        with self.assertRaises(ValidationError):
            solve_payload(payload)

    def test_invalid_weights_are_explicitly_rejected(self):
        bad_weights = [-1, '-0.000001', True, False, None, float('nan'), float('inf'),
                       float('-inf'), 'NaN', 'Infinity', '1e3', ' 1', '1 ', '+1', '', '.',
                       '0.0000001', '1000000000000.000001', {}, [], '9' * 10000]
        for weight in bad_weights:
            with self.subTest(weight=repr(weight)[:80]):
                payload = request()
                payload['graph']['edges'][0]['weight'] = weight
                self.assert_bad(payload)

    def test_precisely_representable_weight_variants(self):
        for weight, expected in [(0, '0'), (1.25, '1.25'), ('1.2500000', '1.25'),
                                 (Decimal('0.000001'), '0.000001'), ('1000000000000', '1000000000000')]:
            with self.subTest(weight=weight):
                payload = request()
                payload['graph']['edges'][0]['weight'] = weight
                self.assertEqual(solve_payload(payload)['cost'], expected)

    def test_coordinate_bounds_and_types(self):
        for coordinate in [float('nan'), float('inf'), -10000.0001, 10000.0001, True, '42', None]:
            for axis in ('x', 'y'):
                with self.subTest(coordinate=coordinate, axis=axis):
                    payload = request()
                    payload['graph']['nodes'][0][axis] = coordinate
                    self.assert_bad(payload)
        for coordinate in (-10000, 10000, 0.25):
            payload = request()
            payload['graph']['nodes'][0]['x'] = coordinate
            self.assertEqual(solve_payload(payload)['cost'], '1')

    def test_node_and_edge_identifier_contract(self):
        for invalid in ['', 'a' * 41, 'A B', '../A', '<script>', 'á', True, 7, None]:
            with self.subTest(identifier=invalid):
                payload = request()
                payload['graph']['nodes'][0]['id'] = invalid
                self.assert_bad(payload)
                payload = request()
                payload['graph']['edges'][0]['id'] = invalid
                self.assert_bad(payload)

    def test_duplicate_nodes_edges_and_parallel_connections(self):
        mutations = [
            lambda g: g['nodes'].append(copy.deepcopy(g['nodes'][0])),
            lambda g: g['edges'].append(copy.deepcopy(g['edges'][0])),
            lambda g: g['edges'].append({'id': 'other', 'source': 'A', 'target': 'B', 'weight': '2'}),
            lambda g: g['edges'].append({'id': 'reverse', 'source': 'B', 'target': 'A', 'weight': '2'}),
        ]
        for mutation in mutations:
            payload = request()
            mutation(payload['graph'])
            self.assert_bad(payload)
        directed = request(graph(['A', 'B'], [('A', 'B', '1'), ('B', 'A', '2')], True))
        self.assertEqual(solve_payload(directed)['cost'], '1')

    def test_nonexistent_endpoints(self):
        for field in ('source', 'target'):
            payload = request()
            payload[field] = 'MISSING'
            self.assert_bad(payload)
            payload = request()
            payload['graph']['edges'][0][field] = 'MISSING'
            self.assert_bad(payload)

    def test_top_level_and_required_field_types(self):
        for value in (None, [], 'text', 0, True):
            self.assert_bad(value)
        for key in ('graph', 'source', 'target'):
            payload = request()
            del payload[key]
            self.assert_bad(payload)
        for value in ('true', 1, None, []):
            payload = request()
            payload['trace'] = value
            self.assert_bad(payload)
        for key, invalid in [('schema_version', True), ('schema_version', 2), ('directed', 'false'),
                             ('directed', 0), ('nodes', {}), ('edges', None)]:
            payload = request()
            payload['graph'][key] = invalid
            self.assert_bad(payload)

    def test_unicode_labels_remain_data_and_enforce_length(self):
        payload = request()
        payload['graph']['nodes'][0]['label'] = 'Ruta café 🚗 <script>alert(1)</script>'
        self.assertEqual(solve_payload(payload)['cost'], '1')
        payload['graph']['nodes'][0]['label'] = 'á' * 81
        self.assert_bad(payload)

    def test_unpaired_surrogate_cannot_break_utf8_responses(self):
        payload = request()
        payload['graph']['nodes'][0]['label'] = '\ud800'
        self.assert_bad(payload)

    def test_json_parser_rejects_duplicates_and_nonstandard_numbers(self):
        encoded = json.dumps(request())
        malformed = ['null', '[]', 'true', '7', '"text"', '{', encoded + '{}',
                     encoded.replace('"trace": true', '"trace": true, "trace": false'),
                     encoded.replace('"weight": "1"', '"weight": "1", "weight": "2"'),
                     encoded.replace('"weight": "1"', '"weight": NaN'),
                     encoded.replace('"weight": "1"', '"weight": Infinity')]
        for value in malformed:
            with self.subTest(value=value[:100]):
                with self.assertRaises(ValidationError):
                    solve_json(value)

    def test_extreme_json_has_controlled_validation_error(self):
        for value in ('[' * 1200 + '0' + ']' * 1200,
                      '{"graph":' + '9' * 10000 + '}',
                      '{"graph":' + ' ' * 2_100_000 + 'null}'):
            with self.assertRaises(ValidationError):
                solve_json(value)

    def test_extreme_decimal_exponents_are_controlled(self):
        encoded = json.dumps(request())
        for token in ('1e999999999999999999999999999999999', '1e-999999999999999999999999999999999'):
            with self.subTest(token=token):
                with self.assertRaises(ValidationError):
                    solve_json(encoded.replace('"weight": "1"', '"weight": ' + token))

    def test_oversized_numeric_representation_is_rejected_before_normalization(self):
        encoded = json.dumps(request())
        token = '0.1' + '0' * 20_000
        with self.assertRaises(ValidationError):
            solve_json(encoded.replace('"weight": "1"', '"weight": ' + token))
        payload = request()
        payload['graph']['edges'][0]['weight'] = Decimal(token)
        self.assert_bad(payload)

    def test_error_messages_for_unexpected_keys_are_utf8_safe(self):
        payload = request()
        payload['\ud800'] = 'unexpected'
        try:
            solve_payload(payload)
        except ValidationError as exc:
            str(exc).encode('utf-8')
        else:
            self.fail('Unexpected fields must be rejected')

    def test_maximum_nodes_and_one_beyond(self):
        ids = [f'N{i}' for i in range(500)]
        data = graph(ids, [(ids[i], ids[i + 1], '1000000000000') for i in range(499)], True)
        result = solve_payload(request(data, ids[0], ids[-1], False))
        self.assertEqual(result['cost'], '499000000000000')
        data['nodes'].append({'id': 'overflow', 'label': '', 'x': 0, 'y': 0})
        self.assert_bad(request(data, ids[0], ids[-1], False))

    def test_maximum_edges_and_one_beyond(self):
        ids = [f'N{i}' for i in range(65)]
        pairs = [(a, b, '0') for a in ids for b in ids if a != b]
        data = graph(ids, pairs[:4000], True)
        self.assertEqual(solve_payload(request(data, ids[0], ids[-1], False))['cost'], '0')
        data['edges'].append({'id': 'overflow', 'source': pairs[4000][0], 'target': pairs[4000][1], 'weight': '0'})
        self.assert_bad(request(data, ids[0], ids[-1], False))


class GraphMutationTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph.from_dict(graph(['A', 'B', 'C'], [('A', 'B', '1'), ('B', 'C', '1'), ('A', 'C', '9')]))

    def test_removing_node_removes_all_incident_edges(self):
        self.graph.remove_node('B')
        self.assertEqual(set(self.graph.nodes), {'A', 'C'})
        self.assertEqual(set(self.graph.edges), {'e2'})
        self.assertEqual(DijkstraSolver(self.graph).solve('A', 'C')['cost'], '9')
        self.assertTrue(all(neighbor != 'B' for neighbor, _ in self.graph.neighbors('A')))

    def test_edge_weight_update_changes_solution(self):
        self.graph.update_edge('e2', weight='0.5')
        result = DijkstraSolver(self.graph).solve('A', 'C')
        self.assertEqual(result['cost'], '0.5')
        self.assertEqual(result['edge_path'], ['e2'])

    def test_edge_rewire_updates_both_undirected_adjacencies(self):
        self.graph.add_node(Node('D', 'Destino', 5, 5))
        self.graph.update_edge('e2', source='D', target='C', weight='1')
        self.assertEqual(DijkstraSolver(self.graph).solve('A', 'D')['path'], ['A', 'B', 'C', 'D'])
        self.assertNotIn('D', [neighbor for neighbor, _ in self.graph.neighbors('A')])
        self.assertIn('C', [neighbor for neighbor, _ in self.graph.neighbors('D')])
        self.assertIn('D', [neighbor for neighbor, _ in self.graph.neighbors('C')])

    def test_failed_mutations_are_atomic(self):
        for mutation in (
            lambda: self.graph.update_edge('e2', source='MISSING', weight='0'),
            lambda: self.graph.update_edge('e2', source='A', target='B'),
            lambda: self.graph.update_edge('e2', weight='-1'),
            lambda: self.graph.update_node('A', label='changed', x=float('nan')),
            lambda: self.graph.add_node(Node('A')),
            lambda: self.graph.add_edge(Edge('other', 'A', 'B', '3')),
        ):
            before = self.graph.to_dict()
            with self.assertRaises(ValidationError):
                mutation()
            self.assertEqual(self.graph.to_dict(), before)
            self.assertEqual(DijkstraSolver(self.graph).solve('A', 'C')['cost'], '2')

    def test_node_update_does_not_change_routes(self):
        self.graph.update_node('A', label='Nuevo nombre', x=-10, y=20)
        self.assertEqual(self.graph.get_node('A').label, 'Nuevo nombre')
        self.assertEqual(DijkstraSolver(self.graph).solve('A', 'C')['cost'], '2')

    def test_external_views_and_value_objects_cannot_corrupt_graph(self):
        with self.assertRaises(TypeError):
            self.graph.nodes['X'] = Node('X')
        with self.assertRaises(TypeError):
            self.graph.edges['X'] = Edge('X', 'A', 'C', '0')
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            self.graph.get_edge('e0').weight = Decimal('0')
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            self.graph.get_node('A').id = 'X'
        exported = self.graph.to_dict()
        exported['nodes'][0]['id'] = 'X'
        exported['edges'].clear()
        self.assertEqual(DijkstraSolver(self.graph).solve('A', 'C')['cost'], '2')

    def test_remove_and_readd_uses_new_weight(self):
        self.graph.remove_edge('e2')
        self.graph.add_edge(Edge('e2', 'A', 'C', '0'))
        self.assertEqual(DijkstraSolver(self.graph).solve('A', 'C')['cost'], '0')

    def test_directed_remove_and_rewire_do_not_leave_reverse_arcs(self):
        directed = Graph.from_dict(graph(['A', 'B', 'C'], [('A', 'B', '1'), ('B', 'A', '2')], True))
        directed.update_edge('e0', source='B', target='C')
        self.assertEqual(directed.neighbors('A'), ())
        self.assertEqual(DijkstraSolver(directed).solve('A', 'C')['status'], 'no_path')
        directed.remove_node('B')
        self.assertEqual(len(directed.edges), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
