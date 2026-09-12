# Evaluación final frente al reto SDV

**Los requisitos del perfil Software tienen implementación, documentación y evidencia ejecutada.** La referencia es `Bootcamp SDV.pdf`, página 3. La GUI es opcional; no se inventa una rúbrica numérica ni una nota oficial.

| Requisito | Entrega | Evidencia |
|---|---|---|
| Dijkstra desde cero en Python o C++ | [Implementación propia en Python](../vertice/dijkstra.py) | [Comparación independiente con Bellman–Ford](../evidence/verification/independent.json), [mutaciones](AUDITORIA_MUTACIONES.md) |
| Orientación a objetos: nodos, conexiones y grafo | [Node, Edge, Graph](../vertice/graph.py) y DijkstraSolver | [Pruebas del núcleo](../tests/test_core.py) |
| Crear y modificar el grafo; elegir extremos y solicitar ruta | [Editor gráfico](../web/index.html), [terminal](../vertice/cli.py) | [54 controles de interfaz](../evidence/ui/qa.json), [22 adversos](../evidence/ui/adversarial.json) |
| Documentar clases, atributos, métodos y responsabilidades | [API](API.md), [arquitectura](ARQUITECTURA.md), docstrings | [Consistencia con código](../evidence/documentation/consistency.json) |
| Representar la estructura y sus relaciones | Diagramas de clases y adyacencia en arquitectura e informe | [Informe](VerticeSDV_Informe.pdf), [revisión visual](../evidence/report/qa.json) |
| Distintos grafos y extremos, incluyendo ausencia de ruta | [Seis ejemplos](../examples/), casos dirigidos, empates y componentes separadas | [Suite independiente](../tests/test_independent.py), `no_path` distinto de inicio=destino |
| Explicar decisiones y funcionamiento | [Algoritmo y corrección](ALGORITMO.md), [guía de defensa](DEFENSA.md), traza interactiva | Relajación, asentamiento, desempates, aritmética decimal y complejidad documentados |

## Qué impidió considerar impecable la primera versión

La [auditoría crítica](AUDITORIA.md) conserva defectos reales y sus correcciones: pérdida de precisión al importar, validación de JSON costosa, cancelación compartida, etiquetas alteradas, fuentes externas, fallos en rangos de video y protección del empaquetado. El ensayo prolongado encontró además que los nodos ampliados podían cubrir el zoom. El recorte del SVG pasó [192 comprobaciones en seis escenarios](../evidence/ui/zoom-viewport/after.json); se conservan los [seis escenarios fallidos anteriores](../evidence/ui/zoom-viewport/before.json).

La mejora visual aporta lectura, navegación por teclado, historial, recuperación de sesión y reproducción de decisiones. Las gráficas del video proceden de ejecuciones y mediciones guardadas. Estos extras ayudan a entender y verificar el algoritmo dentro del perfil solicitado.

## Resultado comprobado

- **Batería Python conjunta:** [123 pruebas en la batería](../evidence/verification/combined.json): 122 aprobadas y una omitida por el permiso de Windows para crear enlaces simbólicos. La [matriz de compatibilidad](COMPATIBILIDAD.md) identifica las ejecuciones por intérprete; no suma repeticiones como casos diferentes.
- **Estabilidad:** [cinco bloques completos](../evidence/ui/soak-complete/closure.json), 12,16 minutos, 408 acciones, 54 ciclos y 67 cálculos, sin fallos y con los archivos del programa sin cambios. Los intentos largos interrumpidos y el intento fallido se conservan por separado. No se atribuyen 45 minutos continuos a esta ejecución de doce minutos.
- **Informe y video:** [diez páginas revisadas](../evidence/report/qa.json) y [20 comprobaciones técnicas del MP4](../evidence/video_audit/verification.json). El video está narrado en español y permite navegar por capítulos.
- **Primera publicación:** [31 controles sin autenticación](../evidence/publication/public-initial/qa.json), motor Python real, 22 archivos contrastados y reproducción con descarga parcial.

## Entrega de la versión

El [README](../README.md) reúne código, ejemplos, instrucciones, documentación e informe. La página [Proyecto](https://edson-zepeda.github.io/vertice-sdv-openlab/proyecto.html) reúne estudio, video, informe, código y paquete. Los comprobantes del ZIP real, su extracción y su descarga se adjuntan a la [versión 1.0.0](https://github.com/Edson-Zepeda/vertice-sdv-openlab/releases/tag/v1.0.0), separados del paquete para conservar limpia la revisión que este identifica. [Procedimiento y alcance](AUDITORIA_ENTREGA.md).

## Límites que siguen siendo reales

GitHub no inició CI por un bloqueo de facturación de la cuenta; el [despliegue y las pruebas locales](PUBLICACION.md) tienen evidencia separada. Las pruebas no garantizan ausencia universal de defectos ni rendimiento en cualquier equipo. Los grafos y costos son didácticos; no representan conducción ni validación vehicular. La guía de defensa prepara una exposición, pero no acredita que ya se haya realizado. La evaluación oficial corresponde al equipo del reto.
