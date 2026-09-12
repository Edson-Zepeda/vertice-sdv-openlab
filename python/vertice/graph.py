"""Objetos del grafo e invariantes. No requiere bibliotecas externas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (Context, Decimal, DecimalException, DivisionByZero,
                     InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext)
import math
import re
from types import MappingProxyType
from typing import Any, Mapping


MAX_NODES = 500
MAX_EDGES = 4000
MAX_WEIGHT = Decimal("1000000000000")
MAX_NUMBER_CHARS = 100
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,40}\Z", re.ASCII)
WEIGHT_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)
_MISSING = object()


class ValidationError(ValueError):
    """Entrada inválida; el mensaje está destinado a quien usa el proyecto."""


def _decimal_context() -> Context:
    # Todos los campos explícitos: Context(prec=40) por sí solo hereda otros
    # valores de DefaultContext, que también puede ser modificado por un cliente.
    return Context(prec=40, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def validate_id(value: Any, field: str = "ID") -> str:
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise ValidationError(f"{field}: usa de 1 a 40 letras ASCII, números, guiones o guiones bajos.")
    return value


def canonical_decimal(value: Decimal) -> str:
    """Representación exacta sin exponente ni ceros fraccionarios sobrantes."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError("El costo debe ser un decimal finito.")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def parse_weight(value: Any) -> Decimal:
    """Convierte un peso sin redondearlo, sin depender del contexto global."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError("El peso debe ser un número o texto decimal, no un booleano ni un valor vacío.")
    if isinstance(value, str):
        if len(value) > MAX_NUMBER_CHARS or WEIGHT_PATTERN.fullmatch(value) is None:
            raise ValidationError("El peso debe ser texto decimal no negativo, sin espacios, signos ni exponentes.")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValidationError("El peso debe ser finito; NaN e infinito no se admiten.")
    # Decimal(str(...)) conserva el valor textual del número y no aplica la
    # precisión global. El contexto propio también aísla trampas del llamador.
    try:
        with localcontext(_decimal_context()):
            result = value if isinstance(value, Decimal) else Decimal(str(value))
            if not result.is_finite() or result < 0 or result > MAX_WEIGHT:
                raise ValidationError("El peso debe estar entre 0 y 1000000000000 y ser finito.")
    except (DecimalException, ValueError, OverflowError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("El peso no es un decimal válido.") from exc
    digits = result.as_tuple().digits
    exponent = result.as_tuple().exponent
    if len(digits) > MAX_NUMBER_CHARS:
        raise ValidationError("El peso excede el límite de 100 dígitos de entrada.")
    # Recorrer índices es lineal, incluso ante numerosos ceros finales.
    # normalize() no se usa porque puede redondear según el contexto.
    last = len(digits) - 1
    while last >= 0 and digits[last] == 0 and exponent < 0:
        last -= 1
        exponent += 1
    if result != 0 and exponent < -6:
        raise ValidationError("El peso admite como máximo seis posiciones decimales, sin redondear.")
    return Decimal(canonical_decimal(result))


def _coordinate(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValidationError(f"{field} debe ser una coordenada numérica finita.")
    if isinstance(value, Decimal):
        with localcontext(_decimal_context()):
            if not value.is_finite() or value < -10000 or value > 10000:
                raise ValidationError(f"{field} debe estar entre -10000 y 10000 y ser finita.")
    try:
        converted = float(value)
    except (ValueError, OverflowError):
        raise ValidationError(f"{field} debe estar entre -10000 y 10000.") from None
    if not math.isfinite(converted) or abs(converted) > 10000:
        raise ValidationError(f"{field} debe estar entre -10000 y 10000 y ser finita.")
    return 0.0 if converted == 0 else converted


def _check_object(value: Any, required: set[str], optional: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} debe ser un objeto JSON.")
    keys = set(value)
    if not all(isinstance(key, str) for key in keys):
        raise ValidationError(f"{label} solo admite claves de texto.")
    missing = required - keys
    if missing:
        raise ValidationError(f"{label}: faltan {', '.join(sorted(missing))}.")
    unexpected = keys - required - optional
    if unexpected:
        displayed = [repr(key[:80]) + ("…" if len(key) > 80 else "") for key in sorted(unexpected)[:5]]
        suffix = "…" if len(unexpected) > 5 else ""
        raise ValidationError(f"{label}: campos no admitidos: {', '.join(displayed)}{suffix}.")
    return value


@dataclass(frozen=True, slots=True)
class Node:
    """Nodo con identidad estable, etiqueta y posición visual independiente."""

    id: str
    label: str = ""
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        validate_id(self.id, "ID del nodo")
        if not isinstance(self.label, str) or len(self.label) > 80:
            raise ValidationError("La etiqueta del nodo debe ser texto de hasta 80 caracteres.")
        if any(ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF
               for char in self.label):
            raise ValidationError("La etiqueta del nodo no admite caracteres de control ni Unicode inválido.")
        object.__setattr__(self, "x", _coordinate(self.x, "x"))
        object.__setattr__(self, "y", _coordinate(self.y, "y"))

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "x": self.x, "y": self.y}


@dataclass(frozen=True, slots=True)
class Edge:
    """Conexión inmutable. La dirección se interpreta mediante su Graph."""

    id: str
    source: str
    target: str
    weight: Decimal

    def __post_init__(self) -> None:
        validate_id(self.id, "ID de la conexión")
        validate_id(self.source, "Origen de la conexión")
        validate_id(self.target, "Destino de la conexión")
        object.__setattr__(self, "weight", parse_weight(self.weight))

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "target": self.target,
                "weight": canonical_decimal(self.weight)}


class Graph:
    """Grafo editable; cada mutación conserva identidades y adyacencia."""

    def __init__(self, directed: bool = False) -> None:
        if type(directed) is not bool:
            raise ValidationError("directed debe ser true o false.")
        self._directed = directed
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._adjacency: dict[str, dict[str, str]] = {}

    @property
    def directed(self) -> bool:
        return self._directed

    @property
    def nodes(self) -> Mapping[str, Node]:
        return MappingProxyType(self._nodes)

    @property
    def edges(self) -> Mapping[str, Edge]:
        return MappingProxyType(self._edges)

    def get_node(self, node_id: str) -> Node:
        validate_id(node_id, "ID del nodo")
        if node_id not in self._nodes:
            raise ValidationError(f"No existe el nodo {node_id}.")
        return self._nodes[node_id]

    def get_edge(self, edge_id: str) -> Edge:
        validate_id(edge_id, "ID de la conexión")
        if edge_id not in self._edges:
            raise ValidationError(f"No existe la conexión {edge_id}.")
        return self._edges[edge_id]

    def add_node(self, node: Node) -> Node:
        if not isinstance(node, Node):
            raise ValidationError("add_node requiere un objeto Node.")
        if node.id in self._nodes:
            raise ValidationError(f"El nodo {node.id} ya existe.")
        if len(self._nodes) >= MAX_NODES:
            raise ValidationError(f"El grafo admite como máximo {MAX_NODES} nodos.")
        self._nodes[node.id] = node
        self._adjacency[node.id] = {}
        return node

    def update_node(self, node_id: str, *, label: Any = _MISSING,
                    x: Any = _MISSING, y: Any = _MISSING) -> Node:
        original = self.get_node(node_id)
        replacement = Node(original.id,
                           original.label if label is _MISSING else label,
                           original.x if x is _MISSING else x,
                           original.y if y is _MISSING else y)
        self._nodes[node_id] = replacement
        return replacement

    def remove_node(self, node_id: str) -> Node:
        original = self.get_node(node_id)
        incident = [edge.id for edge in self._edges.values()
                    if edge.source == node_id or edge.target == node_id]
        for edge_id in incident:
            self.remove_edge(edge_id)
        del self._adjacency[node_id]
        del self._nodes[node_id]
        return original

    def _check_edge(self, edge: Edge, replacing: str | None = None) -> None:
        if not isinstance(edge, Edge):
            raise ValidationError("add_edge requiere un objeto Edge.")
        if edge.id in self._edges and edge.id != replacing:
            raise ValidationError(f"La conexión {edge.id} ya existe.")
        self.get_node(edge.source)
        self.get_node(edge.target)
        existing = self._adjacency[edge.source].get(edge.target)
        if existing is not None and existing != replacing:
            raise ValidationError("Ya existe una conexión entre esos nodos con esa dirección.")
        if replacing is None and len(self._edges) >= MAX_EDGES:
            raise ValidationError(f"El grafo admite como máximo {MAX_EDGES} conexiones.")

    def _insert_edge(self, edge: Edge) -> None:
        self._edges[edge.id] = edge
        self._adjacency[edge.source][edge.target] = edge.id
        if not self._directed:
            self._adjacency[edge.target][edge.source] = edge.id

    def add_edge(self, edge: Edge) -> Edge:
        self._check_edge(edge)
        self._insert_edge(edge)
        return edge

    def update_edge(self, edge_id: str, *, source: Any = _MISSING,
                    target: Any = _MISSING, weight: Any = _MISSING) -> Edge:
        original = self.get_edge(edge_id)
        replacement = Edge(original.id,
                           original.source if source is _MISSING else source,
                           original.target if target is _MISSING else target,
                           original.weight if weight is _MISSING else weight)
        # Validar todo antes de retirar la conexión existente hace atómico el
        # rechazo: una edición inválida nunca borra los datos anteriores.
        self._check_edge(replacement, replacing=edge_id)
        self.remove_edge(edge_id)
        self._insert_edge(replacement)
        return replacement

    def remove_edge(self, edge_id: str) -> Edge:
        original = self.get_edge(edge_id)
        del self._adjacency[original.source][original.target]
        if not self._directed and original.source != original.target:
            del self._adjacency[original.target][original.source]
        del self._edges[edge_id]
        return original

    def neighbors(self, node_id: str) -> tuple[tuple[str, Edge], ...]:
        """Instantánea de vecinos salientes ordenada por ID ASCII."""
        self.get_node(node_id)
        return tuple((neighbor, self._edges[edge_id]) for neighbor, edge_id
                     in sorted(self._adjacency[node_id].items()))

    def to_dict(self) -> dict:
        return {"schema_version": 1, "directed": self.directed,
                "nodes": [self._nodes[key].to_dict() for key in sorted(self._nodes)],
                "edges": [self._edges[key].to_dict() for key in sorted(self._edges)]}

    @classmethod
    def from_dict(cls, payload: dict) -> Graph:
        _check_object(payload, {"schema_version", "directed", "nodes", "edges"}, set(), "Grafo")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValidationError("schema_version debe ser el entero 1.")
        if not isinstance(payload["nodes"], list) or not isinstance(payload["edges"], list):
            raise ValidationError("nodes y edges deben ser listas JSON.")
        if len(payload["nodes"]) > MAX_NODES or len(payload["edges"]) > MAX_EDGES:
            raise ValidationError(f"El límite es {MAX_NODES} nodos y {MAX_EDGES} conexiones.")
        graph = cls(payload["directed"])
        for item in payload["nodes"]:
            _check_object(item, {"id"}, {"label", "x", "y"}, "Nodo")
            graph.add_node(Node(item["id"], item.get("label", ""), item.get("x", 0), item.get("y", 0)))
        for item in payload["edges"]:
            _check_object(item, {"id", "source", "target", "weight"}, set(), "Conexión")
            graph.add_edge(Edge(item["id"], item["source"], item["target"], item["weight"]))
        return graph
