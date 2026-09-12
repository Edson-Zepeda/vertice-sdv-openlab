# Metodología de pruebas

## Fuente y alcance

Las pruebas parten del área Software de `Bootcamp SDV.pdf`, página 3, y del contrato documentado en `CONTRATO.md`. Evalúan Dijkstra propio, objetos del grafo, creación y modificación, consulta entre dos nodos, manejo de ausencia de ruta y evidencia reproducible. No prueban conducción autónoma ni amplían el trabajo a Visión o Electrónica.

## Oráculo independiente

`tests/independent_oracle.py` no importa el algoritmo entregado. Interpreta los pesos ordinarios como enteros en micro-unidades (1 unidad = 1,000,000 micro-unidades) y aplica Bellman-Ford con rondas sincrónicas. Cada ronda lee la anterior y relaja todas las aristas; no utiliza cola de prioridad, conjunto de asentados ni ayudantes del núcleo. Una segunda formulación, Floyd-Warshall, verifica el oráculo en 40 grafos.

Para cada consulta se compara el costo óptimo y la existencia de ruta. Se comprueba que cada conexión de la ruta existe en la dirección permitida, que su suma exacta coincide con el costo y que la ruta no incorpora ciclos. Los empates solo exigen la política local documentada: vecinos ordenados por ID y prioridad `(costo, ID)`. No se promete el camino lexicográficamente menor entre todos los óptimos.

## Casos y trazas

- `evidence/verification/cases.json`: 18 casos explícitos, con entrada y expectativa compartidas para Python local y navegador.
- `evidence/verification/seeded_graphs.json`: 160 grafos de 2 a 18 nodos, semilla 20260912, dirigidos y no dirigidos, distintas densidades, costos cero, microdecimales y costos grandes. Las consultas repetidas de un mismo grafo se eliminan: quedan 631.
- Enumeración reproducible: los 729 grafos dirigidos de tres nodos sin bucles, con cada arco ausente, de costo cero o uno; nueve pares por grafo, 6,561 consultas. Se genera directamente en la prueba con el producto cartesiano de esos tres estados. Es exhaustiva para ese dominio limitado, no una prueba formal de todo grafo posible.
- Propiedades adicionales: cambio de escala positivo, extensión desconectada, renombrado biyectivo e independencia del orden de entrada.
- Frontera: IDs, etiquetas, coordenadas, peso no negativo finito, precisión, límites 500/4000, claves repetidas, entrada profunda, Unicode inválido y tokens numéricos excesivos.
- Objetos: actualización y borrado de nodos/conexiones, adyacencia dirigida y no dirigida, rechazo atómico y protección de objetos y vistas externas.

Las trazas se reconstruyen paso a paso. `settle` debe retirar el mínimo disponible y nunca repetirse; `consider` debe referirse a una arista real; `relax` debe reducir estrictamente una estimación por el costo de esa arista. El orden de pasos es consecutivo y `finish` coincide con el resultado. Las distancias asentadas se contrastan con el oráculo; las restantes se conservan como tentativas, incluso si aún no son óptimas.

Los métodos de prueba, consultas y eventos son unidades distintas. No se suman para producir una cifra publicitaria de “pruebas”. Las repeticiones de rendimiento tampoco se cuentan como casos de corrección adicionales.

La ejecución instrumentada registró 38 métodos independientes aprobados y 59,070 eventos comprobados. La misma suite se ejecutó en CPython 3.10.11, 3.11.9, 3.12.14 y 3.14.7; los resultados por versión permanecen separados y no multiplican el número de casos únicos. La matriz posterior a la protección JSON volvió a aprobar los 38 métodos. Sus informes normalizados reutilizan los contadores de cobertura de la suite determinista intacta y enlazan el registro nuevo; no afirman haber capturado esos contadores otra vez. La procedencia figura en [independent.json](../evidence/verification/independent.json).

## Revisiones adicionales separadas

- [Protección JSON](AUDITORIA_JSON.md): regresiones sobre la implementación aplicada, equivalencia con un escáner independiente y memoria antes/después con entrada idéntica. La memoria de una entrada no constituye una cota para todas las entradas.
- [Mutaciones semánticas](AUDITORIA_MUTACIONES.md): copias aisladas con defectos plausibles verifican si las pruebas los detectan. Las modificaciones equivalentes se identifican aparte; el conteo no es una probabilidad de corrección del programa.
- [Entrega](AUDITORIA_ENTREGA.md): protección de fuentes al empaquetar, integridad, copias limpias y dependencias de autoría. Una prueba con archivos aislados no equivale a comprobar el ZIP público final.
- [Video](AUDITORIA_VIDEO.md): resultados matemáticos, sincronización con la narración, subtítulos, decodificación y muestras visuales del archivo exportado. Una imagen generada antes de exportar no sustituye un fotograma extraído del MP4.

Las verificaciones de interfaz, cancelación y duración tienen sus propios registros. Un ensayo de duración interrumpido se conserva como parcial y nunca se presenta como si hubiera completado el tiempo previsto.

## Ejecución

Desde la carpeta del proyecto, con Python 3.10 o posterior:

```text
python scripts/verify_independent.py
python scripts/probe_hostile_json.py evidence/verification/hostile_after.json
python scripts/benchmark.py
python scripts/verify_http.py
python scripts/verify_cli.py
python scripts/verify_json_guard.py
python scripts/verify_mutations.py
```

La suite usa exclusivamente la biblioteca estándar. El ejecutor escribe JSON y registro legible con fecha, versión de Python, plataforma, resultados y hashes de fuentes. La evidencia anterior a los arreglos se conserva con sufijo `_before`; no se sustituye por la ejecución exitosa.

La suite HTTP crea un servidor efímero y archivos sintéticos fuera de la web del proyecto. La suite de terminal copia el núcleo a una carpeta temporal con espacios y acentos, compara sus hashes y ejecuta procesos Python con `-S`, que deshabilita `site-packages`. Son verificaciones diferentes de la suite algorítmica; sus resultados se conservan por separado.

## Rendimiento

El benchmark contiene siete grafos y dos variantes por grafo (traza habilitada/deshabilitada), con nueve muestras por variante y dos calentamientos del solver. Publica todas las muestras, mediana, mínimo, máximo y percentil descriptivo por rango más próximo. Con nueve muestras, p95 coincide con el máximo; no es una estimación robusta de la cola de latencia.

`solver_only` mide la búsqueda sobre un Graph previamente construido. `json_to_json` incluye lectura JSON, validación, creación del grafo, búsqueda y serialización. Bellman-Ford se ejecuta fuera del cronómetro para contrastar el costo. La memoria se mide en otra ejecución con `tracemalloc`: representa asignaciones Python, no toda la RAM del proceso.

Los resultados en `evidence/verification/benchmark.json` corresponden a un solo equipo Windows con CPython, sin aislamiento de otras cargas. No garantizan el rendimiento de Pyodide, del navegador, de otros equipos ni de un sistema en tiempo real.

## Revisión final

Antes de publicar, comprobar que los hashes de la evidencia coincidan con la versión entregada y completar por separado la revisión de servidor, paridad de motor y experiencia de usuario. Si cambia el código que una evidencia cubre, volver a ejecutar solo la verificación afectada y mantener identificada la evidencia anterior.
