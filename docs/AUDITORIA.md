# Auditoría crítica de VÉRTICE / SDV

## Criterio

La referencia es exclusivamente el perfil Software de la página 3 de `Bootcamp SDV.pdf`. Se verificaron su texto y la [matriz de requisitos](REQUISITOS.md): Dijkstra propio en Python o C++, orientación a objetos, creación/edición y consulta del grafo, documentación de clases, representación de relaciones, distintas pruebas y ausencia de ruta. La interfaz gráfica es opcional; el documento no fija una rúbrica numérica ni duración de presentación para este perfil. El video y la publicación son recursos adicionales del proyecto.

La revisión empezó antes de implementar: `REQUISITOS.md` quedó versionado en el primer commit. No se encontró una implementación previa de este reto en los proyectos y tareas revisados; se construyó una nueva. Esto describe el alcance de la búsqueda realizada, no una inspección exhaustiva de toda la computadora.

Una interfaz atractiva no demuestra que Dijkstra sea correcto. Para considerar completa la entrega, el código debe calcular costos mínimos, conservar la exactitud de los datos, representar el algoritmo con clases, explicar sus decisiones y permitir que otra persona reproduzca los resultados. El valor adicional debe ayudar a comprobar o comprender esos requisitos.

## Defectos encontrados y correcciones

| Prioridad | Hallazgo observado | Por qué importaba | Corrección aplicada | Evidencia |
|---|---|---|---|---|
| Alta | Un exponente JSON extremo escapaba como excepción de Decimal. | Un archivo pequeño podía interrumpir la operación sin un error comprensible. | Conversión numérica controlada y límites explícitos del token. | [Antes](../evidence/verification/hostile_before.json), [después](../evidence/verification/hostile_after.json) |
| Alta | Miles de ceros fraccionarios causaban normalización cuadrática. | El límite del archivo no bastaba para una respuesta ágil. | Validación temprana y normalización lineal. | [Auditoría algorítmica](AUDITORIA_ALGORITMICA.md) |
| Media | El contexto Decimal heredaba atributos globales. | Otro código Python podía alterar precisión o exponentes del cálculo. | Contexto íntegramente explícito, con pruebas de contexto hostil. | [Núcleo](../tests/test_core.py), [pruebas independientes](../tests/test_independent.py) |
| Alta | Importar mediante JSON.parse perdía el texto original de números. | Un peso fuera de límite podía convertirse en uno aceptado; se perdían decimales. | El texto original se valida en Python antes de normalizar el grafo. | [Transporte e importación](AUDITORIA_HTTP.md), [verificación de navegador](../evidence/browser/worker.json) |
| Media | Cancelar una solicitud del motor podía afectar otras pendientes. | Una interacción interfería con una operación independiente. | Cola de trabajo, cancelación individual y aislamiento de generaciones del worker. | [Pruebas del adaptador](../tests/engine_queue.mjs) |
| Media | Tipografía auxiliar pequeña y exceso de texto. | La densidad comprometía la lectura. | Tipografía ampliada y menos texto decorativo. | [Auditoría de interfaz](../evidence/ui/README.md) |
| Media | Las fuentes se pedían a un dominio externo. | La apariencia dependía de otra conexión de red. | Fuentes abiertas incluidas localmente con licencia y procedencia. | [Manifiesto de fuentes](../evidence/dependencies/fonts.json) |
| Media | Cabeceras Origin y Content-Type duplicadas se aceptaban. | Una solicitud ambigua podía recibir tratamiento inconsistente. | Cardinalidad estricta y rechazo explícito. | [HTTP anterior](../evidence/verification/http_before.json), [auditoría HTTP](AUDITORIA_HTTP.md) |
| Media | HEAD, If-Range y unidades desconocidas no respetaban la semántica esperada. | La reproducción y descarga parcial podían responder incorrectamente. | Rangos solo para GET, condiciones conservadoras y unidades desconocidas ignoradas. | [Pruebas HTTP](../tests/test_server.py) |
| Alta | Un JSON de casi 2 MiB creaba cientos de miles de objetos antes de ser rechazado. | El tamaño del texto se amplificaba en memoria antes de aplicar el contrato del grafo. | Límite de estructura antes de decodificar; conserva el máximo válido y el parser estricto. | [Medición anterior](../evidence/profiling/json_memory.json), [versión integrada](../evidence/verification/json_guard.json) |
| Alta | La UI rechazaba etiquetas vacías, recortaba espacios y podía partir un emoji al abreviar. | Importar/exportar modificaba datos válidos o producía texto Unicode incompleto en el dibujo. | Se preserva la etiqueta, se cuenta por puntos de código y se abrevia sin separar pares sustitutos. | [Antes](../evidence/ui/label-contract/before.json), [después en API y Pyodide](../evidence/ui/label-contract/after.json) |
| Media | El límite de importación visual usaba 2 MB decimales mientras Python permitía 2 MiB. | Un archivo válido en el núcleo fallaba en la interfaz. | Mismo límite de 2097152 bytes; un byte más se rechaza conservando el grafo. | [Antes](../evidence/ui/polish-before.json), [después](../evidence/ui/polish-after.json) |
| Media | Elegir elementos con teclado no llevaba el foco al formulario y los metadatos invadían el dibujo. | Se dificultaba editar y leer grafos en escritorio y móvil. | Foco en el editor y espacio propio para los metadatos. | [Verificación de pulido](../evidence/ui/polish-after.json) |
| Alta | El empaquetador aceptaba una salida que apuntaba a un archivo fuente. | Podía reemplazar código por un ZIP. Se reprodujo en una carpeta de prueba aislada. | Rechazar salidas dentro de la fuente y destinos sin extensión `.zip` antes de escribir. | [Reproducción](../evidence/delivery/package_before.json), [regresiones](../evidence/delivery/package_after.json) |
| Media | Un nombre acentuado de ZIP fallaba al escribir su checksum como ASCII. | Dejaba una entrega incompleta aunque el ZIP ya existiera. | Archivos auxiliares UTF-8 y verificación previa al reemplazo de la entrega. | [Auditoría del paquete](AUDITORIA_ENTREGA.md) |
| Media | El verificador del video dependía de un plan temporal no incluido en la entrega. | La copia limpia no podía reproducir la verificación del MP4. | Usar el plan incluido en la evidencia cuando no se pasa uno explícito. | [Fallo anterior](../evidence/delivery/clean_snapshot_video_before.json), [verificación posterior](../evidence/delivery/clean_snapshot_video.json) |
| Media | En el video había consultas implícitas y una equivalencia demasiado amplia entre los dos algoritmos. | El espectador podía asociar un costo a otro destino o suponer que el oráculo reproduce la traza. | Origen/destino explícitos, dirección visible y comparación entre algoritmos limitada al costo. | [Auditoría audiovisual](AUDITORIA_VIDEO.md) |
| Media | Marcadores, subtítulos y focos podían tapar información o desincronizarse con la voz. | Una gráfica correcta podía resultar ilegible o señalar otro concepto. | Orden de dibujo corregido, subtítulos sin solapamiento y focos ligados a palabras reales. | [Plan previo](../evidence/video_audit/plan_before.json), [plan corregido](../evidence/video_audit/plan_final.json), [focos corregidos](../evidence/video_audit/focus_timing_after.json) |

