# Verificación de la protección JSON integrada

La protección ya está aplicada en `vertice/codec.py`, antes de la decodificación. La adaptación HTTP de `server.py` también elimina la serialización redundante. Esta revisión verificó los cambios sin modificar nuevamente el núcleo ni el servidor y conservó los archivos originales del perfil.

## Resultado

| Comprobación | Resultado |
|---|---|
| CPython 3.10.11 | 25 pruebas de núcleo, 38 independientes y 8 de protección JSON pasan. |
| CPython 3.11.9 | Las mismas 71 pruebas pasan. |
| CPython 3.12.14 | Las mismas 71 pruebas pasan. |
| CPython 3.14.7 | Las mismas 71 pruebas pasan. |
| Producción frente a propuesta revisada y escáner independiente | 1628 comparaciones coinciden. |
| Copia del núcleo web y manifiesto SHA-256 | Cuatro archivos idénticos al núcleo nativo. |
| Cuerpos de respuesta de seis ejemplos | La serialización anterior y la actual producen bytes idénticos. |
| Núcleo, servidor y fuentes históricas durante la revisión | Hashes antes/después idénticos. |

Las 1628 comparaciones incluyen 600 serializaciones de grafos pequeños con Unicode y escapado, 10 solicitudes válidas máximas, 18 casos de umbral y 1000 fragmentos léxicos mutados con semilla fija. El escáner independiente usa una máquina de estados por carácter; la implementación productiva busca comillas y comprueba las barras invertidas anteriores. Las entradas malformadas de esta comparación evalúan el recuento estructural, no reemplazan pruebas de sintaxis JSON.

Las ocho regresiones nuevas comprueban que los máximos válidos se aceptan incluso cuando las etiquetas obligan a recorrer el texto completo; que un exceso se rechaza antes de llamar al decodificador; y que se mantienen Unicode, escapado, decimales exactos, límites de bytes y errores del parser. La misma suite independiente contrasta resultados y trazas con Bellman–Ford.

## Memoria observada

La entrada hostil tiene **2097151 bytes**, **699050 objetos vacíos** y SHA-256 `2b5db9948de9425f8b0c4e06e760c25bc7c3a307b633776792d4e4d6716d50ed`.

| Medición | Pico de asignaciones Python |
|---|---:|
| Captura histórica sin protección | 50676060 bytes / 48.33 MiB |
| Versión integrada | 2097212 bytes / 2.00 MiB |

La reducción observada es aproximadamente **95.9%**. El antes procede de la evidencia histórica preservada, no de una nueva ejecución bajo las condiciones actuales. El después incluye la comprobación inicial del tamaño UTF-8. Esta es una comparación de asignaciones Python con entrada idéntica; no un benchmark de rendimiento, una medición de RAM total ni una garantía universal.

Los límites estructurales tampoco fijan un máximo absoluto de memoria. Un objeto inválido con 24999 campos, todavía dentro del umbral, alcanzó **7371791 bytes** antes del rechazo de esquema. Una lista de 50000 decimales alcanzó **5647604 bytes**. Esos resultados se conservaron para hacer explícito el alcance de la mitigación.

## Diferencia entre versiones resuelta en la prueba

La primera prueba nueva suponía que `load_json` debía rechazar siempre una anidación de 1500 niveles. CPython 3.12/3.14 puede decodificarla, mientras que 3.10/3.11 alcanza antes su límite de recursión. El proyecto no promete un umbral propio de profundidad.

Se corrigió la expectativa de la prueba para verificar el contrato público: `solve_json` rechaza esa entrada, ya sea por el límite del parser o porque una solicitud debe ser un objeto con los campos requeridos. No fue necesario cambiar producción. Los logs iniciales se conservan con sufijo `.initial`; los logs finales reflejan la prueba corregida y todas las versiones pasan.

## Reproducción y alcance

```console
python scripts/verify_json_guard.py
python -m unittest discover -s tests -p test_json_guard.py -v
```

Se pueden añadir varios argumentos `--python RUTA` al verificador para repetir la matriz con intérpretes locales. El resultado detallado está en `evidence/verification/json_guard.json`, con versiones, conteos, logs, hashes, tamaños y fuentes.

La comprobación de cuerpos HTTP es local; la suite de peticiones HTTP y la validación real de Pyodide son revisiones separadas. Las 71 pruebas por versión son las mismas pruebas repetidas para compatibilidad, no 284 comportamientos distintos. Ningún conteo de esta auditoría equivale a una calificación de corrección perfecta.
