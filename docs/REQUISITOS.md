# VÉRTICE / SDV - requisitos y criterios de aceptación

Fuente: Bootcamp SDV.pdf, página 3, SHA-256 af12c207356864b7718b448fee1d279579fbc4813270ea627f85896a3b6b63df.

Se implementa únicamente el área Software: Dijkstra con programación orientada a objetos en Python. Los perfiles Visión y Electrónica/STM32 son áreas separadas del documento. No se atribuye este trabajo a ejecución en un vehículo.

| Requisito del documento | Entrega verificable |
|---|---|
| Dijkstra desde cero en Python o C++ | Python propio, sin NetworkX/SciPy en el algoritmo entregado |
| Objetos para nodos, conexiones y grafo | Node, Edge, Graph con invariantes explícitos; DijkstraSolver separado |
| Crear/modificar el grafo y elegir inicio/destino | Editor visual, edición mediante formularios y terminal; importación/exportación |
| Ruta de costo mínimo | Resultado con nodos, conexiones y costo exacto; verificación independiente |
| Manejar ausencia de ruta | Estado específico, sin ruta falsa ni costo cero |
| Documentar clases y responsabilidades | API explicada, diagrama de clases y estructura de adyacencia |
| Pruebas con distintos grafos y extremos | Casos límite, oráculo independiente y ejecuciones reproducibles |
| Explicar decisiones y funcionamiento | Informe, trazas reales del algoritmo y demostración narrada |

## Criterios propios de calidad

- El mismo código Python produce el resultado en terminal, servidor local y navegador; no se presenta una reimplementación JavaScript como Python.
- Pesos no negativos y finitos. Decimales de hasta seis posiciones; rechazo explícito de negativos, NaN, infinitos, entradas ambiguas y archivos fuera de límites.
- Grafo dirigido o no dirigido, costos cero, ciclos, empates, aislamiento e inicio igual a destino documentados.
- Las trazas provienen de relajaciones reales. Las distancias tentativas se distinguen de las definitivas.
- Navegación por teclado, edición sin arrastrar, móvil, reducción de movimiento, historial de deshacer/rehacer y persistencia recuperable.
- Documentos y video basados en la versión probada. Paquete verificable y arranque sin instalar bibliotecas para usar el núcleo local.
- Ninguna cifra de precisión o rendimiento se inventa. Se publican entorno, casos, semillas y limitaciones de los resultados.

## Riesgos que debe atacar la auditoría

Costos decimales mal redondeados; estados visuales desactualizados tras editar; ruta no válida al borrar un nodo; respuestas tardías del motor aplicadas al grafo equivocado; grafos dañados al importar; bloqueo de interfaz durante la búsqueda; depender de Internet sin indicarlo; desfase entre Python local y navegador; completar el proyecto antes del tiempo solicitado.
