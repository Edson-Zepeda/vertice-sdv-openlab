"""Regression checks for the production JSON allocation boundary."""
from __future__ import annotations

from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from vertice import Graph, ValidationError
from vertice.codec import (MAX_JSON_BYTES, MAX_JSON_CONTAINERS, MAX_JSON_PUNCTUATION,
                           load_json, solve_json)


def maximum_graph(label):
    """Largest legal schema, with all optional fields and unique directed arcs."""
    return {
        "schema_version": 1, "directed": True,
        "nodes": [{"id": f"N{i:03}", "label": label, "x": i, "y": -i} for i in range(500)],
        "edges": [{"id": f"E{i}_{step}", "source": f"N{i:03}",
                   "target": f"N{(i + step) % 500:03}", "weight": "0.000001"}
                  for i in range(500) for step in range(1, 9)],
    }


class JsonStructureGuardTests(unittest.TestCase):
    def test_maximum_graph_accepts_labels_that_force_slow_scan(self):
        for label in ("[" * 80, "," * 80, '🧭[{,:}]\\"' * 8):
            with self.subTest(label=repr(label[:12])):
                graph = maximum_graph(label)
                raw = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
                # These strings must trigger the slower branch, while their
                # punctuation remains valid label data rather than structure.
                self.assertTrue(raw.count("[") + raw.count("{") > MAX_JSON_CONTAINERS
                                or raw.count(",") + raw.count(":") > MAX_JSON_PUNCTUATION)
                restored = Graph.from_dict(load_json(raw))
                self.assertEqual(len(restored.nodes), 500)
                self.assertEqual(len(restored.edges), 4000)
                self.assertEqual(restored.get_node("N499").label, label)
                request = json.dumps({"graph": graph, "source": "N000", "target": "N499", "trace": False}, ensure_ascii=False)
                self.assertEqual(json.loads(solve_json(request))["cost"], "0.000063")

    def test_container_limit_accepts_boundary_rejects_one_more_before_decoder(self):
        at_limit = "[" + ",".join(["{}"] * (MAX_JSON_CONTAINERS - 1)) + "]"
        self.assertEqual(len(load_json(at_limit)), MAX_JSON_CONTAINERS - 1)
        over = "[" + ",".join(["{}"] * MAX_JSON_CONTAINERS) + "]"
        with patch("vertice.codec.json.loads") as decoder:
            with self.assertRaisesRegex(ValidationError, "estructura"):
                load_json(over)
            decoder.assert_not_called()

    def test_punctuation_limit_accepts_boundary_rejects_one_more_before_decoder(self):
        at_limit = "[" + ",".join(["0"] * (MAX_JSON_PUNCTUATION + 1)) + "]"
        self.assertEqual(len(load_json(at_limit)), MAX_JSON_PUNCTUATION + 1)
        over = "[" + ",".join(["0"] * (MAX_JSON_PUNCTUATION + 2)) + "]"
        with patch("vertice.codec.json.loads") as decoder:
            with self.assertRaisesRegex(ValidationError, "campos"):
                load_json(over)
            decoder.assert_not_called()

    def test_brackets_and_escaped_quotes_inside_strings_are_not_structure(self):
        for value in ('[{,:}]' * 10000, '\\"' * 10000 + '[' * 6000,
                      '"' * 8000 + ',' * 50001, '\\' * 8001 + '{' * 6000,
                      '🧭漢字\\"[{,:' * 7000):
            for ascii_only in (True, False):
                with self.subTest(prefix=repr(value[:10]), ascii=ascii_only):
                    raw = json.dumps({"value": value}, ensure_ascii=ascii_only)
                    self.assertEqual(load_json(raw), {"value": value})

    def test_existing_syntax_and_duplicate_errors_survive_slow_scan(self):
        noisy_value = json.dumps("[" * 6000)
        for raw, message in ((f'{{"label":{noisy_value},"x":0,"x":1}}', "repite"),
                             (f'{{"label":{noisy_value},"x":NaN}}', "finito"),
                             (f'{{"label":{noisy_value},"x":Infinity}}', "finito"),
                             (f'{{"label":{noisy_value},"x":1e99999999999999999999999999999999}}', "exponente"),
                             (f'{{"label":{noisy_value},"x":' + "1" * 101 + "}", "100"),
                             ('"' + "[" * 6000, "JSON inválido")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValidationError, message):
                    load_json(raw)

    def test_decimal_reading_remains_exact_on_slow_scan(self):
        raw = '{"noise":' + json.dumps("[" * 6000) + ',"a":0.1,"b":0.2,"micro":1e-6}'
        data = load_json(raw)
        self.assertEqual(data["a"] + data["b"], Decimal("0.3"))
        self.assertEqual(data["micro"], Decimal("0.000001"))

    def test_utf8_and_byte_limit_run_before_structural_scan(self):
        for raw, message in (("\ud800", "Unicode"),
                             ('"' + "🧭" * (MAX_JSON_BYTES // 4) + '"', "2 MiB")):
            with self.subTest(message=message):
                with patch("vertice.codec._guard_json_structure") as guard:
                    with self.assertRaisesRegex(ValidationError, message):
                        load_json(raw)
                    guard.assert_not_called()

    def test_small_nested_invalid_input_remains_controlled(self):
        # Decoder recursion limits vary between Python versions. The public
        # request still rejects this via parser limits OR the request schema.
        with self.assertRaises(ValidationError):
            solve_json("[" * 1500 + "]" * 1500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
