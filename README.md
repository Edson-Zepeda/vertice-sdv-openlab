# VÉRTICE / SDV

Edita un grafo y explora cómo Dijkstra encuentra la ruta de menor costo.

Implementación propia en Python, con clases `Node`, `Edge`, `Graph` y `DijkstraSolver`. La interfaz reproduce las decisiones del mismo núcleo que se ejecuta en terminal. Corresponde al perfil **Software**, página 3 de **Bootcamp SDV.pdf**.

[Informe](docs/VerticeSDV_Informe.pdf) · [Guía de defensa](docs/DEFENSA.md) · [Video](web/media/VerticeSDV_Demo.mp4). La página **Proyecto** del estudio reúne los entregables.

## Abrir

En Windows, abre **Iniciar.cmd**. Requiere Python 3.10 o posterior y no instala paquetes.

En cualquier sistema, abre una terminal en la carpeta extraída del proyecto y ejecuta:

```sh
python server.py --open
```

Abre `http://127.0.0.1:8770`. Si el puerto está ocupado: `python server.py --port 8771 --open`.

Si tu instalación usa el comando `python3`, úsalo en lugar de `python` en los ejemplos. La matriz documentada se ejecutó en Windows; no se atribuyen pruebas locales a Linux o macOS.

El modo local funciona sin Internet. La versión estática en `web/` incluye Pyodide y las fuentes; debe servirse mediante HTTP o HTTPS, no abriendo el HTML como un archivo. En una publicación remota se necesita descargar la aplicación; no se promete una instalación sin conexión persistente.

## Usar

1. Abre un ejemplo o crea nodos y conexiones.
2. Elige inicio y destino y pulsa **Calcular ruta**.
3. Abre **Pasos** para recorrer el algoritmo, o edita el grafo y vuelve a calcular.

El resultado suma los costos de las conexiones. Mover un nodo cambia su posición visual, no el peso de sus conexiones. Deshacer y rehacer permiten recuperar ediciones. Exporta JSON para conservar un archivo propio.

## Qué incluye

| Entregable | Archivo o carpeta |
|---|---|
| Algoritmo, clases y formato JSON | `vertice/` |
| Editor y visualización de la ejecución | `web/` |
| Seis grafos didácticos | `examples/` |
| Contrato de requisitos | `docs/REQUISITOS.md` |
| Clases, métodos e invariantes | `docs/API.md`, `docs/ARQUITECTURA.md` |
| Argumento de corrección y complejidad | `docs/ALGORITMO.md` |
| Revisión crítica y correcciones | `docs/AUDITORIA.md` |
| Pruebas independientes y mediciones | `tests/`, `evidence/verification/` |
| Informe, video y presentación del proyecto | `docs/VerticeSDV_Informe.pdf`, `web/proyecto.html`, `web/media/` |
| Guía para explicar y demostrar el trabajo | `docs/DEFENSA.md` |

## Formato de un grafo

```json
{
  "schema_version": 1,
  "directed": false,
  "nodes": [
    {"id": "A", "label": "Inicio", "x": 100, "y": 200},
    {"id": "B", "label": "Destino", "x": 400, "y": 200}
  ],
  "edges": [{"id": "e1", "source": "A", "target": "B", "weight": "0.25"}]
}
```

Usa pesos como texto decimal para conservar sus cifras entre aplicaciones. Se admiten valores desde 0 hasta `1000000000000`, con un máximo de seis decimales, 500 nodos y 4000 conexiones. No se aceptan pesos negativos ni conexiones paralelas para el mismo par. Los bucles propios y los ciclos de costo cero se admiten. Consulta `docs/API.md` para los límites completos.

## Verificar

Python 3.10 o posterior basta para las pruebas Python. La comprobación de la cola del navegador requiere además Node.js 22 o posterior; CI usa Node.js 24.

```sh
python -m unittest discover -s tests -p "test_*.py" -v
node tests/engine_queue.mjs
python scripts/benchmark.py --help
```

Las pruebas del algoritmo utilizan un oráculo Bellman-Ford independiente con costos enteros. Las mediciones distinguen tiempo del solucionador y procesamiento completo de JSON; no deben confundirse con tiempos de un navegador o vehículo.

También puedes usar el núcleo desde terminal:

```sh
python -m vertice.cli validate examples/desvio.json
python -m vertice.cli solve examples/desvio.json --source S --target T --json
```

El ejemplo devuelve costo `11`. Las pruebas locales y el archivo de GitHub Actions son evidencias diferentes: un flujo definido no significa que haya sido ejecutado en GitHub.

## Reconstruir la web

```sh
python scripts/sync_web_core.py
```

Este paso copia los archivos del núcleo byte a byte y actualiza el manifiesto que comprueba el navegador. Pyodide y las fuentes ya están incluidos; sus versiones, licencias y hashes están en `evidence/dependencies/` y `web/vendor/`.

## Reconstruir los entregables

La aplicación no necesita estas herramientas. Para regenerar documentos o video, crea un entorno con `python -m venv .venv`. Actívalo con `.venv\Scripts\Activate.ps1` en PowerShell o `source .venv/bin/activate` en Linux/macOS, y ejecuta:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_report.py --render
python scripts/build_film.py --render
python scripts/verify_film.py
```

El PDF requiere Poppler (`pdftoppm`) para revisar sus páginas. El video requiere FFmpeg y FFprobe. Esos programas deben estar disponibles en la terminal. La voz ya está incluida; cambiar su guion necesita Internet para volver a sintetizarla. El verificador del video también funciona en la entrega extraída, sin los archivos temporales del render.

Puedes indicar los ejecutables sin cambiar PATH: `build_report.py` acepta `--poppler "ruta/al/pdftoppm"`; `build_film.py` y `verify_film.py` aceptan `--ffmpeg "ruta/al/ffmpeg" --ffprobe "ruta/al/ffprobe"`. En Windows, incluye `.exe`; las rutas con espacios deben ir entre comillas. Son rutas al archivo ejecutable, no a su carpeta.

Las versiones directas de Python están fijadas; esto no congela todas sus dependencias transitivas ni garantiza que nuevas voces o PDF sean idénticos byte a byte. Revisa visualmente cualquier PDF o video regenerado antes de entregarlo.

## Crear el ZIP

Desde un clon Git con todos los archivos guardados en un commit y sin cambios pendientes:

```sh
python scripts/package_release.py --output ../VerticeSDV_Proyecto.zip
```

El ZIP contiene `MANIFEST.json` con el hash de cada archivo. Se generan además `.sha256` y `.receipt.json`. La salida debe quedar fuera del directorio fuente. El empaquetador comprueba licencias, dependencias, copia del núcleo web y PDF; usa fecha del commit y metadatos estables. Repetirlo con los mismos archivos y la misma versión de zlib produce el mismo ZIP. `--allow-dirty` sirve para revisión local y marca el paquete como no publicable.

La copia extraída se ejecuta directamente; volver a empaquetarla requiere un clon con historial Git. No se necesita Git para abrir el estudio, resolver grafos o verificar el video.

## Alcance

La ruta óptima corresponde a los pesos del grafo. Los ejemplos son didácticos. No se realizaron pruebas de conducción ni integración con un vehículo: no son entregables de este perfil del documento. Al detenerse en el destino, solo las distancias de nodos asentados son definitivas; las demás pueden mejorar si se continúa buscando.
