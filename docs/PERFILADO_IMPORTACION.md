# Perfil de importación y memoria

Auditoría acotada de SDV. Las mediciones originales de este perfil se realizaron sin cambiar producción y se conservan intactas. Posteriormente se aplicaron la protección estructural JSON y la eliminación de una serialización HTTP redundante. Su verificación se registra por separado en `evidence/verification/json_guard.json`; los datos originales del benchmark no se modificaron.

## Qué se midió

Se separaron lectura estricta del JSON, construcción del grafo, búsqueda y serialización. Se usaron tres repeticiones nuevas por caso, después de un calentamiento. `cProfile` y `tracemalloc` se ejecutaron aparte de esas mediciones. Los casos de 500 nodos reutilizan exactamente el grafo guardado del benchmark, recortando su lista de conexiones a 500, 2000 y 4000; los dos casos pequeños tienen 8 conexiones por nodo y semilla fija.

Durante esta captura se renderizaba el video del proyecto y se ejecutaba una prueba de navegador. Los tiempos describen esa captura: **no sustituyen el benchmark final ni permiten atribuir las diferencias exclusivamente al tamaño**. El perfil cuenta llamadas reales, pero su instrumentación también aumenta el tiempo.

| Nodos | Conexiones | Lectura JSON, ms | Construcción, ms | Búsqueda, ms | Serialización, ms | JSON completo, ms |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 400 | 0.76 | 7.86 | 1.54 | 1.03 | 12.33 |
| 200 | 1600 | 2.99 | 32.96 | 8.39 | 5.84 | 51.27 |
| 500 | 500 | 1.86 | 14.14 | 5.31 | 4.21 | 26.16 |
| 500 | 2000 | 4.06 | 46.72 | 3.93 | 2.86 | 56.23 |
| 500 | 4000 | 10.94 | 135.55 | 28.69 | 19.32 | 200.36 |

Son medianas de cada fase; su suma no tiene por qué coincidir con la mediana de otra ejecución completa. El destino puede asentarse antes en un grafo más conectado; por eso el costo de búsqueda no depende solo de la cantidad de conexiones.

## Causa del costo

La construcción y validación dominan. En una ejecución instrumentada de 500 nodos y 4000 conexiones, `Graph.from_dict` acumuló 375.01 de 493.14 ms. `parse_weight` acumuló 146.90 ms y las comprobaciones de inserción de conexiones 65.86 ms. Los valores acumulados se solapan: no deben sumarse entre sí.

No se encontró una búsqueda cuadrática accidental de conexiones duplicadas. Cada inserción consulta diccionarios de nodos, conexiones y adyacencia; no recorre las conexiones existentes. Para entradas admitidas, la construcción tiene trabajo esperado O(V + E + L), donde L es el texto validado y está acotado por las longitudes del contrato. Esta afirmación corresponde a las operaciones observadas en el código, no a un ajuste estadístico de cinco puntos.

| Operación del perfil máximo | Llamadas | Interpretación |
|---|---:|---|
| `Graph.from_dict` | 1 | Una construcción |
| `parse_weight` | 4000 | Una conversión por conexión |
| `_check_edge` | 4000 | Una comprobación de inserción por conexión |
| `_check_object` | 4502 | Solicitud, grafo, 500 nodos y 4000 conexiones |
| `validate_id` | 20755 | Incluye 8000 comprobaciones repetidas de extremos al insertar |
| `Decimal.as_tuple` | 8000 | Dos lecturas de la misma tupla por peso |
| `_decimal_context` | 4001 | Un contexto por peso y uno para la búsqueda |
| `neighbors` | 253 | Solo nodos expandidos antes del destino |

`Decimal` mantiene costos exactos y aísla el contexto global. La validación de límites, claves repetidas, tipos y adyacencia cumple el contrato; omitirla para acelerar la importación debilitaría el proyecto. Las repeticiones de ID y tupla son costos constantes, no un cambio de orden de complejidad.

## Mejora de serialización aplicada

El servidor local ejecutaba `json.loads(solve_json(text))` y después `_json` serializaba de nuevo el mismo resultado. La respuesta medida contenía 348811 bytes: esa conversión repetida tardó 16.93 ms de mediana en tres muestras, frente a 0.058 ms para codificar directamente el JSON ya calculado. En las tres comparaciones, los bytes fueron idénticos. Estos tiempos describen el microperfil anterior, no la latencia de la versión actual.

La versión actual llama `solve_payload(load_json(text))` y deja una sola serialización en `_json`. Se mantienen el cargador estricto, los encabezados, los códigos de estado y el tratamiento de errores. La comparación local de los seis ejemplos conserva cuerpos idénticos byte a byte. Esta comprobación de cuerpos no sustituye las pruebas de peticiones HTTP, que tienen evidencia independiente. No se ha presentado un nuevo benchmark a partir de esta modificación.

En el núcleo se puede guardar `parts = result.as_tuple()` y leer `parts.digits` y `parts.exponent`, evitando 4000 asignaciones en ese caso. No se atribuye una ganancia de latencia a ese cambio sin una comparación controlada. No se recomienda sustituir validaciones completas por un cargador permisivo.

## Memoria: límites y evidencia

El máximo contractual es 500 nodos, 4000 conexiones y 2 MiB de texto JSON. No es un límite de memoria de proceso.

