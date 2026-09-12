"""Terminal: python -m vertice.cli --help. Solo biblioteca estándar."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from .codec import MAX_JSON_BYTES, load_json
from .dijkstra import DijkstraSolver
from .graph import Edge, Graph, Node, ValidationError


def _read_graph(filename: str) -> Graph:
    if filename == "-":
        binary = getattr(sys.stdin, "buffer", None)
        if binary is not None:
            # Las tuberías JSON son UTF-8 incluso si la terminal de Windows
            # usa cp1252. Medir bytes antes de decodificar conserva el límite.
            incoming = binary.read(MAX_JSON_BYTES + 1)
            if len(incoming) > MAX_JSON_BYTES:
                raise ValidationError("El archivo JSON excede el límite de 2 MiB.")
            text = incoming.decode("utf-8")
        else:
            text = sys.stdin.read(MAX_JSON_BYTES + 1)
    else:
        path = Path(filename)
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ValidationError("El archivo JSON excede el límite de 2 MiB.")
        text = path.read_text(encoding="utf-8")
    return Graph.from_dict(load_json(text))


def _write_graph(graph: Graph, output: str, overwrite: bool) -> None:
    """Archivo temporal y sustitución atómica; reemplazo solo con --overwrite."""
    destination = Path(output).expanduser().absolute()
    if destination.exists() and not overwrite:
        raise ValidationError("El archivo de salida ya existe. Elige otro nombre o usa --overwrite.")
    text = json.dumps(graph.to_dict(), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False,
                                         dir=destination.parent, prefix=".vertice-", suffix=".tmp") as handle:
            temporary = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            # link() falla si otro proceso crea el destino mientras escribimos;
            # evita sobrescribirlo por una carrera entre comprobación y guardado.
            os.link(temporary, destination)
            os.unlink(temporary)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", "-o", required=True, help="Archivo JSON de salida")
    parser.add_argument("--overwrite", action="store_true", help="Permitir reemplazar el archivo de salida")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VÉRTICE / SDV · Grafos editables y Dijkstra en Python")
    commands = parser.add_subparsers(dest="command", required=True)
    solve = commands.add_parser("solve", help="Calcular una ruta de costo mínimo")
    solve.add_argument("file", help="Grafo JSON; usa - para leer la entrada estándar")
    solve.add_argument("--source", "-s", required=True, help="ID de inicio")
    solve.add_argument("--target", "-t", required=True, help="ID de destino")
    solve.add_argument("--json", action="store_true", help="Mostrar el resultado JSON completo")
    solve.add_argument("--trace", action="store_true", help="Incluir las operaciones del algoritmo en el JSON")
    validate = commands.add_parser("validate", help="Comprobar todas las invariantes del grafo")
    validate.add_argument("file")
    create = commands.add_parser("create", help="Crear un grafo vacío")
    create.add_argument("--directed", action="store_true", help="Crear conexiones dirigidas")
    _output_options(create)
    edit = commands.add_parser("edit", help="Editar nodos o conexiones sin arrastrar elementos")
    edit.add_argument("file", help="Grafo JSON original")
    operations = edit.add_subparsers(dest="operation", required=True)
    for name, description in (("add-node", "Añadir un nodo"), ("update-node", "Editar un nodo"),
                              ("remove-node", "Quitar un nodo y sus conexiones"),
                              ("add-edge", "Añadir una conexión"), ("update-edge", "Editar una conexión"),
                              ("remove-edge", "Quitar una conexión")):
        operation = operations.add_parser(name, help=description)
        operation.add_argument("id", help="Identificador estable")
        if name in {"add-node", "update-node"}:
            operation.add_argument("--label", default=argparse.SUPPRESS)
            operation.add_argument("--x", type=float, default=argparse.SUPPRESS)
            operation.add_argument("--y", type=float, default=argparse.SUPPRESS)
        if name in {"add-edge", "update-edge"}:
            for field in ("source", "target", "weight"):
                operation.add_argument("--" + field, required=name == "add-edge", default=argparse.SUPPRESS)
        _output_options(operation)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            graph = Graph(directed=args.directed)
            _write_graph(graph, args.output, args.overwrite)
            print(f"Grafo guardado: {args.output}")
            return 0
        graph = _read_graph(args.file)
        if args.command == "validate":
            print(f"Grafo válido: {len(graph.nodes)} nodos, {len(graph.edges)} conexiones.")
            return 0
        if args.command == "solve":
            result = DijkstraSolver(graph).solve(args.source, args.target, args.trace)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
            elif result["status"] == "no_path":
                print(f"No hay ruta de {args.source} a {args.target}.")
            else:
                print("Ruta: " + " → ".join(result["path"]))
                print("Costo: " + result["cost"])
                print(f"Nodos asentados: {result['stats']['settled']}")
            # No encontrar ruta es un resultado válido, no un error de entrada.
            return 0
        fields = vars(args)
        if args.operation in {"add-node", "update-node"}:
            changes = {key: fields[key] for key in ("label", "x", "y") if key in fields}
            if args.operation == "add-node":
                graph.add_node(Node(args.id, **changes))
            else:
                graph.update_node(args.id, **changes)
        elif args.operation == "remove-node":
            graph.remove_node(args.id)
        elif args.operation in {"add-edge", "update-edge"}:
            changes = {key: fields[key] for key in ("source", "target", "weight") if key in fields}
            if args.operation == "add-edge":
                graph.add_edge(Edge(args.id, **changes))
            else:
                graph.update_edge(args.id, **changes)
        else:
            graph.remove_edge(args.id)
        _write_graph(graph, args.output, args.overwrite)
        print(f"Grafo guardado: {args.output}")
        return 0
    except (ValidationError, OSError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
