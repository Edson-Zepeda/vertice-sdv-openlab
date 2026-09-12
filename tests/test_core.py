"""Pruebas de regresión del núcleo, ejecutables con unittest o pytest."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from decimal import Context, Decimal, DefaultContext, Inexact, Rounded, localcontext
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vertice import DijkstraSolver, Edge, Graph, Node, ValidationError, solve_json, solve_payload
from vertice.cli import main
from vertice.codec import load_json


def make_graph(nodes="ABCD", edges=(), directed=False):
    graph = Graph(directed)
    for node in nodes:
        graph.add_node(Node(node))
    for index, (source, target, weight) in enumerate(edges):
        graph.add_edge(Edge(f"e{index}", source, target, weight))
    return graph


class GraphInvariants(unittest.TestCase):
    def test_duplicate_and_missing_references_are_atomic(self):
        graph = make_graph(edges=[("A", "B", "2")])
        before = graph.to_dict()
        for operation in (lambda: graph.add_node(Node("A")),
                          lambda: graph.add_edge(Edge("x", "B", "A", "7")),
                          lambda: graph.add_edge(Edge("e0", "A", "C", "3")),
                          lambda: graph.add_edge(Edge("x", "A", "Z", "1"))):
            with self.assertRaises(ValidationError):
                operation()
            self.assertEqual(graph.to_dict(), before)

    def test_invalid_update_preserves_old_edge_and_adjacency(self):
        graph = make_graph(edges=[("A", "B", 2), ("A", "C", 3)])
        before = graph.to_dict()
        for changes in ({"target": "C"}, {"target": "Z"}, {"weight": "-1"}):
            with self.assertRaises(ValidationError):
                graph.update_edge("e0", **changes)
            self.assertEqual(graph.to_dict(), before)
            self.assertEqual([node for node, _ in graph.neighbors("A")], ["B", "C"])

    def test_rewiring_and_node_removal_rebuild_incidence(self):
        graph = make_graph(edges=[("A", "B", 1), ("B", "C", 2), ("B", "B", 0)])
        graph.update_edge("e0", source="C", target="D", weight="1.25")
        self.assertEqual(graph.neighbors("A"), ())
        self.assertEqual([node for node, _ in graph.neighbors("D")], ["C"])
        graph.remove_node("B")
        self.assertEqual(set(graph.edges), {"e0"})
        self.assertEqual(set(graph.nodes), {"A", "C", "D"})
        self.assertEqual(DijkstraSolver(graph).solve("D", "C")["cost"], "1.25")

    def test_directed_reverse_edge_is_distinct(self):
        graph = make_graph(nodes="AB", edges=[("A", "B", 2), ("B", "A", 7)], directed=True)
        self.assertEqual(DijkstraSolver(graph).solve("A", "B")["cost"], "2")
        self.assertEqual(DijkstraSolver(graph).solve("B", "A")["cost"], "7")
        graph.remove_edge("e0")
        self.assertEqual(DijkstraSolver(graph).solve("A", "B")["status"], "no_path")

    def test_read_only_views_do_not_allow_invariant_bypass(self):
        graph = make_graph(edges=[("A", "B", 2)])
        with self.assertRaises(TypeError):
            graph.nodes["Z"] = Node("Z")
        with self.assertRaises(FrozenInstanceError):
            graph.get_edge("e0").weight = -1
        neighbors = graph.neighbors("A")
        graph.remove_edge("e0")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(graph.neighbors("A"), ())

    def test_export_import_preserves_graph_but_not_mutable_aliases(self):
        original = make_graph(edges=[("A", "A", "0.000001"), ("B", "C", "1000000000000")])
        payload = original.to_dict()
        restored = Graph.from_dict(payload)
        payload["nodes"][0]["label"] = "Cambio externo"
        self.assertEqual(original.to_dict(), restored.to_dict())
        restored.update_node("A", label="Árbol 🟢", x=-10000, y=10000)
        self.assertEqual(original.get_node("A").label, "")

    def test_node_validation_is_explicit(self):
        for node_id in ("", "A B", "ñ", "A" * 41, 3, None):
            with self.subTest(node_id=node_id), self.assertRaises(ValidationError):
                Node(node_id)
        for fields in ({"label": "x" * 81}, {"label": "\ud800"}, {"label": "a\nb"},
                       {"x": True}, {"x": float("nan")}, {"y": Decimal("10000.0000000000000001")}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Node("A", **fields)

    def test_weights_never_round_or_accept_nonfinite(self):
        invalid = (True, None, -1, "-1", "NaN", "Infinity", float("nan"), float("inf"),
                   "0.0000001", "1000000000000.000001", " 1 ", "+1", "01", "1e3")
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Edge("e", "A", "B", value)
        self.assertEqual(Edge("e", "A", "B", "1.23000000").to_dict()["weight"], "1.23")


class DijkstraBehavior(unittest.TestCase):
    def test_lower_cost_can_require_more_edges(self):
        graph = make_graph(edges=[("A", "D", "8"), ("A", "B", "0.1"),
                                  ("B", "C", "0.2"), ("C", "D", "0.3")])
        result = DijkstraSolver(graph).solve("A", "D")
        self.assertEqual(result["path"], ["A", "B", "C", "D"])
        self.assertEqual(result["edge_path"], ["e1", "e2", "e3"])
        self.assertEqual(result["cost"], "0.6")

    def test_decimal_precision_and_traps_are_isolated(self):
        hostile = Context(prec=2, Emax=3, Emin=-3)
        hostile.traps[Inexact] = True
        hostile.traps[Rounded] = True
        with localcontext(hostile):
            graph = make_graph(edges=[("A", "B", "999999999999.999999"),
                                      ("B", "C", "999999999999.999999"),
                                      ("C", "D", "0.000001")])
            result = DijkstraSolver(graph).solve("A", "D")
            self.assertEqual(result["cost"], "1999999999999.999999")

    def test_same_node_is_zero_without_traversal(self):
        graph = make_graph(edges=[("A", "A", "0"), ("A", "B", "5")])
        result = DijkstraSolver(graph).solve("A", "A")
        self.assertEqual((result["status"], result["path"], result["edge_path"], result["cost"]),
                         ("ok", ["A"], [], "0"))
        self.assertEqual(result["settled"], ["A"])
        self.assertIsNone(result["distances"]["B"])

    def test_default_context_mutation_does_not_change_the_engine(self):
        original = DefaultContext.copy()
        try:
            DefaultContext.prec = 1
            DefaultContext.Emax = 2
            DefaultContext.Emin = -2
            DefaultContext.traps[Inexact] = True
            DefaultContext.traps[Rounded] = True
            graph = make_graph(edges=[("A", "B", "999999999999.999999"), ("B", "C", "0.000001")])
            self.assertEqual(DijkstraSolver(graph).solve("A", "C")["cost"], "1000000000000")
        finally:
            for field in ("prec", "rounding", "Emin", "Emax", "capitals", "clamp", "flags", "traps"):
                setattr(DefaultContext, field, getattr(original, field))

    def test_unreachable_target_retains_reachable_distances(self):
        result = DijkstraSolver(make_graph(edges=[("A", "B", 0)])).solve("A", "D")
        self.assertEqual((result["status"], result["path"], result["edge_path"], result["cost"]),
                         ("no_path", [], [], None))
        self.assertEqual(result["distances"], {"A": "0", "B": "0", "C": None, "D": None})

    def test_lazy_heap_discards_stale_entries(self):
        graph = make_graph(edges=[("A", "B", 8), ("A", "C", 1), ("C", "B", 1)], directed=True)
        result = DijkstraSolver(graph).solve("A", "D")
        self.assertEqual(result["settled"], ["A", "C", "B"])
        self.assertEqual(result["stats"]["stale_pops"], 1)
        self.assertEqual([event["node"] for event in result["trace"] if event["kind"] == "stale"], ["B"])

    def test_equal_costs_are_stable_under_input_permutation(self):
        first = make_graph(edges=[("A", "C", 1), ("C", "D", 1), ("A", "B", 1), ("B", "D", 1)])
        payload = first.to_dict()
        payload["nodes"].reverse()
        payload["edges"].reverse()
        second = Graph.from_dict(payload)
        result = DijkstraSolver(first).solve("A", "D")
        self.assertEqual(result["path"], ["A", "B", "D"])
        self.assertEqual(result, DijkstraSolver(second).solve("A", "D"))

    def test_zero_cycle_does_not_create_predecessor_cycle(self):
        graph = make_graph(edges=[("A", "B", 0), ("B", "C", 0), ("C", "A", 0),
                                  ("C", "D", 1)], directed=True)
        result = DijkstraSolver(graph).solve("A", "D")
        self.assertEqual(result["path"], ["A", "B", "C", "D"])
        self.assertEqual(result["cost"], "1")

    def test_early_stop_does_not_claim_all_distances_final(self):
        graph = make_graph(edges=[("A", "B", 1), ("A", "C", 9), ("B", "C", 1)], directed=True)
        result = DijkstraSolver(graph).solve("A", "B")
        self.assertEqual(result["distances"]["C"], "9")
        self.assertNotIn("C", result["settled"])

    def test_trace_is_consistent_and_optional(self):
        solver = DijkstraSolver(make_graph(edges=[("A", "B", 2), ("B", "D", 1)]))
        traced = solver.solve("A", "D")
        plain = solver.solve("A", "D", trace=False)
        self.assertEqual([event["step"] for event in traced["trace"]], list(range(len(traced["trace"]))))
        self.assertEqual(traced["trace"][0]["kind"], "initialize")
        self.assertEqual(traced["trace"][-1]["kind"], "finish")
        self.assertEqual(sum(event["kind"] == "relax" for event in traced["trace"]), traced["stats"]["relaxations"])
        traced["trace"] = []
        self.assertEqual(traced, plain)


class CodecAndTerminal(unittest.TestCase):
    def test_utf8_stdin_preserves_labels_under_windows_legacy_encoding(self):
        graph = make_graph(nodes="AB")
        graph.update_node("A", label="Café 🚗 你好")
        raw = json.dumps(graph.to_dict(), ensure_ascii=False).encode("utf-8")
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "copia.json"
            with patch("sys.stdin", stdin), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["edit", "-", "update-node", "B", "--label", "actualizado",
                                       "--output", str(output)]), 0)
            restored = Graph.from_dict(json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(restored.get_node("A").label, "Café 🚗 你好")
            self.assertEqual(restored.get_node("B").label, "actualizado")

    def test_json_and_payload_share_exact_engine_result(self):
        payload = {"graph": make_graph(edges=[("A", "B", "0.123456")]).to_dict(),
                   "source": "A", "target": "B", "trace": True}
        self.assertEqual(json.loads(solve_json(json.dumps(payload))), solve_payload(payload))

    def test_json_rejects_duplicate_keys_nonfinite_and_bad_structure(self):
        for text in ('{"graph":{},"graph":{}}', '[1,2]', '{"a":NaN}', '{"a":Infinity}',
                     '{"a":-Infinity}', '{bad}', '[[' * 1000 + ']]' * 1000):
            with self.subTest(text=text[:40]), self.assertRaises(ValidationError):
                solve_json(text)
        self.assertEqual(load_json('{"n":0.000001}')["n"], Decimal("0.000001"))

    def test_validation_rejects_unknown_fields_without_mutation(self):
        graph = make_graph().to_dict()
        graph["note"] = "campo no admitido"
        with self.assertRaises(ValidationError):
            Graph.from_dict(graph)
        self.assertIn("note", graph)

    def test_hostile_numeric_tokens_raise_validation_without_expensive_normalization(self):
        for token in ("1e999999999999999999999999999999999", "1e-999999999999999999999999999999999",
                      "0.1" + "0" * 20000, "9" * 5000):
            with self.subTest(token=token[:40]), self.assertRaises(ValidationError):
                load_json('{"n":' + token + '}')
        with self.assertRaises(ValidationError):
            Edge("e", "A", "B", Decimal("0.1" + "0" * 20000))

    def test_error_messages_are_unicode_safe_and_bounded(self):
        for key in ("\ud800", "x" * 20000):
            graph = make_graph().to_dict()
            graph[key] = "unexpected"
            try:
                Graph.from_dict(graph)
            except ValidationError as exc:
                message = str(exc)
                message.encode("utf-8")
                self.assertLess(len(message), 200)
            else:
                self.fail("La clave inesperada debía rechazarse")

    def test_terminal_creates_edits_solves_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "grafo.json")
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(["create", "-o", path]), 0)
                self.assertEqual(main(["edit", path, "add-node", "A", "-o", path, "--overwrite"]), 0)
                self.assertEqual(main(["edit", path, "add-node", "B", "-o", path, "--overwrite"]), 0)
                self.assertEqual(main(["edit", path, "add-edge", "ab", "--source", "A", "--target", "B",
                                       "--weight", "0.125", "-o", path, "--overwrite"]), 0)
                stdout.seek(0)
                stdout.truncate()
                self.assertEqual(main(["solve", path, "-s", "A", "-t", "B", "--json", "--trace"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["cost"], "0.125")
                before = Path(path).read_bytes()
                self.assertEqual(main(["create", "-o", path]), 2)
                self.assertEqual(Path(path).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
