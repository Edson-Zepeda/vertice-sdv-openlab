"""VÉRTICE / SDV: Dijkstra orientado a objetos, sin dependencias externas."""

from .graph import Edge, Graph, Node, ValidationError
from .dijkstra import DijkstraSolver
from .codec import solve_json, solve_payload

__all__ = ["Node", "Edge", "Graph", "DijkstraSolver", "ValidationError", "solve_json", "solve_payload"]
__version__ = "1.0.0"
