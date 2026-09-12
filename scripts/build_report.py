"""Build the evidence-backed, ten-page SDV report and its identical web copy.

Authoring dependencies: reportlab, fonttools, pypdf, Pillow. None is needed by
the delivered graph engine. Render with --render (Poppler required).
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont as FontFile
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageOps, ImageDraw
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vertice.codec import solve_payload

WIDTH, HEIGHT = 595.2756, 841.8898
MARGIN, CONTENT = 42, 511.2756
INK = colors.HexColor('#153c3a')
TEAL = colors.HexColor('#087e77')
CORAL = colors.HexColor('#df6f4a')
PAPER = colors.HexColor('#f7f3e9')
WHITE = colors.HexColor('#ffffff')
MUTED = colors.HexColor('#58706c')
LINE = colors.HexColor('#c9d5ca')
PALE = colors.HexColor('#e5eee4')
MONO = 'Courier'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(relative, default=None):
    path = ROOT / relative
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def fresh_evidence(report, relevant=None):
    if not report or report.get('status', 'pass') != 'pass':
        return False
    hashes = report.get('source_hashes', {})
    if not hashes:
        return False
    for name, expected in hashes.items():
        if relevant and name not in relevant:
            continue
        path = ROOT / name
        if not path.is_file() or digest(path) != expected:
            return False
    return True


def setup_fonts():
    output = ROOT / 'tmp/pdfs/fonts'
    output.mkdir(parents=True, exist_ok=True)
    for family, name, weight in [('Manrope', 'Display', 700), ('Manrope', 'DisplayMedium', 550),
                                 ('DMSans', 'Body', 430), ('DMSans', 'BodyBold', 650)]:
        destination = output / f'{name}.ttf'
        font = FontFile(ROOT / f'web/fonts/{family}.ttf')
        axes = {'wght': weight}
        if 'fvar' in font and any(axis.axisTag == 'opsz' for axis in font['fvar'].axes):
            axes['opsz'] = 12
        if 'fvar' in font:
            font = instantiateVariableFont(font, axes, inplace=True)
        font.recalcTimestamp = False
        font.save(destination)
        pdfmetrics.registerFont(TTFont(name, destination))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='BodyBold', italic='Body', boldItalic='BodyBold')


class Report:
    def __init__(self, destination):
        self.canvas = canvas.Canvas(str(destination), pagesize=(WIDTH, HEIGHT), pageCompression=1, invariant=1)
        self.canvas.setTitle('VÉRTICE / SDV - Informe de implementación y verificación')
        self.canvas.setAuthor('VÉRTICE / SDV')
        self.canvas.setSubject('Dijkstra orientado a objetos: código, trazas, pruebas y auditoría')
        self.page_number = 0
        self.regions = []

    def rect(self, x, y, width, height, fill=WHITE, stroke=None, radius=0):
        c = self.canvas
        c.setFillColor(fill)
        c.setStrokeColor(stroke or fill)
        if radius:
            c.roundRect(x, HEIGHT-y-height, width, height, radius, fill=1, stroke=bool(stroke))
        else:
            c.rect(x, HEIGHT-y-height, width, height, fill=1, stroke=bool(stroke))

    def line(self, x1, y1, x2, y2, color=LINE, width=1):
        self.canvas.setStrokeColor(color)
        self.canvas.setLineWidth(width)
        self.canvas.line(x1, HEIGHT-y1, x2, HEIGHT-y2)

    def text(self, text, x, y, size=11, font='Body', color=INK):
        text = str(text).replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
        self.canvas.setFillColor(color)
        self.canvas.setFont(font, size)
        self.canvas.drawString(x, HEIGHT-y-size, text)
        self.regions.append({'page': self.page_number, 'text': text, 'x': x, 'y': y,
                             'width': pdfmetrics.stringWidth(text, font, size), 'height': size*1.25})

    def para(self, text, x, y, width=CONTENT, size=11, leading=None, color=INK, bold=False):
        style = ParagraphStyle('p', fontName='BodyBold' if bold else 'Body', fontSize=size,
                               leading=leading or size*1.43, textColor=color, alignment=TA_LEFT)
        paragraph = Paragraph(text.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-'), style)
        _, height = paragraph.wrap(width, HEIGHT)
        paragraph.drawOn(self.canvas, x, HEIGHT-y-height)
        self.regions.append({'page': self.page_number, 'text': text, 'x': x, 'y': y,
                             'width': width, 'height': height})
        return y + height

    def circle(self, x, y, radius, fill=TEAL, stroke=None):
        self.canvas.setFillColor(fill)
        self.canvas.setStrokeColor(stroke or fill)
        self.canvas.circle(x, HEIGHT-y, radius, fill=1, stroke=bool(stroke))

    def page(self, section, title, subtitle=None):
        if self.page_number:
            self.canvas.showPage()
        self.page_number += 1
        self.rect(0, 0, WIDTH, HEIGHT, PAPER)
        self.text('VÉRTICE', MARGIN, 25, 12, 'Display', TEAL)
        self.text('/ SDV', MARGIN+68, 28, 9, 'BodyBold', MUTED)
        self.text(section.upper(), 305, 29, 9, 'BodyBold', MUTED)
        self.line(MARGIN, 59, WIDTH-MARGIN, 59)
        self.text(title, MARGIN, 80, 29, 'Display')
        if subtitle:
            self.para(subtitle, MARGIN, 124, size=11.2, color=MUTED)
        self.line(MARGIN, HEIGHT-49, WIDTH-MARGIN, HEIGHT-49)
        self.text('OPENLAB 2026  /  PERFIL SOFTWARE', MARGIN, HEIGHT-34, 8, 'BodyBold', MUTED)
        self.text(f'{self.page_number:02d} / 10', WIDTH-MARGIN-37, HEIGHT-35, 9, 'BodyBold', TEAL)
        self.canvas.bookmarkPage(f'page{self.page_number}')
        self.canvas.addOutlineEntry(title, f'page{self.page_number}', level=0, closed=False)

    def label(self, title, x, y, width=CONTENT):
        self.text(title.upper(), x, y, 9.7, 'BodyBold', TEAL)
        self.line(x, y+21, x+width, y+21)

    def card(self, number, label, x, y, width=157, color=TEAL):
        self.rect(x, y, width, 85, WHITE, radius=10)
        self.text(number, x+16, y+9, 28, 'Display', color)
        self.para(label, x+16, y+50, width-28, 10.2, color=MUTED)

    def arrow(self, x1, y1, x2, y2, color=TEAL):
        self.line(x1, y1, x2, y2, color, 1.5)
        angle = math.atan2(y2-y1, x2-x1)
        for adjustment in (-0.55, 0.55):
            self.line(x2, y2, x2-8*math.cos(angle+adjustment), y2-8*math.sin(angle+adjustment), color, 1.5)

    def table(self, headers, rows, widths, x=MARGIN, y=180, row_height=48, size=10):
        self.rect(x, y, sum(widths), 30, INK, radius=4)
        current = x
        for header, width in zip(headers, widths):
            self.text(header, current+10, y+8, 9, 'BodyBold', WHITE)
            current += width
        y += 30
        for index, row in enumerate(rows):
            self.rect(x, y, sum(widths), row_height, WHITE if index % 2 == 0 else PALE)
            current = x
            for cell, width in zip(row, widths):
                height = self.para(str(cell), current+10, y+9, width-20, size=size, leading=size*1.32)-y
                if height > row_height-4:
                    raise ValueError(f'Tabla desbordada en página {self.page_number}: {cell}')
                current += width
            y += row_height
        return y

    def graph(self, graph, result, x, y, width, height, labels=True):
        nodes = {node['id']: node for node in graph['nodes']}
        xs, ys = [n['x'] for n in nodes.values()], [n['y'] for n in nodes.values()]
        low_x, high_x, low_y, high_y = min(xs), max(xs), min(ys), max(ys)
        def point(node_id):
            node = nodes[node_id]
            return (x+20+(node['x']-low_x)/max(1, high_x-low_x)*(width-40),
                    y+25+(node['y']-low_y)/max(1, high_y-low_y)*(height-50))
        route = set(result['edge_path'])
        for edge in graph['edges']:
            px, py = point(edge['source']); qx, qy = point(edge['target'])
            selected = edge['id'] in route
            self.line(px, py, qx, qy, TEAL if selected else LINE, 3.8 if selected else 1.4)
            if labels:
                mx, my = (px+qx)/2, (py+qy)/2
                self.rect(mx-9, my-8, 18, 17, PAPER, radius=4)
                self.text(edge['weight'], mx-4, my-7, 10, 'BodyBold', TEAL if selected else MUTED)
        for node_id in nodes:
            px, py = point(node_id)
            selected = node_id in result['path']
            self.circle(px, py, 15, TEAL if selected else WHITE, TEAL if selected else LINE)
            label_width = pdfmetrics.stringWidth(node_id, 'BodyBold', 11)
            self.text(node_id, px-label_width/2, py-7, 11, 'BodyBold', WHITE if selected else INK)


def build(output, integration_path):
    setup_fonts()
    data = read_json('web/data/examples.json')
    example = next(item for item in data if item['id'] == 'desvio')
    result = solve_payload({key: example[key] for key in ('graph', 'source', 'target')} | {'trace': True})
    independent = read_json('evidence/verification/independent.json', {})
    benchmark = read_json('evidence/verification/benchmark.json', {})
    mutations = read_json('evidence/verification/mutations.json', {})
    mutations_current = fresh_evidence({'source_hashes': mutations.get('production_sha256_after', {})},
                                       {'vertice/graph.py', 'vertice/dijkstra.py', 'vertice/codec.py',
                                        'tests/test_independent.py', 'tests/independent_oracle.py'})
    http = read_json('evidence/verification/http.json', {})
    cli_path = 'evidence/verification/cli_python311.json'
    cli = read_json(cli_path, read_json('evidence/verification/cli.json', {}))
    cli_versions = [item.get('environment', {}).get('python', '?')
                    for path in sorted((ROOT/'evidence/verification').glob('cli_python*.json'))
                    if fresh_evidence(item := read_json(str(path.relative_to(ROOT))))]
    integration = read_json(integration_path, {})
    verified = fresh_evidence(independent)
    benchmark_current = fresh_evidence(benchmark, {'vertice/graph.py', 'vertice/dijkstra.py', 'vertice/codec.py',
                                                   'scripts/benchmark.py', 'tests/independent_oracle.py'})
    scopes = independent.get('scenarios', {})
    evidence_inputs = ['web/data/examples.json', 'docs/REQUISITOS.md', 'docs/CONTRATO.md', 'docs/API.md',
                       'docs/ALGORITMO.md', 'docs/ARQUITECTURA.md', 'docs/AUDITORIA.md',
                       'evidence/verification/independent.json', 'evidence/verification/benchmark.json',
                       'evidence/verification/http.json', 'evidence/verification/mutations.json', cli_path, integration_path]
    evidence_inputs.extend(str(path.relative_to(ROOT)).replace('\\', '/')
                           for path in sorted((ROOT/'evidence/verification').glob('cli_python*.json'))
                           if str(path.relative_to(ROOT)).replace('\\', '/') not in evidence_inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    r = Report(output)

    # 01 - Cover and an actual computed route.
    r.page('Informe de implementación', 'Una ruta. Cada decisión.', 'Dijkstra orientado a objetos, con costos exactos y evidencia reproducible.')
    r.text('VÉRTICE', MARGIN, 180, 60, 'Display', TEAL)
    r.text('Laboratorio de rutas mínimas', MARGIN+3, 254, 17, 'DisplayMedium', INK)
    r.graph(example['graph'], result, MARGIN+2, 307, CONTENT-4, 255)
    r.rect(MARGIN, 583, CONTENT, 79, INK, radius=11)
    r.text('RUTA CALCULADA', MARGIN+18, 597, 9, 'BodyBold', PALE)
    r.text(' > '.join(result['path']), MARGIN+18, 620, 20, 'Display', WHITE)
    r.text(f"COSTO {result['cost']}", 418, 623, 16, 'Display', WHITE)
    r.para('Grafo didáctico incluido en <b>examples/desvio.json</b>. El resultado se genera con el mismo '
           'núcleo Python de la entrega; los costos no representan distancias medidas de una calle.', MARGIN, 688, size=10.5, color=MUTED)
    r.text('VANTTEC / OPENLAB 2026', MARGIN, 750, 9, 'BodyBold', TEAL)

    # 02 - Requirement traceability.
    r.page('01 / Alcance', 'Del lineamiento a la evidencia', 'Referencia: Bootcamp SDV.pdf, página 3. Perfil Software: Dijkstra y POO.')
    rows = [
        ('Dijkstra desde cero', 'DijkstraSolver: relajaciones, cola, predecesores y ruta propios.', 'vertice/dijkstra.py'),
        ('Objetos del sistema', 'Node, Edge y Graph; edición validada y adyacencia consistente.', 'graph.py; API.md'),
        ('Crear y modificar', 'Terminal editable y editor web; inicio y destino explícitos.', 'cli.py; interfaz'),
        ('Clases documentadas', 'Atributos, métodos, responsabilidades y representación visual.', 'API.md; p. 3'),
        ('Pruebas distintas', 'Casos nombrados, grafos con semilla y oráculo independiente.', 'p. 6; evidencia JSON'),
        ('Ausencia de ruta', 'no_path, rutas vacías y costo null; sin inventar un costo cero.', 'tests; ejemplos'),
        ('Decisiones y operación', 'Trazas reales, argumento de corrección y complejidad explícita.', 'pp. 4-5; ALGORITMO.md'),
    ]
    r.table(['REQUISITO', 'IMPLEMENTACIÓN', 'DÓNDE COMPROBAR'], rows, [131, 238, 142], y=184, row_height=62, size=10)
    r.label('Valor adicional dentro del alcance', MARGIN, 674)
    r.para('La edición reversible, la visualización de eventos y la auditoría ayudan a explicar y verificar el reto. '
           'La GUI es opcional en el documento; aquí complementa la implementación Python. No se presenta como ejecución en un vehículo.',
           MARGIN, 710, size=10.8)

    # 03 - Class model and concrete adjacency.
    r.page('02 / Arquitectura', 'Objetos y responsabilidades', 'El grafo conserva las reglas; el solucionador calcula; la interfaz representa el resultado.')
    boxes = [
        (42, 181, 'Node', 'id · label · x · y', 'Identidad y posición visual.', 'Objeto inmutable.'),
        (312, 181, 'Edge', 'id · source · target · weight', 'Extremos y costo Decimal.', 'Objeto inmutable.'),
        (42, 346, 'Graph', 'nodes · edges · adjacency', 'Crear, editar, borrar y consultar.', 'Valida antes de modificar.'),
        (312, 346, 'DijkstraSolver', 'graph · solve(inicio, destino)', 'Relajar, asentar y reconstruir.', 'Estado propio en cada búsqueda.'),
    ]
    for x, y, title, fields, purpose, rule in boxes:
        r.rect(x, y, 241, 128, WHITE, stroke=LINE, radius=9)
        r.text(title, x+14, y+10, 18, 'Display', TEAL)
        r.line(x+14, y+44, x+227, y+44)
        r.text(fields, x+14, y+56, 9.5, 'BodyBold', MUTED)
        r.para(purpose+'<br/>'+rule, x+14, y+80, 214, 10.1, leading=14)
    r.arrow(164, 345, 164, 310)
    r.arrow(249, 345, 394, 310)
    r.arrow(311, 412, 284, 412)
    r.text('administra', 61, 317, 9, 'BodyBold', MUTED)
    r.label('Adyacencia del ejemplo', MARGIN, 517)
    sample = [('S', 'A : e1   |   B : e2'), ('B', 'A : e3   |   D : e6   |   S : e2'), ('T', 'E : e11  |   F : e12')]
    for index, (node, neighbors) in enumerate(sample):
        y = 553+index*34
        r.rect(MARGIN, y, CONTENT, 29, WHITE, radius=5)
        r.text(node, MARGIN+13, y+6, 11, 'BodyBold', TEAL)
        r.text(neighbors, MARGIN+53, y+7, 10.3, MONO)
    r.para('Estructura: <b>nodo → vecino → ID de conexión</b>. En no dirigido se conservan ambas orientaciones; '
           'un bucle propio aparece una vez. Borrar un nodo retira sus conexiones. Una edición inválida conserva el grafo anterior.',
           MARGIN, 680, size=10.7)

    # 04 - Trace from the actual Python solver.
    r.page('03 / Ejecución', 'La traza explica el resultado', 'Ejemplo “Un mejor desvío”: la conexión directa no siempre produce el menor costo.')
    r.card(str(result['stats']['settled']), 'nodos asentados', 42, 178)
    r.card(str(result['stats']['relaxations']), 'mejoras aplicadas', 219, 178)
    r.card(str(result['stats']['stale_pops']), 'entradas antiguas descartadas', 396, 178, color=CORAL)
    chosen_steps = [0, 1, 3, 5, 6, 8, 18, 29, result['trace'][-1]['step']]
    events = {event['step']: event for event in result['trace']}
    trace_rows = []
    names = {'initialize': 'Iniciar', 'settle': 'Asentar', 'relax': 'Mejorar', 'stale': 'Descartar', 'finish': 'Terminar'}
    for step in chosen_steps:
        event = events[step]
        detail = event.get('node') or f"{event.get('source')} > {event.get('target')}"
        if event['kind'] == 'relax':
            value = f"{event['old_cost'] if event['old_cost'] is not None else 'sin dato'} > {event['new_cost']}"
        elif event['kind'] == 'stale':
            value = f"{event['cost']} ya reemplazado por {event['new_cost']}"
        else:
            value = event.get('cost', '')
        trace_rows.append((str(step), names[event['kind']], detail, value))
    r.table(['PASO', 'OPERACIÓN', 'NODO / CONEXIÓN', 'COSTO'], trace_rows, [53, 105, 163, 190], y=294, row_height=35, size=10.5)
    r.para(f"Selección de {len(chosen_steps)} eventos de una traza real de <b>{len(result['trace'])}</b>. Los números de paso conservan "
           'su posición original. “Sin dato” significa que el nodo todavía no tenía una ruta descubierta.', MARGIN, 660, size=10.5, color=MUTED)
    r.para('<b>La mejora clave:</b> S descubre A con costo 4; al procesar B aparece una ruta a A de costo 3. '
           'La entrada antigua de costo 4 se descarta después, sin volver a expandir A.', MARGIN, 715, size=10.5)

    # 05 - Correctness and numerical guarantee.
    r.page('04 / Corrección', 'Por qué el mínimo es correcto', 'Premisas: conexiones válidas, pesos no negativos y grafo estable durante cada búsqueda.')
    proof = [
        ('01', 'Cada costo representa una ruta', 'El origen empieza en cero. Relajar añade una conexión real a una ruta conocida; nunca inventa una distancia menor que el óptimo.'),
        ('02', 'El menor vigente queda resuelto', 'Una ruta más barata cruzaría antes por un nodo pendiente de costo menor. Ese nodo habría salido primero de la cola. La no negatividad hace válida esta contradicción.'),
        ('03', 'Los predecesores reconstruyen', 'Un predecesor está asentado antes que su sucesor. La cadena retrocede en ese orden, no forma ciclos y termina en el inicio.'),
    ]
    y = 180
    for number, title, body in proof:
        r.circle(MARGIN+17, y+17, 17, TEAL)
        r.text(number, MARGIN+9, y+9, 11, 'BodyBold', WHITE)
        r.text(title, MARGIN+47, y-1, 15, 'DisplayMedium')
        end = r.para(body, MARGIN+47, y+25, CONTENT-47, 10.7)
        y = end+29
    r.rect(MARGIN, 476, CONTENT, 103, INK, radius=10)
    r.text('21 cifras necesarias · 40 cifras disponibles', MARGIN+17, 491, 18, 'Display', WHITE)
    r.para('Con 500 nodos, peso máximo 10<super>12</super> y seis decimales, una suma candidata usa como máximo '
           '15 cifras enteras + 6 fraccionarias. El contexto Decimal explícito representa esas sumas sin redondear.',
           MARGIN+17, 524, CONTENT-34, 10.6, color=WHITE)
    r.label('Parar temprano exige una distinción', MARGIN, 613)
    r.para('Se termina al <b>asentar</b> el destino. Solo los nodos de <b>settled</b> tienen distancia definitiva. '
           'Si A→B=1, A→C=9 y B→C=1, buscar A→B deja a C con costo tentativo 9; su óptimo global sería 2.',
           MARGIN, 649, size=11)
    r.para('Si se agota la cola sin asentar el destino, no hay ruta. Inicio igual a destino devuelve costo cero. '
           'El argumento completo, las cotas y los casos límite están en ALGORITMO.md.', MARGIN, 722, size=10.3, color=MUTED)

    # 06 - Independent verification without mixing counting units.
    r.page('05 / Verificación', 'Contraste independiente', 'Bellman-Ford con enteros en micro-unidades comprueba los costos de Dijkstra.')
    r.card(str(independent.get('test_methods', '-')), 'métodos independientes', 42, 178)
    r.card(str(scopes.get('seeded_graphs', '-')), 'grafos con semilla', 219, 178)
    r.card(str(scopes.get('seeded_queries', '-')), 'consultas con semilla', 396, 178)
    groups = Counter(record['test'].split('.')[1] for record in independent.get('results', []))
    labels = {'GraphMutationTests': 'Edición e invariantes', 'DijkstraContractTests': 'Rutas y contrato',
              'NumericAndJsonTests': 'Números y JSON', 'IndependentOracleTests': 'Oráculo y propiedades',
              'ValidationTests': 'Validación', 'AlgorithmTests': 'Algoritmo',
              'IndependentAlgorithmTests': 'Algoritmo y oráculo', 'ValidationBoundaryTests': 'Entradas y números'}
    grouped = [(labels.get(name, name.replace('Tests', '')), str(count), 'Aprobados' if verified else 'Revalidar versión')
               for name, count in sorted(groups.items())]
    r.table(['CATEGORÍA', 'MÉTODOS', 'ESTADO'], grouped, [286, 85, 140], y=294, row_height=43, size=10.3)
    y = 330+43*len(grouped)+26
    r.para(f"Además: <b>{scopes.get('named_queries', '-')} casos nombrados</b>. Las consultas son ejecuciones dentro de los métodos; "
           'no se suman como si fueran nuevas pruebas unitarias. El oráculo usa otra estrategia y no reutiliza la relajación de Dijkstra.',
           MARGIN, y, size=10.7)
    y += 72
    exhaustive_graphs = scopes.get('exhaustive_graphs')
    exhaustive_queries = scopes.get('exhaustive_queries')
    if exhaustive_graphs is not None:
        r.para(f'<b>Dominio exhaustivo acotado:</b> {exhaustive_graphs} grafos dirigidos de tres nodos y '
               f'{exhaustive_queries} consultas. Cada una de las seis conexiones posibles toma ausencia, costo 0 o costo 1. '
               'No se extrapola exhaustividad a grafos mayores.', MARGIN, y, size=10.7)
        y += 78
    mutation_note = (f"Las pruebas detectaron <b>{mutations.get('summary', {}).get('detected_by_assertion', '-')} defectos</b> "
                     'introducidos en copias aisladas; no es una garantía universal.' if mutations_current else
                     'La auditoría de mutaciones necesita revalidar esta versión.')
    r.para(f"Se revisaron <b>{scopes.get('trace_events', '-')} eventos</b> por invariantes. Floyd-Warshall contrastó el propio oráculo. "
           + mutation_note, MARGIN, y, size=10.7)
    r.para('Evidencia: independent.json, cases.json y seeded_graphs.json. Fecha, entorno, semillas y huellas SHA-256 acompañan los resultados. '
           'El estado mostrado requiere que coincidan las huellas del código actual.', MARGIN, 720, size=9.7, color=MUTED)

    # 07 - Measured performance, common scale and honest sampling.
    r.page('06 / Rendimiento', 'Algoritmo y recorrido completo', 'Medianas en milisegundos. La validación y la serialización también cuestan tiempo.')
    selected = [entry for entry in benchmark.get('results', []) if not entry['trace_enabled']]
    names = {'chain_50': 'Cadena 50 / 49', 'chain_200': 'Cadena 200 / 199', 'chain_500': 'Cadena 500 / 499',
             'directed_500_4000': 'Dirigido 500 / 4000', 'undirected_grid_400': 'Malla 400 / 760',
             'unreachable_500_zero_chain': 'Sin ruta 500 / 498', 'same_source_target_500': 'Inicio = destino 500 / 4000'}
    r.text('Caso: nodos / conexiones', MARGIN, 182, 9.5, 'BodyBold', MUTED)
    r.rect(270, 183, 9, 9, TEAL); r.text('Algoritmo', 284, 179, 9.5, color=MUTED)
    r.rect(390, 183, 9, 9, CORAL); r.text('JSON a JSON', 404, 179, 9.5, color=MUTED)
    axis_x, axis_width = 264, 226
    maximum = max((entry['json_to_json']['median_ms'] for entry in selected), default=1)
    axis_maximum = math.ceil(maximum/25)*25
    for index in range(4):
        value = axis_maximum*index/3
        x = axis_x+axis_width*index/3
        r.line(x, 225, x, 611, LINE, .6)
        r.text(f'{value:.0f}', x-4, 616, 8.5, color=MUTED)
    for index, entry in enumerate(selected):
        y = 229+index*53
        r.text(names.get(entry['id'], entry['id']), MARGIN, y, 10.2, 'BodyBold')
        a, b = entry['solver_only']['median_ms'], entry['json_to_json']['median_ms']
        r.text(f'{a:.2f} / {b:.2f} ms', MARGIN, y+19, 10, color=MUTED)
        r.rect(axis_x, y+2, max(1, a/axis_maximum*axis_width), 7, TEAL, radius=2)
        r.rect(axis_x, y+16, max(1, b/axis_maximum*axis_width), 7, CORAL, radius=2)
    r.text('ms', axis_x+axis_width+10, 613, 9, 'BodyBold', MUTED)
    method = benchmark.get('method', {})
    environment = benchmark.get('environment', {})
    r.para(f"<b>Método:</b> {method.get('warmups_per_solver', '-')} calentamientos y "
           f"{method.get('timed_repeats_per_variant', '-')} repeticiones por variante. Siete cargas, con y sin traza; aquí se muestra sin traza. "
           '“Algoritmo” excluye construir el grafo; “JSON a JSON” incluye validar, construir, resolver y serializar.',
           MARGIN, 651, size=10.4)
    r.para(f"CPython {environment.get('python', '-')} · Windows · {environment.get('processor', environment.get('machine', '-'))}. "
           f"Semilla {method.get('graph_seed', '-')} · reloj perf_counter_ns. "
           'Una computadora; sin garantía de tiempo real. Con nueve muestras, el percentil95 por rango más cercano coincide con el máximo. '
           + ('Huellas de cálculo comprobadas.' if benchmark_current else 'La medición requiere revalidar las huellas de esta versión.'),
           MARGIN, 719, size=9.6, color=MUTED)

    # 08 - Actual audit with fixes, no fabricated rating.
    r.page('07 / Auditoría', 'La primera versión no bastaba', 'Se conservaron fallos anteriores y se añadieron regresiones para comprobar las correcciones.')
    rows = [
        ('Números JSON extremos', 'Excepción o trabajo cuadrático.', 'Límite temprano y recorrido lineal.'),
        ('Contexto decimal externo', 'Podía cambiar la aritmética.', 'Todos los atributos explícitos.'),
        ('JSON convertido antes de validar', 'Pérdida silenciosa de cifras o claves.', 'Validar el texto original en Python.'),
        ('JSON amplio inválido', 'Memoria elevada antes del rechazo.', 'Límites de estructura previos.'),
        ('Cancelación compartida', 'Interrumpía solicitudes ajenas.', 'FIFO y cancelación independiente.'),
        ('Etiquetas y límite del archivo', 'Espacios perdidos y emoji cortados.', 'Datos intactos y límite de 2 MiB.'),
        ('Salida del empaquetador', 'Podía sobrescribir un archivo fuente.', 'Salida externa y escritura temporal.'),
        ('Cabeceras y rangos HTTP', 'Ambigüedad y semántica incorrecta.', 'Validación estricta y regresiones.'),
    ]
    r.table(['HALLAZGO', 'CONSECUENCIA', 'CAMBIO'], rows, [164, 175, 172], y=182, row_height=49, size=10.1)
    r.label('La revisión deja límites visibles', MARGIN, 634)
    r.para('Aprobar pruebas no demuestra ausencia de todos los defectos. Los costos son abstractos, la legibilidad de grafos densos '
           'tiene límites y una medición local no representa otros equipos. La defensa debe poder explicar y modificar el código.',
           MARGIN, 671, size=10.9)
    r.para('AUDITORIA.md enlaza los registros anteriores y posteriores, incluidas revisiones de interfaz, video y entrega. '
           'No se asigna una calificación oficial ni una aprobación de un evaluador externo.', MARGIN, 735, size=9.6, color=MUTED)

    # 09 - Integration statuses are sourced and can be refreshed independently.
    r.page('08 / Integración', 'Comprobar cada superficie', 'Un núcleo correcto no demuestra por sí solo que el navegador o la publicación funcionen.')
    integration_checks = [
        {'name': 'API local HTTP', 'status': 'pass' if fresh_evidence(http) else 'pending',
         'detail': f"{http.get('test_methods', '-')} métodos. Solicitudes reales a localhost con fixtures aislados."},
        {'name': 'Terminal y arranque', 'status': 'pass' if fresh_evidence(cli) else 'pending',
         'detail': f"{cli.get('test_methods', '-')} métodos. CPython {', '.join(cli_versions) or 'por revalidar'}. Misma suite; no son casos adicionales."},
    ]
    supplied = integration.get('checks', [])
    if supplied:
        integration_checks.extend(supplied)
    else:
        integration_checks.extend([
            {'name': 'Python en navegador', 'status': 'pending', 'detail': 'Pendiente de evidencia de paridad y carga real.'},
            {'name': 'Editor y accesibilidad', 'status': 'pending', 'detail': 'Pendiente de pruebas reales de interacción y revisión visual.'},
            {'name': 'Publicación y descarga', 'status': 'pending', 'detail': 'Pendiente de comprobación de la entrega pública.'},
        ])
    state_names = {'pass': 'Verificado', 'pending': 'Pendiente', 'fail': 'Revisar'}
    rows = [(escape(item['name']), state_names.get(item.get('status'), 'Pendiente'), escape(item.get('detail', '')))
            for item in integration_checks]
    r.table(['COMPONENTE', 'ESTADO', 'EVIDENCIA'], rows, [139, 91, 281], y=184, row_height=72, size=10.1)
    y = 234+72*len(rows)
    r.label('Uso previsto', MARGIN, y)
    r.para('Abrir el proyecto, elegir un ejemplo, seleccionar inicio y destino y calcular. Después, editar un costo y observar '
           'cómo cambia la ruta. La reproducción recorre eventos; no modifica el resultado del algoritmo.', MARGIN, y+36, size=10.8)
    r.para('Una respuesta calculada para un grafo anterior debe descartarse tras editar. El modo web ejecuta el paquete Python '
           'en un worker; la cancelación y la identidad del worker tienen pruebas separadas de la paridad matemática.',
           MARGIN, y+103, size=10.4, color=MUTED)

    # 10 - Reproduction, complexity and primary references.
    r.page('09 / Reproducción', 'Código, evidencia y límites a la vista', 'Núcleo y terminal: Python 3.10 o posterior, solo biblioteca estándar.')
    commands = [
        'python -m vertice.cli validate examples/desvio.json',
        'python -m vertice.cli solve examples/desvio.json -s S -t T --json',
        'python -m unittest discover -s tests -p test_core.py',
        'python scripts/verify_independent.py',
        'python scripts/benchmark.py',
        'node --test tests/engine_queue.mjs',
    ]
    r.rect(MARGIN, 178, CONTENT, 184, INK, radius=9)
    r.text('DESDE LA CARPETA DEL PROYECTO', MARGIN+16, 191, 9, 'BodyBold', PALE)
    for index, command in enumerate(commands):
        r.text(command, MARGIN+16, 219+index*18, 9.5, MONO, WHITE)
    r.para('Añade --trace a solve para exportar cada evento. En Windows, Iniciar.cmd abre la aplicación local. '
           'Las herramientas de PDF, video y verificación del navegador son dependencias de producción de la entrega, no del algoritmo.',
           MARGIN, 382, size=10.3)
    r.label('Complejidad declarada', MARGIN, 454)
    r.text('Tiempo O((V + E) log(V + E + 1))', MARGIN, 492, 17, 'DisplayMedium', TEAL)
    r.text('Memoria O(V + E)', MARGIN, 521, 17, 'DisplayMedium', TEAL)
    r.para('La cota incluye vecinos ordenados, cola con entradas antiguas y trazas. La precisión numérica está acotada. '
           'El detalle por operación está en ALGORITMO.md.', MARGIN, 557, size=10.4)
    r.label('Fuentes primarias y archivos de evidencia', MARGIN, 616)
    references = [
        ('Bootcamp SDV.pdf, p. 3', 'Documento suministrado; perfil Software.'),
        ('Dijkstra (1959), problema 2', 'https://ir.cwi.nl/pub/9256/9256D.pdf'),
        ('Python: Decimal', 'https://docs.python.org/3/library/decimal.html'),
        ('Python: heapq', 'https://docs.python.org/3/library/heapq.html'),
        ('Evidencia de ejecución', 'evidence/verification/; semillas y SHA-256 en JSON.'),
    ]
    for index, (label, target) in enumerate(references):
        y = 650+index*26
        r.text(label, MARGIN, y, 9.2, 'BodyBold')
        r.text(target, MARGIN+172, y, 8.7, color=MUTED)
        if target.startswith('https://'):
            r.canvas.linkURL(target, (MARGIN+172, HEIGHT-y-13, WIDTH-MARGIN, HEIGHT-y+2), relative=0)
    r.canvas.save()
    if len(PdfReader(output).pages) != 10:
        raise ValueError('El informe debe contener diez páginas.')
    target = ROOT / 'web/docs/VerticeSDV_Informe.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output, target)
    evidence_dir = ROOT / 'evidence/report'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    record = {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'pages': 10,
        'pdf': str(output.relative_to(ROOT)).replace('\\', '/'), 'pdf_sha256': digest(output),
        'web_copy_sha256': digest(target), 'web_copy_identical': digest(output) == digest(target),
        'independent_current': verified, 'benchmark_current': benchmark_current,
        'inputs': {name: digest(ROOT/name) for name in evidence_inputs if (ROOT/name).is_file()},
        'core_source_hashes': {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path)
                               for path in sorted((ROOT/'vertice').glob('*.py'))},
        'example_result': result, 'integration_checks': integration_checks,
    }
    (evidence_dir/'sources.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    bounds = [region for region in r.regions if region['x'] < MARGIN-1 or region['x']+region['width'] > WIDTH-MARGIN+1
              or region['y']+region['height'] > HEIGHT-20
              or (region['y'] < HEIGHT-60 and region['y']+region['height'] > HEIGHT-65)]
    (evidence_dir/'layout.json').write_text(json.dumps({'regions': r.regions, 'bounds_issues': bounds}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if bounds:
        raise ValueError(f'{len(bounds)} elementos de texto fuera de márgenes; revisa evidence/report/layout.json')
    return record


def render_pdf(output, poppler=None):
    executable = poppler or shutil.which('pdftoppm')
    if not executable:
        bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
        executable = str(bundled) if bundled.exists() else None
    if not executable:
        raise RuntimeError('Instala Poppler o indica --poppler para renderizar y revisar las páginas.')
    directory = ROOT/'evidence/report/pages'
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run([executable, '-r', '110', '-png', str(output), str(directory/'page')], check=True)
    paths = sorted(directory.glob('page-*.png'))
    thumbs = []
    for path in paths:
        original = Image.open(path).convert('RGB')
        thumb = ImageOps.contain(original, (356, 505))
        tile = Image.new('RGB', (372, 534), '#e4e8df')
        tile.paste(thumb, ((372-thumb.width)//2, 8))
        ImageDraw.Draw(tile).text((14, 516), path.stem, fill='#153c3a')
        thumbs.append(tile)
    sheet = Image.new('RGB', (372*5, 534*2), '#e4e8df')
    for index, tile in enumerate(thumbs):
        sheet.paste(tile, ((index%5)*372, (index//5)*534))
    sheet.save(ROOT/'evidence/report/contact-sheet.png')
    rendered = [{'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': digest(path)} for path in paths]
    (ROOT/'evidence/report/render.json').write_text(json.dumps({
        'pdf_sha256': digest(output), 'rendered_pages': rendered,
        'renderer': 'Poppler pdftoppm', 'dpi': 110,
    }, indent=2)+'\n', encoding='utf-8')
    return [item['path'] for item in rendered]


def record_review(output):
    """Explicit receipt; call only after inspecting every rendered page."""
    source = read_json('evidence/report/sources.json')
    layout = read_json('evidence/report/layout.json')
    rendered = read_json('evidence/report/render.json')
    reader = PdfReader(output)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    checks = {
        'ten_pages': len(reader.pages) == 10,
        'ten_rendered_pages': len(rendered['rendered_pages']) == 10,
        'identical_web_copy': digest(output) == digest(ROOT/'web/docs/VerticeSDV_Informe.pdf'),
        'zero_bounds_issues': not layout['bounds_issues'],
        'render_matches_pdf': rendered['pdf_sha256'] == digest(output),
        'rendered_page_hashes_match': all(digest(ROOT/item['path']) == item['sha256'] for item in rendered['rendered_pages']),
        'source_receipt_matches_pdf': source['pdf_sha256'] == digest(output),
        'source_inputs_unchanged': all(digest(ROOT/name) == value for name, value in source['inputs'].items()),
        'independent_source_hashes_match': source['independent_current'],
        'benchmark_source_hashes_match': source['benchmark_current'],
        'no_replacement_character': '\ufffd' not in text,
    }
    if not all(checks.values()):
        raise ValueError(f'La revisión no puede registrarse: {checks}')
    receipt = {'generated_at': datetime.now(timezone.utc).isoformat(), 'status': 'pass',
               'pdf_sha256': digest(output), 'page_count': 10, 'reviewed_pages': list(range(1, 11)),
               'visual_review': 'Full-page PNG inspection completed; no clipping, overlap or missing glyphs observed.',
               'checks': checks, 'rendered_pages': rendered['rendered_pages'],
               'integration_state': source['integration_checks']}
    (ROOT/'evidence/report/qa.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--integration', default='evidence/report_integration.json')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--poppler')
    parser.add_argument('--record-review', action='store_true',
                        help='Registrar revisión visual ya realizada, sin volver a generar el PDF')
    args = parser.parse_args()
    output = ROOT/'docs/VerticeSDV_Informe.pdf'
    if args.record_review:
        receipt = record_review(output)
        print(json.dumps({'status': receipt['status'], 'pdf_sha256': receipt['pdf_sha256'], 'pages': 10}))
        return
    report = build(output, args.integration)
    if args.render:
        report['rendered_pages'] = render_pdf(output, args.poppler)
    print(json.dumps({key: report[key] for key in ('pdf', 'pages', 'pdf_sha256', 'web_copy_identical',
                                                  'independent_current', 'benchmark_current')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