Para la solicitud admitida de 500 nodos y 4000 conexiones, la búsqueda con traza produjo 3177 eventos. Su pico de asignaciones Python fue 1463746 bytes (1.40 MiB); el recorrido completo JSON→JSON alcanzó 5153991 bytes (4.92 MiB). `tracemalloc` mide asignaciones observadas de Python, no la RAM total, las bibliotecas nativas ni WebAssembly.

Antes de aplicar la protección se probó un JSON sintácticamente válido de 2097151 bytes con 699050 objetos vacíos. Se rechazó correctamente porque una solicitud debe ser un objeto, pero la decodificación previa alcanzó 50676060 bytes (48.33 MiB) de asignaciones Python. Este caso demostró una amplificación de memoria anterior a la validación del grafo. Su captura original permanece en `evidence/profiling/json_memory.json`; no es un máximo de todas las entradas posibles.

## Protección estructural aplicada

`load_json` verifica primero tipo, Unicode válido y tamaño UTF-8. Antes de invocar el decodificador estándar, `_guard_json_structure` limita a 5000 las aperturas de objetos/arreglos y a 50000 las comas/dos puntos fuera de cadenas. Una solicitud válida con todos los campos y el grafo máximo utiliza 4504 contenedores y 36012 signos de puntuación. El escaneo ignora el contenido de las cadenas, incluidas comillas y barras invertidas escapadas; `json.loads` conserva la responsabilidad de la sintaxis, los números y las claves duplicadas.

El caso de 699050 objetos ahora se rechaza **antes de decodificarlo**. El pico integrado observado fue **2097212 bytes (2.00 MiB)**, frente a **50676060 bytes (48.33 MiB)** de la captura histórica: una reducción observada de aproximadamente 95.9%. La evidencia verifica que tamaño y SHA-256 de la entrada coinciden exactamente. Se conserva explícitamente la diferencia entre la medición anterior y esta nueva captura; no se ejecutó un benchmark de latencia.

La protección mitiga la amplificación, pero no impone un techo absoluto de memoria. Los ejemplos de 24999 campos y 50000 números decimales siguen dentro del límite estructural y requieren más memoria que su texto antes de ser rechazados por el esquema: se observaron **7371791 bytes (7.03 MiB)** y **5647604 bytes (5.39 MiB)**, respectivamente. Las cifras figuran en `json_guard.json`; corresponden a asignaciones Python, no a memoria del navegador o del proceso completo.

La revisión aislada previa observó menos de 1 ms de escaneo en el grafo máximo normal y aproximadamente 28–32 ms con etiquetas válidas cargadas de corchetes o puntuación. Son mediciones históricas de la propuesta: no deben presentarse como un costo universal ni como tiempos actuales de la implementación integrada. El trabajo permanece lineal y las cadenas legítimas no se rechazan por contener esos caracteres.

Las regresiones de `tests/test_json_guard.py` verifican grafos máximos, umbrales exactos, rechazo previo al decodificador, escapado y Unicode, y conservación de errores sintácticos y numéricos. La comparación con la propuesta y un escáner independiente se registra junto con la matriz de versiones Python en `evidence/verification/json_guard.json`.

## Límites del resto de la ejecución

La traza almacena eventos, no copias completas del grafo en cada paso. Si A es el número de entradas de adyacencia explorables y R el número de relajaciones exitosas, hay como máximo V + A + 2R + 3 eventos; R ≤ A y A ≤ 2E. Con los límites actuales, 24503 es una cota conservadora de eventos para una consulta. El tamaño de cada evento también depende de los ID y costos admitidos. Esta cota no incluye la estructura temporal que crea el decodificador JSON.

El navegador añade copias de mensajes entre la interfaz y el worker, texto JSON, objetos JavaScript y el runtime Python/Wasm. `engine.js` serializa los trabajos y cancela el worker activo al agotar el tiempo; la cola interna de trabajos no tiene un máximo general. El flujo normal de la interfaz utiliza cancelación, pero el motor por sí solo no promete una cota de memoria para un número arbitrario de solicitudes encoladas.

El módulo Pyodide incluido contiene crecimiento de memoria WebAssembly y un `getHeapMax` de 4294901760 bytes. Es un techo técnico del runtime observado en el archivo, **no una reserva de memoria, medición real ni garantía de disponibilidad del navegador**. La aplicación no define un presupuesto menor de RAM. El servidor escucha solo en loopback y limita a 16 solicitudes simultáneas; tampoco impone una cuota de RAM de proceso.

## Reproducción

```powershell
python scripts/profile_import.py --concurrent-workload "describir carga concurrente" --output-name import_profile_repeat
python scripts/verify_json_guard.py
```

`profile_import.py` genera datos acotados, tres muestras por fase y un perfil separado; se debe usar un nombre de salida nuevo para conservar la captura original. `profile_json_memory.py` se conserva como fuente histórica y no se volvió a ejecutar sobre su archivo de salida original. `import_profile.json` contiene todas las muestras originales, conteos y huellas del núcleo; `json_memory.json` conserva el tamaño, SHA-256 y resultado previo del caso inválido.

`verify_json_guard.py` reproduce la mitigación actual sin peticiones HTTP, compara el mismo texto con la captura original, ejecuta las regresiones y guarda la evidencia integrada en `evidence/verification/json_guard.json`. Se pueden agregar varios argumentos `--python RUTA` para verificar otros intérpretes locales. Estos diagnósticos no se mezclan con tiempos de benchmark ni con una calificación de corrección universal.
