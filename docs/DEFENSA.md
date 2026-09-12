# Explicar y demostrar VÉRTICE

Guía de ensayo, no transcripción de una presentación realizada. El documento del reto no fija una duración para el perfil Software; esta secuencia propone unos seis minutos y deja tiempo para preguntas.

## Demostración sugerida

| Tiempo orientativo | Mostrar | Explicar |
|---|---|---|
| 0:00–0:40 | Ejemplo «Un mejor desvío», inicio S, destino T | El problema consiste en encontrar el menor costo total en un grafo. La posición del dibujo no determina el peso. |
| 0:40–1:30 | Calcular: S → B → D → E → T, costo 11 | Dijkstra asienta la menor distancia pendiente. La ruta sale de las conexiones reales y de sus pesos. |
| 1:30–2:20 | Pasos: mejora de A de 4 a 3; descarte posterior de 4 | Considerar una conexión no significa que mejora la ruta. Una entrada antigua de la cola se ignora si ya no representa el mejor costo conocido. |
| 2:20–3:10 | Cambiar el costo de S–A de 4 a 1 y recalcular | La respuesta cambia a S → A → C → D → E → T, costo 10. Deshacer devuelve el problema anterior. Estos dos resultados se calcularon con el núcleo del proyecto. |
| 3:10–3:50 | Ejemplo «Sin conexión» y luego inicio igual a destino | Un destino inalcanzable devuelve «Sin ruta», no costo cero. Inicio igual a destino sí tiene costo cero y una ruta de un nodo. |
| 3:50–4:40 | Diagrama de clases del informe | Node y Edge representan elementos; Graph conserva relaciones válidas; DijkstraSolver ejecuta la búsqueda. La interfaz presenta sus eventos. |
| 4:40–5:30 | Pruebas y rendimiento en el informe | Bellman-Ford independiente contrasta costos; las trazas tienen comprobaciones propias. La medición del algoritmo excluye construir el grafo; JSON a JSON incluye esa preparación y la salida. |
| 5:30–6:00 | Código `vertice/dijkstra.py` | Señalar la cola, mejora estricta, predecesores, parada al asentar el destino y reconstrucción. Cerrar con lo que se comprobó y los límites del modelo. |

El video es un recurso de respaldo. La demostración editable permite contestar preguntas cambiando el problema en el momento.

## Preguntas que debes poder contestar

**¿Usar heapq significa que Dijkstra no está hecho desde cero?**

heapq proporciona las operaciones de una cola mínima. La implementación propia decide las distancias, el orden de búsqueda, las relajaciones, el manejo de entradas antiguas, los predecesores, la parada y la reconstrucción. No se llama a una función de caminos mínimos de una biblioteca.

**¿Por qué no acepta pesos negativos?**

La justificación para volver definitiva la menor distancia pendiente depende de que las conexiones restantes no reduzcan el costo. Un peso negativo rompe esa premisa; por eso la entrada se rechaza, en lugar de ofrecer un resultado sin la garantía de Dijkstra.

**¿Qué ocurre con un ciclo de peso cero?**

Solo se registra una mejora si el candidato es estrictamente menor. Volver con el mismo costo no actualiza el predecesor ni reinserta indefinidamente el nodo. Un nodo asentado tampoco se expande otra vez.

**¿Por qué Decimal y no float?**

El contrato admite costos con hasta seis decimales. Conservar el texto numérico y usar Decimal evita introducir redondeo binario al importar y sumar esos valores. No recupera cifras que otra aplicación ya haya perdido antes de exportar el JSON.

**¿Todas las distancias de la tabla son finales?**

Solo las de los nodos asentados. Se detiene al asentar el destino, por lo que otros valores pueden seguir siendo tentativos. La interfaz distingue ambos estados.

**¿La ruta mostrada es la única óptima?**

Puede haber empates. El orden por ID y las actualizaciones estrictas hacen reproducible la elección. No se promete que sea la menor secuencia lexicográfica entre todas las rutas óptimas.

**¿Por qué separar los objetos de la interfaz?**

El modelo valida sus reglas aunque se use desde terminal. La misma implementación Python también se ejecuta en el navegador; no hay dos algoritmos distintos que deban coincidir por casualidad.

**¿Qué demuestran las pruebas independientes?**

Que los costos observados coinciden con otro algoritmo para los casos ejecutados, y que las rutas y trazas cumplen los invariantes comprobados. No demuestran ausencia universal de defectos ni validación en un vehículo.

**¿Por qué añadir un límite estructural si el archivo ya admite solo 2 MiB?**

Un texto pequeño puede crear muchos objetos al decodificarse. Se reprodujo ese problema y se limita la estructura antes de decodificar, conservando los grafos válidos y el parser estricto. La mejora reduce una amplificación observada; no convierte el límite del archivo en una garantía de RAM.

**¿Qué cambiarías si se necesitaran costos negativos o rutas dinámicas?**

Primero cambiaría el contrato y el algoritmo adecuado al problema. No basta con retirar una validación. En este alcance, editar el grafo invalida el resultado y exige una nueva consulta.

## Ejercicio sin guion

Crea cuatro nodos A, B, C, D y estas conexiones dirigidas: A→B = 2, A→C = 7, B→C = 1, C→D = 3. Antes de calcular A→D, predice la ruta y el costo. Después elimina B→C y vuelve a predecir. El primer costo es 6; el segundo, 10. Invierte la consulta D→A y explica por qué no hay ruta.

Localiza en el código la condición que hace posible cada respuesta. El objetivo del ensayo es poder justificar y modificar el proyecto, además de mostrar sus entregables.
