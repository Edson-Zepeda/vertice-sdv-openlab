"""Reference verification only: Bellman-Ford in integer micro-units.

This module never imports the delivered graph, codec or Dijkstra classes.
Its fixtures contain educational graphs, not measured road distances.
"""
from __future__ import annotations

import random
from typing import Any

SCALE = 1_000_000


def micros(value: str | int) -> int:
    """Parse ordinary nonnegative decimal fixture values without float math."""
    text = str(value)
    whole, dot, fraction = text.partition('.')
    fraction = fraction.rstrip('0')
    if len(fraction) > 6 or not whole.isdigit() or (fraction and not fraction.isdigit()):
        raise ValueError(f'Invalid oracle value: {text!r}')
    return int(whole) * SCALE + int(fraction.ljust(6, '0') or '0')


def decimal_text(value: int | None) -> str | None:
    if value is None:
        return None
    whole, fraction = divmod(value, SCALE)
    return str(whole) if not fraction else f'{whole}.{fraction:06d}'.rstrip('0')


def arcs(graph: dict[str, Any]) -> list[tuple[str, str, int, str]]:
    result = []
    for edge in graph['edges']:
        cost = micros(edge['weight'])
        result.append((edge['source'], edge['target'], cost, edge['id']))
        if not graph['directed'] and edge['source'] != edge['target']:
            result.append((edge['target'], edge['source'], cost, edge['id']))
    return result


def bellman_ford(graph: dict[str, Any], source: str) -> dict[str, int | None]:
    """Synchronous relaxation across all arcs, at most |V|-1 rounds.

    Separate previous/current maps make the reference independent of edge order.
    There is no priority queue, settled set, or delivered-code helper.
    """
    distances = {node['id']: None for node in graph['nodes']}
    distances[source] = 0
    edge_list = arcs(graph)
    for _ in range(max(0, len(distances) - 1)):
        previous = distances
        distances = previous.copy()
        for u, v, cost, _ in edge_list:
            if previous[u] is None:
                continue
            candidate = previous[u] + cost
            if distances[v] is None or candidate < distances[v]:
                distances[v] = candidate
        if distances == previous:
            break
    return distances


