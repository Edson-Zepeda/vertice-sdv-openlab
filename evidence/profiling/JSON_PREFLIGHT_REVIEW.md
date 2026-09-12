# Revisión independiente del límite estructural JSON

Estado: propuesta aislada, sin cambios en producción. Revisión del archivo `scripts/experiment_json_preflight.py`, comparada con `vertice/codec.py` y `vertice/graph.py`. Evidencia reproducible: `python scripts/review_json_preflight.py`; resultados en `json_preflight_review.json`.

## Decisión

Recomiendo integrar el límite estructural después de concluir la prueba de duración vigente. Reduce una amplificación de memoria reproducida, añade unas 30 líneas y conserva la aceptación de los grafos contemplados por el contrato. La necesidad procede de un caso observado, no de una hipótesis de exposición pública: el servidor está limitado a loopback y el navegador ejecuta una tarea a la vez.

No lo describiría como un límite de RAM, un analizador JSON alternativo ni una prueba de seguridad completa. El límite de entrada, el analizador estándar, las claves duplicadas, los límites numéricos y la validación del grafo siguen siendo necesarios.

## Resultado

5,321 comprobaciones aisladas correctas con semilla `260912`:

- 1,431 comparaciones de aceptación y resultado del grafo: 350 grafos aleatorios en cuatro serializaciones, 12 variantes del grafo de 500 nodos y 4,000 conexiones, y 19 entradas numéricas límite.
- 3,883 comparaciones del guardado estructural con un escáner independiente basado en estados carácter por carácter. Incluyen esas entradas, la solicitud de cada grafo máximo, 40 casos a ambos lados de los límites y 2,400 fragmentos léxicos mutados.
- 6 equivalencias exactas de bytes en respuestas de la alternativa de serialización HTTP.
- 1 comprobación de que los siete archivos de producción revisados permanecieron idénticos.

Se probaron etiquetas Unicode, comillas, barras invertidas, corchetes y puntuación; etiquetas con 80 caracteres; campos opcionales; JSON compacto y con sangría; Unicode literal y escapado; pesos de 0 a 10¹²; seis decimales; texto decimal de 100 caracteres; exponentes numéricos y límites que deben rechazarse.

## Hallazgos

| Aspecto | Resultado | Implicación |
|---|---|---|
| Límite válido más amplio | Una solicitud con todos los campos, 500 nodos y 4,000 conexiones contiene **4,504 contenedores y 36,012 comas/dos puntos externos**. Su profundidad es 4. | Los umbrales 5,000/50,000 dejan margen. El recuento previo de 37,012 era una sobreestimación. |
| Ruta rápida | Cuenta apariciones también dentro de las cadenas. Su cuenta siempre es mayor o igual que la cantidad estructural. | Puede activar trabajo innecesario; no puede dejar pasar un exceso por subcontar estructura. |
| Ruta lenta | La búsqueda de comillas considera la paridad de barras invertidas inmediatamente anteriores. El recorrido es lineal; los segmentos examinados no crecen de forma cuadrática. | No se encontró discrepancia con el escáner independiente. La gramática continúa a cargo de `json.loads`. |
| Caso de 699,050 objetos vacíos | Pico anterior: 50,676,060 bytes. Con propuesta: **2,097,244 bytes** trazados. Entrada: 2,097,151 bytes. | Reducción observada de aproximadamente **95.9%**. El pico de la propuesta incluye la codificación UTF-8 inicial. |
| Cadenas incompletas | El escáner deja que el analizador reporte el error de sintaxis. | El millón de caracteres dentro de una cadena sin cerrar no produce objetos JSON intermedios. |
| Profundidad | 900 niveles se rechazan por esquema; 1,500 activan el manejo existente de recursión. | El prototipo no impone un límite propio de profundidad. Estos casos no mostraron una amplificación importante. |
| Memoria residual | 24,999 campos quedan debajo del límite de puntuación y alcanzan **7,371,613 bytes** trazados antes del rechazo del esquema. 50,000 decimales alcanzan **5,647,578 bytes**. | Los contadores reducen la amplificación; no garantizan un máximo de 2 MiB de RAM. |
| Sobrecosto | Grafo máximo normal: mediana 0.77–0.84 ms. Etiquetas llenas de `[` o `,`: 28–29 ms. Etiquetas mixtas Unicode/puntuación: 30–32 ms. | La afirmación «menos de 1 ms» debe restringirse al caso medido normal. La ruta lenta también afecta entradas legítimas. |

Los tiempos pertenecen a este equipo con CPython 3.11.9 y una prueba de navegador concurrente. `tracemalloc` mide asignaciones Python, no memoria total del proceso, del navegador ni del sistema operativo. No se han inferido límites de memoria superiores a partir de estos ejemplos.

## Condiciones de integración

1. Ubicar el escaneo después de comprobar tipo, Unicode válido y tamaño UTF-8; antes de `json.loads`.
2. Mantener el analizador estándar y todas sus funciones de conversión y detección de duplicados. Los nuevos errores describen límites de estructura, sin prometer que el JSON sea válido.
3. Nombrar los umbrales y explicar su relación con los máximos de nodos/conexiones. Si cambia ese contrato, revisar también estos límites y el caso de grafo máximo.
4. No agregar un límite de profundidad ni sustituir el escáner por expresiones regulares complejas sin una necesidad medida.
5. Añadir unas pocas regresiones estables a las pruebas del núcleo: máximo válido con cadenas que fuerzan la ruta lenta; límite exacto y exceso; escapado; objeto ancho hostil. Mantener este fuzz como evidencia separada, no multiplicar innecesariamente la suite ordinaria.
6. Tras integrar: sincronizar el núcleo del navegador, verificar sus hashes, ejecutar regresiones de importación/HTTP y volver a probar importación real en Pyodide. La prueba de duración anterior debe seguir identificando la versión exacta que ejecutó.

## Serialización HTTP propuesta

El archivo `server_single_serialization.patch` es una propuesta no aplicada. Cambia el import a `solve_payload` y reemplaza:

```python
result = json.loads(solve_json(text))
```

por:

```python
result = solve_payload(load_json(text))
```

La implementación de `_json`, sus encabezados, errores y escritura no cambian. Se evita codificar el resultado completo en texto y volverlo a decodificar antes de la codificación HTTP definitiva. En los seis ejemplos, el cuerpo final es idéntico byte a byte. La propuesta conserva el parser estricto de entrada, incluidas las claves duplicadas y los decimales exactos.

El microperfil previo encontró aproximadamente 16.9 ms en la recodificación redundante de una respuesta de 348,811 bytes. Este informe no vuelve a medir esa cifra ni la confunde con el tiempo total de respuesta. La comprobación HTTP completa corresponde realizarla si se aplica el parche.
