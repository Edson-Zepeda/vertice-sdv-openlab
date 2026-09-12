# Dijkstra: funcionamiento y argumento de corrección

VÉRTICE implementa el problema de ruta mínima con pesos no negativos. El antecedente es el problema 2 del artículo de E. W. Dijkstra de 1959: construir distancias mínimas en orden creciente hasta alcanzar el destino. El artículo distingue las distancias definitivas de las mejores conocidas y contempla costos dependientes de la dirección. La implementación y el argumento siguientes describen este código, con cola binaria, grafos desconectados y límites explícitos. [Artículo original, CWI, pp. 270–271](https://ir.cwi.nl/pub/9256/9256D.pdf); [registro editorial y DOI](https://doi.org/10.1007/BF01386390).

## Estado de una búsqueda

- `distances[v]`: menor costo descubierto para llegar a `v`; `None` representa ausencia de una ruta descubierta.
- `closed`: nodos cuya distancia ya es definitiva. `settled` conserva su orden de asentamiento.
- `predecessors[v] = (u, conexión)`: último paso de la mejor ruta descubierta hacia `v`.
- Cola mínima: pares `(distancia, id_nodo)`; puede conservar entradas antiguas que se descartan al extraerse.
- `trace`: operaciones efectivamente ejecutadas. No es una animación inventada después del resultado.

El inicio recibe distancia cero y entra en la cola. Cada iteración extrae el par mínimo, descarta entradas antiguas y asienta el nodo vigente. Si es el destino, termina. En otro caso recorre vecinos por ID, suma el peso y sustituye la distancia de un vecino no asentado únicamente cuando obtiene una mejora estricta. Cada mejora inserta un nuevo par en la cola.

```text
distancia[inicio] ← 0
cola ← [(0, inicio)]
mientras cola no esté vacía:
    costo, u ← extraer mínimo
    si u ya está asentado o costo no es su distancia actual: continuar
    asentar u
    si u es destino: terminar con ruta
    para cada vecino v, ordenado por ID:
        candidato ← costo + peso(u, v)
        si v no está asentado y candidato mejora distancia[v]:
            distancia[v] ← candidato
            predecesor[v] ← (u, conexión)
            insertar (candidato, v)
si destino no fue asentado: devolver ausencia de ruta
```

## Por qué la ruta es mínima

Este argumento se aplica a un `Graph` válido que no se modifica concurrentemente durante `solve`.

**1. Una distancia finita representa una ruta real.** Al inicio, la ruta vacía llega al origen con costo cero. Una relajación añade una conexión existente a una ruta conocida. Por inducción, todo valor finito corresponde al costo de una ruta del grafo; nunca es una estimación menor que el costo óptimo real.

**2. Asentar el mínimo es seguro.** Supóngase que los nodos ya asentados tienen su distancia óptima y que se extrae el nodo vigente `u` con menor costo `d[u]`. Si existiera una ruta más barata hacia `u`, considérese el primer nodo `y` de esa ruta que todavía no está asentado, precedido por uno asentado `x`. Al procesar `x` se habría descubierto para `y` un costo no mayor que el prefijo de esa ruta. Como los pesos restantes son no negativos, ese costo sería menor que `d[u]`. La cola contendría la entrada vigente de `y` y la habría extraído antes que `u`: contradicción. Por tanto, `d[u]` ya es óptimo. El origen inicia la inducción con costo cero.

**3. Las entradas antiguas no cambian la elección.** Cada mejora inserta la nueva distancia. Una entrada cuyo costo difiere de `distances[u]` ya fue reemplazada; extraerla no relaja conexiones. Descartarla conserva la entrada vigente. Un nodo asentado nunca se procesa otra vez. La cola implementa así la selección del mínimo vigente, aunque contenga duplicados.

**4. Los predecesores permiten reconstruir una ruta finita.** Solo un nodo asentado puede convertirse en predecesor de uno aún no asentado. Por eso la cadena de predecesores retrocede estrictamente en el orden de asentamiento y no forma ciclos. Al asentar el destino, invertir esa cadena devuelve conexiones reales cuyo costo coincide con la distancia óptima.

**5. Agotar la cola demuestra que no hay ruta.** Si existiera una ruta a un destino no asentado, al cruzar por primera vez desde un nodo alcanzado hacia otro pendiente se habría insertado una distancia en la cola. No podría agotarse sin procesar todos los nodos alcanzables. Por tanto, `no_path` es correcto cuando el destino nunca se asienta y ya no quedan entradas.

El caso inicio igual a destino devuelve la ruta de un nodo y costo cero. Los pesos cero y los bucles propios respetan el argumento; una igualdad no actualiza predecesores. Los negativos se rechazan porque invalidan el paso 2. Los ejemplos no constituyen una ejecución en un vehículo.

## Qué significa terminar antes

La búsqueda termina **cuando el destino se asienta**, no cuando aparece por primera vez en la cola. Su costo es definitivo; otras distancias pueden seguir siendo tentativas.

Ejemplo dirigido: `A→B=1`, `A→C=9`, `B→C=1`. Al buscar `A→B`, se asienta `B` y se detiene antes de recorrer sus conexiones. El resultado muestra `distances[C]="9"`, aunque la ruta mínima hacia `C` costaría 2. Por eso el consumidor debe consultar `settled` y no presentar toda la tabla como distancias óptimas. Este caso está comprobado en `tests/test_core.py`.

`null` significa “aún no descubierto” durante una búsqueda detenida temprano. Solo al agotar la cola, un nodo no descubierto es inalcanzable desde el inicio.

## Exactitud decimal

La exactitud no se presupone por usar `Decimal`: también depende de la precisión y de la conversión de entrada. Python documenta que el contexto gobierna las operaciones y que `Decimal(float)` conserva el valor binario recibido, no necesariamente el decimal que escribió una persona. [Python: Decimal y contexto](https://docs.python.org/3.11/library/decimal.html).

Aquí los pesos tienen un máximo de seis decimales y valor `10^12`; no se redondean entradas fuera de esos límites. Una cadena de predecesores usa como máximo 499 conexiones. Incluso una distancia candidata que añade una conexión más tiene costo máximo `500 × 10^12 = 5 × 10^14`: 15 cifras enteras y seis fraccionarias, como máximo 21 cifras significativas. El contexto de 40 cifras representa exactamente esas sumas.

`_decimal_context()` fija precisión, redondeo, exponentes, indicadores y trampas. Así no hereda cambios en `getcontext()` ni en `DefaultContext`. Se verifican ambos casos. Los enteros JSON se leen como `int`; los tokens con fracción o exponente se construyen directamente desde su texto con `Decimal`. Al crear la conexión, ambos se convierten en un peso `Decimal` válido. Para intercambiar grafos se recomienda el peso como cadena. Si una aplicación ya convirtió un número a `float` antes de llamar a la API, no se pueden recuperar sus cifras perdidas.

La representación de salida elimina exponentes y ceros fraccionarios sobrantes. Los límites de 100 caracteres por número y 2 MiB por JSON evitan procesar representaciones arbitrariamente extensas. Los exponentes inválidos generan `ValidationError`.

Antes de decodificar también se limita la cantidad de estructura JSON fuera de cadenas; este control reduce la creación de objetos en entradas inválidas. Su costo de escaneo es lineal en la longitud del texto y no forma parte del bucle de Dijkstra. No fija un techo absoluto de RAM. [Límites y mediciones de importación](PERFILADO_IMPORTACION.md).

## Complejidad de esta implementación

Sea `V` el número de nodos, `E` el de conexiones almacenadas, `A` el número de referencias de adyacencia y `R` las mejoras aplicadas. En dirigido, `A=E`. En no dirigido, `A≤2E`, porque cada bucle propio aparece una vez. El costo de operaciones decimales y comparación de ID es acotado por los límites del proyecto.

| Parte | Tiempo | Memoria adicional |
|---|---|---|
| Inicializar distancias en orden de ID | `O(V log V)` | `O(V)` |
| Ordenar vecinos al procesar cada nodo | `O(Σ d(u) log(1+d(u))) ⊆ O(A log(1+V))` | Hasta `O(V)` temporal |
| Examinar conexiones | `O(A)` | Constante por examen |
| Cola con reemplazo diferido | `O((R+1) log(R+2))`, con `R≤A` | `O(R+1)` |
| Predecesores y reconstrucción | `O(V+R)` | `O(V)` |
| Trazas, cuando se solicitan | `O(V+A+R)` | `O(V+A+R)` |

En conjunto, la cota es `O(V log(1+V) + A log(1+V) + (A+1) log(A+2))`, equivalente a `O((V+E) log(V+E+1))` para este grafo. La memoria total es `O(V+E)`, incluidas adyacencia, cola con duplicados y trazas. Al quitar los límites de longitud numérica, también habría que contabilizar el costo de la aritmética de precisión arbitraria.

No se atribuye `O(V)` a la cola: las entradas antiguas pueden elevarla a `O(E)`. Tampoco se omite el ordenamiento de vecinos. `trace=False` evita almacenar los eventos, pero mantiene distancias, predecesores y cola.

## Decisiones y límites

`heapq` aporta la estructura de cola mínima de la biblioteca estándar; las relajaciones, el asentamiento, los predecesores y las decisiones del algoritmo son código propio. Se insertan prioridades nuevas y se descartan las antiguas en lugar de implementar una operación de disminución de clave. Es simple y verificable, con el costo de guardar duplicados. La documentación oficial presenta el problema de actualizar prioridades y el patrón de invalidación diferida. [Python: cola de prioridad](https://docs.python.org/3.11/library/heapq.html#priority-queue-implementation-notes).

Los empates usan `(costo, id)` y vecinos por ID. Se obtiene el mismo resultado al reordenar nodos y conexiones de entrada. No se promete la ruta lexicográficamente mínima global ni enumerar todas las rutas mínimas.

El sistema es un laboratorio de grafos. No usa coordenadas como heurística, no aprende costos, no admite pesos negativos, no impone restricciones dinámicas de tráfico y no sustituye a un planificador de movimiento de un vehículo. Las pruebas independientes respaldan los casos ejecutados; no constituyen una demostración automática de todos los programas o entornos posibles.

Fuentes primarias consultadas el 12 de septiembre de 2026 UTC. Los ejemplos y cotas específicos anteriores se derivan del código entregado.
