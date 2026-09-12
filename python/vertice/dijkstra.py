"""Dijkstra propio con cola mínima y trazas de las operaciones ejecutadas."""

from __future__ import annotations

from decimal import Decimal, localcontext
import heapq

from .graph import Graph, ValidationError, canonical_decimal, _decimal_context


class DijkstraSolver:
    """Resuelve sobre un Graph; no almacena estado de búsquedas anteriores."""

    def __init__(self, graph: Graph) -> None:
        if not isinstance(graph, Graph):
            raise ValidationError("DijkstraSolver requiere un objeto Graph.")
        self.graph = graph

    def solve(self, source: str, target: str, trace: bool = True) -> dict:
        self.graph.get_node(source)
        self.graph.get_node(target)
        if type(trace) is not bool:
            raise ValidationError("trace debe ser true o false.")
        # Como máximo 500 vértices y pesos <= 10^12 con 6 decimales:
        # una suma candidata requiere menos de 22 cifras significativas.
        # Context propio evita heredar precisión, redondeo o trampas externas.
        with localcontext(_decimal_context()):
            return self._solve(source, target, trace)

    def _solve(self, source: str, target: str, trace: bool) -> dict:
        distances: dict[str, Decimal | None] = {node: None for node in sorted(self.graph.nodes)}
        predecessors: dict[str, tuple[str, str]] = {}
        settled: list[str] = []
        closed: set[str] = set()
        events: list[dict] = []
        stats = {"settled": 0, "relaxations": 0, "heap_pushes": 1,
                 "heap_pops": 0, "stale_pops": 0}

        def decimal_or_none(value: Decimal | None) -> str | None:
            return None if value is None else canonical_decimal(value)

        def emit(kind: str, **fields) -> None:
            if trace:
                events.append({"step": len(events), "kind": kind, **fields})

        distances[source] = Decimal(0)
        heap: list[tuple[Decimal, str]] = [(Decimal(0), source)]
        emit("initialize", node=source, source=source, target=target, cost="0")
        while heap:
            cost, node = heapq.heappop(heap)
            stats["heap_pops"] += 1
            if node in closed or cost != distances[node]:
                stats["stale_pops"] += 1
                emit("stale", node=node, cost=canonical_decimal(cost),
                     new_cost=decimal_or_none(distances[node]))
                continue
            closed.add(node)
            settled.append(node)
            stats["settled"] += 1
            emit("settle", node=node, cost=canonical_decimal(cost))
            if node == target:
                break
            for neighbor, edge in self.graph.neighbors(node):
                candidate = cost + edge.weight
                previous = distances[neighbor]
                emit("consider", source=node, target=neighbor, edge=edge.id,
                     old_cost=decimal_or_none(previous), new_cost=canonical_decimal(candidate))
                if neighbor in closed or (previous is not None and candidate >= previous):
                    continue
                distances[neighbor] = candidate
                predecessors[neighbor] = (node, edge.id)
                heapq.heappush(heap, (candidate, neighbor))
                stats["heap_pushes"] += 1
                stats["relaxations"] += 1
                emit("relax", source=node, target=neighbor, edge=edge.id,
                     old_cost=decimal_or_none(previous), new_cost=canonical_decimal(candidate))

        path: list[str] = []
        edge_path: list[str] = []
        found = target in closed
        if found:
            cursor = target
            path.append(cursor)
            while cursor != source:
                cursor, edge_id = predecessors[cursor]
                path.append(cursor)
                edge_path.append(edge_id)
            path.reverse()
            edge_path.reverse()
        status = "ok" if found else "no_path"
        final_cost = decimal_or_none(distances[target]) if found else None
        emit("finish", node=target, status=status, cost=final_cost)
        return {"status": status, "source": source, "target": target,
                "path": path, "edge_path": edge_path, "cost": final_cost,
                "distances": {node: decimal_or_none(value) for node, value in distances.items()},
                "settled": settled, "trace": events, "stats": stats}
