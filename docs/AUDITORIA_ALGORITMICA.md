# Auditoría independiente del núcleo

La primera implementación calculó correctamente los caminos ensayados, pero todavía no estaba lista para entregarse: tres defectos en entradas inválidas podían interrumpir la API o consumir trabajo desproporcionado. Se registró la evidencia antes de corregirlos. No se atribuyeron al producto los errores de los propios fixtures.

## Hallazgos antes de la corrección

| ID | Prioridad | Reproducción | Resultado inicial | Corrección verificada |
|---|---|---|---|---|
| ALG-01 | P1 | Número JSON `1e999999999999999999999999999999999` como peso; solicitud de 219 bytes | Escapaba `decimal.InvalidOperation`, en vez de `ValidationError` | Conversión numérica acotada y captura de `DecimalException`; ambos signos de exponente producen un error controlado |
| ALG-02 | P1 | Número JSON `0.1` seguido de 20,000 ceros | El valor Decimal evitaba el límite de texto; eliminar ceros cortando tuplas repetidamente era cuadrático | Límite de 100 caracteres por token numérico, 100 dígitos en Decimal directo y recorte lineal |
| ALG-03 | P2 | Clave inesperada con sustituto Unicode aislado `\ud800` | El mensaje de validación no podía codificarse en UTF-8 | Claves representadas de forma segura y mensajes acotados |

La sonda ALG-02 tardó 445.426 ms con 20,000 ceros y 6.2337 ms con 2,000 en la ejecución inicial. Después de corregirla, ambas entradas se rechazaron de forma controlada. Son observaciones diagnósticas de una ejecución, no una garantía de latencia ni una comparación estadística de rendimiento.

Evidencia conservada: `evidence/verification/hostile_before.json`, `hostile_after.json`, `independent_before.json` y sus registros. Los JSON incluyen fechas y SHA-256 del código ejecutado. El resultado inicial de la suite fue 33 métodos: un fallo y tres errores, correspondientes a los tres hallazgos; dos errores son subcasos del mismo defecto de exponente.

## Cómo se verificó la corrección

La suite posterior incluye 38 métodos y comprueba 18 casos explícitos, 160 grafos sintéticos con semilla fija y 631 consultas únicas. Además enumera los 729 grafos dirigidos de tres nodos sin bucles propios donde cada arco puede faltar o costar cero o uno: sus nueve pares producen otras 6,561 consultas. Compara costos con Bellman-Ford escrito por separado, con enteros en micro-unidades. Se verificaron 59,070 eventos de traza, incluyendo selección del mínimo, relajación estricta, costos, aristas y distancias asentadas. Floyd-Warshall contrasta el propio oráculo en 40 de los grafos generados. La enumeración es exhaustiva únicamente en ese dominio pequeño.

Además de valores válidos, se prueban mutaciones atómicas, aislamiento de objetos, máximo de nodos y conexiones, precisión decimal bajo contextos hostiles, JSON duplicado y profundo, Unicode inválido y representaciones numéricas desproporcionadas. La evidencia posterior y sus hashes se encuentran en `evidence/verification/independent.json`.

Los mismos 38 métodos aprobaron en CPython 3.10.11, 3.11.9, 3.12.14 y 3.14.7. Las ejecuciones por versión son comprobaciones de compatibilidad del mismo conjunto; no se cuentan como nuevos escenarios del algoritmo. La auditoría posterior de terminal encontró y corrigió otro defecto, en la lectura UTF-8 de la entrada estándar; se documenta en `COMPATIBILIDAD.md`.

## Límites de esta conclusión

Las pruebas apoyan el cumplimiento del contrato dentro de sus límites, pero no constituyen una demostración formal. Estos grafos son didácticos, no rutas medidas de un vehículo. Una ruta válida en Python tampoco demuestra por sí sola que la interfaz, el servidor y el motor del navegador presenten correctamente el resultado: tienen verificaciones separadas.

Se conserva una distinción crítica: al detenerse Dijkstra al asentar el destino, las distancias de otros nodos pueden seguir siendo tentativas. En el caso `tentative_is_not_final`, X conserva 50 mientras su óptimo global es 3. Solo S y T están asentados; mostrar 50 como definitivo sería incorrecto.