El informe conserva resultados fallidos anteriores a las correcciones. No se transforman retrospectivamente en pruebas aprobadas.

El primer ensayo de duración se interrumpió para corregir los problemas de interfaz; su [registro parcial](../evidence/ui/soak-baseline/INTERRUPCION.md) explica el cierre controlado. No acredita los 75 minutos previstos. Los resultados de un nuevo ensayo deben identificarse por sus propios archivos y hashes.

El video, la copia limpia y las capturas acreditan las versiones que registran. Una modificación posterior de código, datos de rendimiento o captura del estudio requiere renovar las verificaciones afectadas antes de presentar esos artefactos como actuales. El resultado de una prueba del empaquetador tampoco sustituye la extracción y comprobación del ZIP final.

## Ajustes de documentación

Se contrastaron clases, firmas y relaciones con el código: `ValidationError` expone argumentos heredados y `str(error)`, no un atributo `message`; los valores inmutables pueden compartirse entre grafos, por lo que el diagrama usa agregación; y los enteros JSON pasan por `int` antes de convertirse al peso `Decimal`. Se explicaron constructores y valores iniciales, se separó el costo del solver de la frontera JSON y se aclaró que abortar una petición HTTP no detiene automáticamente un cálculo ya iniciado en el servidor.

La cota de Dijkstra incluye el orden de vecinos y la cola con entradas antiguas. Las pruebas de mutación detectaron los defectos seleccionados y distinguieron una modificación equivalente. [Argumento de corrección](ALGORITMO.md), [API](API.md), [arquitectura](ARQUITECTURA.md) y [auditoría de mutaciones](AUDITORIA_MUTACIONES.md) permiten revisar esas afirmaciones.

## Qué aporta más valor dentro del reto

1. **Un solo algoritmo Python.** El servidor local y la publicación web usan los mismos archivos, comparados por SHA-256; la web ejecuta Python en un worker.
2. **Decisiones visibles.** La animación reproduce los eventos realmente emitidos: asentar, considerar, mejorar y descartar entradas antiguas.
3. **Oráculo independiente.** Bellman-Ford con enteros en micro-unidades contrasta los costos de Dijkstra sin reutilizar sus decisiones.
4. **Edición reversible.** Deshacer, rehacer, importar y recuperar una copia permiten experimentar con los grafos.
5. **Defensa verificable.** Clases, argumento de corrección, casos adversos, mediciones y límites quedan junto al código.

## Lo que no justificaría una calificación perfecta

- Aprobar casos de prueba no demuestra ausencia de todos los defectos.
- Medir en una computadora no garantiza los mismos tiempos en otro equipo o navegador.
- El grafo es una abstracción de costos no negativos; no representa la dinámica ni la seguridad de un vehículo.
- El límite admitido por el algoritmo no implica que todos los grafos densos sean visualmente fáciles de leer.
- Una defensa académica exige poder explicar y modificar la implementación, además de mostrarla.

La valoración final debe basarse en los artefactos y comprobaciones de la versión entregada. No se asigna una nota oficial ni se afirma que un evaluador externo haya aprobado el trabajo.

## Fuentes del criterio técnico

- Documento suministrado: `Bootcamp SDV.pdf`, perfil Software, página 3.
- [Dijkstra, artículo original (CWI)](https://ir.cwi.nl/pub/9256/9256D.pdf).
- [Python: Decimal](https://docs.python.org/3/library/decimal.html).
- [Pyodide: ejecución en worker](https://pyodide.org/en/stable/usage/webworker.html).
- [RFC 9110: solicitudes por rango](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2).
