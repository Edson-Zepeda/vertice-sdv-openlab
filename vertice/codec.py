"""Frontera JSON común al servidor, navegador y terminal."""

from __future__ import annotations

from decimal import Decimal, DecimalException, localcontext
import json
from typing import Any

from .dijkstra import DijkstraSolver
from .graph import Graph, MAX_NUMBER_CHARS, ValidationError, _check_object, _decimal_context


MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_CONTAINERS = 5000
MAX_JSON_PUNCTUATION = 50000


def _guard_json_structure(text: str) -> None:
    """Limita la amplificación de objetos antes de decodificar, sin sustituir JSON.

    Una solicitud válida máxima usa 4504 contenedores y 36012 comas/dos puntos.
    El recuento rápido incluye cadenas: solo sobreestima, nunca oculta exceso.
    Si hace falta, el recorrido lineal excluye las cadenas y sus comillas
    escapadas. La sintaxis y los números siguen a cargo de json.loads.
    """
    if (text.count("{") + text.count("[") <= MAX_JSON_CONTAINERS
            and text.count(",") + text.count(":") <= MAX_JSON_PUNCTUATION):
        return
    position = containers = punctuation = 0
    while position < len(text):
        character = text[position]
        if character == '"':
            end = text.find('"', position + 1)
            while end >= 0:
                back = end - 1
                while back > position and text[back] == "\\":
                    back -= 1
                if (end - 1 - back) % 2 == 0:
                    break
                end = text.find('"', end + 1)
            if end < 0:
                return  # El analizador estándar informará la cadena incompleta.
            position = end + 1
            continue
        if character in "[{":
            containers += 1
            if containers > MAX_JSON_CONTAINERS:
                raise ValidationError("El JSON excede la estructura admitida para un grafo.")
        elif character in ",:":
            punctuation += 1
            if punctuation > MAX_JSON_PUNCTUATION:
                raise ValidationError("El JSON contiene demasiados campos para un grafo.")
        position += 1


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            displayed = repr(key[:80]) + ("…" if len(key) > 80 else "")
            raise ValidationError(f"El JSON repite la clave {displayed}; corrige la ambigüedad.")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValidationError(f"{value} no es un número JSON finito admitido.")


def _number(text: str) -> Decimal:
    if len(text) > MAX_NUMBER_CHARS:
        raise ValidationError("Cada número JSON admite como máximo 100 caracteres de entrada.")
    try:
        with localcontext(_decimal_context()):
            return Decimal(text)
    except DecimalException:
        raise ValidationError("El exponente del número JSON está fuera de los límites admitidos.") from None


def _integer(text: str) -> int:
    if len(text) > MAX_NUMBER_CHARS:
        raise ValidationError("Cada número JSON admite como máximo 100 caracteres de entrada.")
    return int(text)


def load_json(text: str) -> Any:
    """Carga estricta reutilizable para grafos y solicitudes; no ejecuta código."""
    if not isinstance(text, str):
        raise ValidationError("La entrada debe ser texto JSON.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValidationError("El JSON contiene caracteres Unicode inválidos.") from None
    if size > MAX_JSON_BYTES:
        raise ValidationError("El archivo JSON excede el límite de 2 MiB.")
    _guard_json_structure(text)
    try:
        return json.loads(text, parse_float=_number, parse_int=_integer, parse_constant=_constant,
                          object_pairs_hook=_object_pairs)
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError, DecimalException) as exc:
        if isinstance(exc, ValidationError):
            raise
        if isinstance(exc, json.JSONDecodeError):
            raise ValidationError(f"JSON inválido en línea {exc.lineno}, columna {exc.colno}.") from exc
        raise ValidationError("El JSON contiene números o estructuras fuera de los límites admitidos.") from exc


def solve_payload(payload: dict) -> dict:
    _check_object(payload, {"graph", "source", "target"}, {"trace"}, "Búsqueda")
    graph = Graph.from_dict(payload["graph"])
    return DijkstraSolver(graph).solve(payload["source"], payload["target"], payload.get("trace", True))


def solve_json(text: str) -> str:
    result = solve_payload(load_json(text))
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
