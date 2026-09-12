# Verificación de la interfaz

La aplicación ejecuta el núcleo Python real. La interfaz JavaScript edita el grafo y reproduce sus eventos; no contiene un algoritmo alternativo de Dijkstra.

## Comprobaciones reproducibles

- `qa.json`: 54 comprobaciones aprobadas. Incluyen edición por formulario y arrastre, teclado, costos exactos, reproducción, historial, importación cruda validada por Python, recuperación de sesión, anuncio accesible del resultado y vistas de 320/390 px.
- `adversarial.json`: 22 comprobaciones aprobadas. Incluyen respuestas tardías, reintento, importación tardía, respuesta incompleta, UTF-8 inválido, tamaño máximo, recuperación de almacenamiento y ampliación equivalente al 200 %.
- `qa.json > accessibility`: axe-core 4.11.1, reglas WCAG 2 A/AA y 2.1 AA, sin violaciones detectadas en los paneles Editar, Ruta y Pasos. Un escaneo automático no reemplaza todas las pruebas humanas de accesibilidad.
- `polish-after.json`: 17 comprobaciones aprobadas; límite exacto de 2 MiB, conservación de etiquetas, rechazo de controles y Unicode inválido, foco del editor y franja del lienzo para metadatos. `polish-before.json` conserva los seis fallos reproducidos antes del ajuste.
- `label-contract/after.json`: 8 comprobaciones aprobadas sobre los motores local y Pyodide. Se conserva vacío, espacios, 80 emoji y texto HTML literal al importar, exportar y calcular costo 0.3; la abreviatura SVG no parte caracteres Unicode. `label-contract/before.json` conserva los seis fallos originales.
- `soak/report.json` y `soak/activity.jsonl`: ensayo prolongado de interacción; consultar `completed`, duración real y fallos antes de atribuirle un resultado.
- `soak-baseline`: ensayo previo interrumpido deliberadamente tras 25,83 minutos para aplicar los hallazgos nuevos; no se presenta como un ensayo completo. `soak-stop-check` verifica la nueva parada ordenada por archivo, con `completed=false`, `interrupted=true` y sin fallos.

Los retrasos de red, HTTP 500, respuesta JSON incompleta y cuota de almacenamiento son fallos inyectados explícitamente por las pruebas. Las respuestas exitosas se obtienen del servidor Python. Los archivos `exported-graph.json` y `quota-recovery-graph.json` son descargas reales del navegador durante esos ensayos.

## Hallazgos corregidos

1. La barra de pasos restauraba su valor anterior al pausar antes de leer la nueva posición. Ahora captura el valor solicitado antes de pausar; Home/End y arrastre actualizan la traza.
2. `JSON.parse` podía redondear pesos numéricos antes de validarlos. La importación envía texto UTF-8 íntegro a Python, que conserva decimales y rechaza claves duplicadas.
3. Comparar el máximo del costo con `Number` ocultaba fracciones superiores al límite. El formulario compara micro-unidades con `BigInt`.
4. Una tabla desplazable no tenía acceso de teclado. Su región ahora acepta foco y navegación de desplazamiento.
5. Mensajes de éxito o acciones de historial podían ocultar un fallo al guardar. El aviso permanece y el grafo puede exportarse desde memoria.
6. La validación del resultado del motor era demasiado superficial. Una respuesta incompleta ahora produce un error recuperable.
7. El grafo horizontal reducía demasiado los nodos en móvil. La vista móvil proyecta el mismo grafo en vertical sin alterar coordenadas, pesos o datos exportados.
8. La interfaz construía miles de controles de una lista cerrada. Ahora la lista se construye al abrirla y el grafo denso reduce etiquetas superpuestas; todos los elementos conservan sus nombres accesibles.
9. La importación limitaba el archivo a 2 000 000 bytes, mientras Python admitía 2 097 152. Ahora ambos usan 2 MiB y se prueban el límite exacto y un byte adicional.
10. La interfaz rechazaba etiquetas vacías y recortaba espacios válidos; además, el formulario contaba unidades UTF-16 y la abreviatura podía partir un emoji. Ahora conserva los datos y cuenta puntos Unicode, con el ID como alternativa visible para un nombre vacío.
11. Elegir un elemento desde la lista destruía el control que tenía foco. El foco pasa al campo de edición correspondiente.
12. El lienzo reservaba espacio insuficiente para sus metadatos en grafos grandes. El SVG ahora termina antes de la franja de estado, también en móvil.
13. El resultado se escribía en un aviso oculto. Una región accesible activa anuncia su costo sin añadir texto visible redundante.

## Alcance de las mediciones

En la ejecución registrada en `adversarial.json`, un grafo didáctico dirigido de 500 nodos y 4 000 conexiones se importó/renderizó en 762 ms. Calcular y mostrar la ruta de costo 499 tomó 1 544 ms. Son observaciones puntuales de este equipo, incluyen interacción y renderizado y no constituyen una garantía de rendimiento.

La prueba del 200 % usa un viewport CSS de 720 × 500 con escala de dispositivo 2 para representar el espacio de una pantalla de 1440 × 1000 ampliada al doble. No se presenta como una comprobación del zoom del sistema operativo.

El ensayo prolongado mide heap principal, DOM y listeners después de GC mediante CDP. Esos indicadores no miden directamente el heap del Web Worker ni demuestran la ausencia universal de fugas.

`dom-retention.json` contiene un experimento de control: tras el calentamiento, editar un formulario HTML nativo y editar nombres en VÉRTICE añadieron ambos un nodo CDP por ciclo; el número de elementos vivos y oyentes permaneció constante. Cincuenta cálculos y recorridos de la traza mantuvieron 1 203 nodos CDP. Al navegar a una página vacía, las tres series volvieron a cuatro nodos y cero oyentes. Estas observaciones separan retención del navegador durante edición de una acumulación atribuible al renderizado del grafo; no identifican por sí solas el origen de cada objeto retenido.

## Ejecución

Con el servidor local en `http://127.0.0.1:8770/`, ejecutar los scripts `scripts/verify_ui.cjs`, `scripts/verify_ui_adversarial.cjs`, `scripts/verify_ui_polish.cjs`, `scripts/probe_label_contract.cjs after` y `scripts/soak_ui.cjs` con Node.js y Playwright disponibles. El canal predeterminado es Chrome, siempre con un perfil aislado. `PLAYWRIGHT_CHANNEL`, `VERTICE_URL`, `SDV_SOAK_MINUTES` y `SDV_SOAK_EVIDENCE` permiten ajustar el entorno. El escaneo axe requiere `axe-core`; el script también reconoce la instalación de herramientas aislada en `tmp/ui-tools`.

Para detener un ensayo de forma ordenada, crear `stop.flag` dentro de su carpeta de evidencia con el motivo. Se conserva el registro y se cierra únicamente su navegador aislado. `SIGINT` y `SIGTERM` solicitan la misma salida. La parada no se marca como ensayo completado. Usar un nombre de evidencia nuevo para conservar ejecuciones anteriores.