def floyd_warshall(graph: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    """All-pairs dynamic programming used to cross-check the reference itself."""
    ids = [node['id'] for node in graph['nodes']]
    result = {u: {v: 0 if u == v else None for v in ids} for u in ids}
    for u, v, cost, _ in arcs(graph):
        if result[u][v] is None or cost < result[u][v]:
            result[u][v] = cost
    for middle in ids:
        for source in ids:
            if result[source][middle] is None:
                continue
            for target in ids:
                if result[middle][target] is None:
                    continue
                candidate = result[source][middle] + result[middle][target]
                if result[source][target] is None or candidate < result[source][target]:
                    result[source][target] = candidate
    return result


def graph(nodes: list[str], edges: list[tuple], directed: bool = False) -> dict:
    return {
        'schema_version': 1,
        'directed': directed,
        'nodes': [{'id': node, 'label': node, 'x': (index % 25) * 40, 'y': (index // 25) * 40} for index, node in enumerate(nodes)],
        'edges': [{'id': f'e{index}', 'source': u, 'target': v, 'weight': str(cost)}
                  for index, (u, v, cost) in enumerate(edges)],
    }


def named_cases() -> list[dict]:
    cases = []

    def add(case_id, title, data, source, target, path=None):
        expected = bellman_ford(data, source)[target]
        item = {'id': case_id, 'title': title,
                'payload': {'graph': data, 'source': source, 'target': target, 'trace': True},
                'expected': {'status': 'ok' if expected is not None else 'no_path',
                             'cost': decimal_text(expected)}}
        if path is not None:
            item['expected']['path'] = path
        cases.append(item)

    add('single_node', 'Inicio y destino en el único nodo', graph(['A'], []), 'A', 'A', ['A'])
    add('chain_reverse', 'Una conexión no dirigida se recorre en ambos sentidos',
        graph(['A', 'B', 'C'], [('A', 'B', '2'), ('B', 'C', '3.5')]), 'C', 'A', ['C', 'B', 'A'])
    add('cheaper_detour', 'Más conexiones pueden costar menos',
        graph(['A', 'B', 'C', 'D'], [('A', 'D', '9'), ('A', 'B', '1'), ('B', 'C', '1'), ('C', 'D', '1')]),
        'A', 'D', ['A', 'B', 'C', 'D'])
    add('zero_cycle', 'Ciclo con costo cero y destino alcanzable',
        graph(['A', 'B', 'C', 'D'], [('A', 'B', '0'), ('B', 'C', '0'), ('C', 'A', '0'), ('C', 'D', '2')], True),
        'A', 'D', ['A', 'B', 'C', 'D'])
    add('decimal_exact', '0.1 + 0.2 gana a 0.300001',
        graph(['A', 'B', 'C'], [('A', 'B', '0.1'), ('B', 'C', '0.2'), ('A', 'C', '0.300001')], True),
        'A', 'C', ['A', 'B', 'C'])
    add('micro_delta', 'Diferencia mínima representable',
        graph(['A', 'B', 'C'], [('A', 'C', '0.000003'), ('A', 'B', '0.000001'), ('B', 'C', '0.000001')]),
        'A', 'C', ['A', 'B', 'C'])
    add('large_exact', 'Suma exacta por encima del máximo de una conexión',
        graph(['A', 'B', 'C'], [('A', 'B', '1000000000000'), ('B', 'C', '999999999999.999999')], True),
        'A', 'C', ['A', 'B', 'C'])
    add('directed_no_reverse', 'La dirección impide volver al inicio',
        graph(['A', 'B', 'C'], [('A', 'B', '1'), ('B', 'C', '1')], True), 'C', 'A', [])
    add('disconnected', 'Componentes separadas',
        graph(['A', 'B', 'C', 'D'], [('A', 'B', '1'), ('C', 'D', '1')]), 'A', 'D', [])
    add('isolated_source', 'Inicio sin conexiones',
        graph(['A', 'B', 'C'], [('B', 'C', '1')]), 'A', 'C', [])
    add('isolated_target', 'Destino aislado',
        graph(['A', 'B', 'C'], [('A', 'B', '1')]), 'A', 'C', [])
    add('self_loops', 'Bucles propios de costo cero y positivo',
        graph(['A', 'B'], [('A', 'A', '0'), ('B', 'B', '10'), ('A', 'B', '2')]), 'A', 'B', ['A', 'B'])
    add('same_node_with_edges', 'Inicio igual al destino no requiere recorrer un ciclo',
        graph(['A', 'B'], [('A', 'B', '5'), ('B', 'A', '0')], True), 'A', 'A', ['A'])
    add('deterministic_tie', 'Empate reproducible por identificador local',
        graph(['S', 'B', 'A', 'T'], [('S', 'B', '1'), ('B', 'T', '1'), ('S', 'A', '1'), ('A', 'T', '1')]),
        'S', 'T', ['S', 'A', 'T'])
    add('not_global_lexicographic', 'No se promete el menor camino lexicográfico global',
        graph(['S', 'A', 'B', 'T'], [('S', 'B', '0'), ('B', 'T', '2'), ('S', 'A', '1'), ('A', 'T', '1')], True),
        'S', 'T', ['S', 'B', 'T'])
    add('stale_heap_entry', 'Relajación posterior vuelve obsoleta una entrada de cola',
        graph(['A', 'B', 'C', 'Z'], [('A', 'B', '9'), ('A', 'C', '1'), ('C', 'B', '1')], True), 'A', 'Z', [])
    add('tentative_is_not_final', 'Parada temprana deja una distancia tentativa no óptima',
        graph(['S', 'T', 'X', 'Y'], [('S', 'T', '1'), ('S', 'X', '50'), ('S', 'Y', '2'), ('Y', 'X', '1')], True),
        'S', 'T', ['S', 'T'])
    add('empty_edges', 'Varios nodos sin conexiones', graph(['A', 'B', 'C'], []), 'B', 'A', [])
    return cases


def seeded_graphs(seed: int = 20260912, count: int = 160) -> list[dict]:
    rng = random.Random(seed)
    result = []
    values = ['0', '0.000001', '0.1', '0.2', '1', '2.75', '99.999999', '1000000000000']
    for index in range(count):
        size = rng.randint(2, 18)
        ids = [f'N{i:02d}' for i in range(size)]
        directed = index % 2 == 0
        density = (0.05, 0.2, 0.45, 0.8)[index % 4]
        edges = []
        for i, source in enumerate(ids):
            for j, target in enumerate(ids):
                if not directed and j < i:
                    continue
                if rng.random() < density:
                    edges.append((source, target, rng.choice(values)))
        queries = [(ids[0], ids[-1]), (ids[-1], ids[0]), (rng.choice(ids), rng.choice(ids)), (ids[size // 2], ids[size // 2])]
        # Deduplicate queries so repetition is not counted as another scenario.
        result.append({'id': f'seeded_{index:03d}', 'graph': graph(ids, edges, directed),
                       'queries': list(dict.fromkeys(queries))})
    return result
