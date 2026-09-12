# ¿Las pruebas detectan errores del algoritmo?

Sí detectaron los **nueve defectos semánticos seleccionados**. Se examinó además una décima modificación que conserva el comportamiento bajo el contrato actual; se identificó como equivalente y no se contó como defecto detectado.

Esta revisión comprueba la sensibilidad de las pruebas ante errores concretos. No representa «100% de corrección», cobertura de todos los errores posibles ni una campaña exhaustiva de mutaciones.

## Método

`python scripts/verify_mutations.py` crea una copia independiente del núcleo y de las pruebas para cada variante dentro de `tmp/`. Aplica el cambio a esa copia, comprueba su sintaxis y ejecuta únicamente las comprobaciones pertinentes de la suite independiente. Sus aserciones y el oráculo Bellman–Ford de enteros no se modifican. La copia inicial sin mutaciones pasa todas las comprobaciones seleccionadas.

Cada subproceso tiene un límite de 20 segundos y 512 MiB. En la ejecución Windows se aplicaron mediante Job Objects el límite de memoria, el de CPU y un máximo de un proceso; el proceso padre también controla 20 segundos de tiempo transcurrido. Las diez variantes duraron aproximadamente 0.49–0.52 segundos cada una. No se involucró al servidor, al navegador ni a la prueba de duración en curso.

Los hashes antes y después confirman que permanecieron intactos los cinco archivos del núcleo, el servidor, cuatro archivos web y los dos archivos de pruebas independientes. La evidencia conserva entradas, resultados, errores de aserción, ubicación de cada copia y hashes.

## Defectos detectados

| Cambio intencional | Comprobación existente | Error observado |
|---|---|---|
| Terminar al descubrir el destino | `cheaper_detour` | Devuelve A→D con costo 9; A→B→C→D cuesta 3. |
| Conservar el primer predecesor tras mejorar el costo | `cheaper_detour` | Informa costo 3, pero devuelve A→D, cuya arista cuesta 9. La suma independiente del camino detecta la inconsistencia. |
| Admitir pesos numéricos negativos | `test_invalid_weights_are_explicitly_rejected` | El valor numérico −1 deja de producir el error de validación requerido. |
| Sumar mediante `float` | `decimal_exact`, `large_exact` | Produce `0.30000000000000004` en vez de `0.3`; también pierde la diferencia entre `1999999999999.999999` y `2000000000000`. |
| Cerrar un nodo al encolarlo | `cheaper_detour` | Devuelve costo 9 y da por alcanzado un destino que ni siquiera se consolidó. |
| Ignorar la dirección declarada | `directed_no_reverse` | Inventa una ruta C→B→A donde las aristas solo permiten A→B→C. |
| Representar un destino inalcanzable con costo cero | `disconnected` | Devuelve `"0"` en vez de `null`. La consulta de un nodo a sí mismo continúa pasando, lo que distingue el caso legítimo de costo cero. |
| Recorrer vecinos según orden de importación | `test_input_order_does_not_change_tie_route_or_trace` | Invertir el orden de entrada cambia la traza. El costo puede seguir siendo correcto; falla la reproducibilidad prometida. |
| Reemplazar un predecesor ante costos iguales | `deterministic_tie` | Sustituye S→A→T por S→B→T y registra una relajación que no mejora el costo. |

Todos fueron detectados mediante aserciones de comportamiento, sin depender de errores de sintaxis, agotamiento de memoria, bloqueos o vencimientos de tiempo. No sobrevivió ningún defecto no equivalente de esta selección; por tanto, esta revisión no requirió agregar pruebas redundantes.

## Modificación equivalente

Se cambió:

```python
if node in closed or cost != distances[node]:
```

por:

```python
if node in closed:
```

La variante pasó los 18 casos nombrados, la prueba de diferencia decimal mínima y la de independencia del orden de entrada.

La equivalencia tiene una explicación bajo las invariantes actuales: las mejoras son estrictas, los pesos no son negativos y la cola extrae por costo mínimo. Una entrada sustituida tiene un costo mayor que su reemplazo. El reemplazo se extrae antes y cierra el nodo; cuando llega la entrada vieja, la condición del conjunto cerrado ya la descarta. Si el algoritmo termina antes por el destino, esa entrada tampoco se procesa. No se insertan entradas por empates.

La equivalencia no se deduce únicamente de que las pruebas pasaron. Depende de esas invariantes, y no justifica eliminar la comprobación defensiva del código entregado. Esta auditoría no modifica el núcleo.

## Evidencia

- `evidence/verification/mutations.json`: registro completo de ejecución.
- `scripts/verify_mutations.py`: generación, aislamiento y verificación reproducibles.
- `tests/test_independent.py`: aserciones de comportamiento utilizadas sin cambios.
- `tests/independent_oracle.py`: referencia independiente y grafos de prueba.

Las rutas temporales registradas permiten inspeccionar esta ejecución local; las copias mutadas no forman parte del paquete de entrega. Para repetir la auditoría se generan nuevas copias, sin reutilizar o sobrescribir las anteriores.
