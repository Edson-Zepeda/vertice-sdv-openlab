# Contrato compartido de implementación

Estado inicial del contrato: 12 de septiembre de 2026, 00:55 UTC.

## Archivos y propiedad

- Núcleo: `vertice/graph.py`, `vertice/dijkstra.py`, `vertice/codec.py`, `vertice/__init__.py`, `vertice/cli.py`; agente de núcleo.
- Web: `web/index.html`, `web/app.js`, `web/style.css`, módulos de edición/visualización; agente de interfaz.
- Motor del navegador, servidor, configuración, ejemplos, documentos, video y entrega: coordinador.
- Pruebas independientes, auditoría algorítmica y benchmarks: agente verificador, sin cambiar el núcleo.

## Grafo JSON

Objeto `{schema_version:1, directed:false, nodes:[{id:"A",label:"Inicio",x:120,y:180}], edges:[{id:"e1",source:"A",target:"B",weight:"1.25"}]}`. IDs de 1 a 40 caracteres ASCII alfanuméricos, guion o guion bajo; etiquetas hasta 80 caracteres Unicode. Coordenadas finitas en [-10000,10000]. Hasta 500 nodos y 4000 conexiones. Sin conexiones paralelas: una por par ordenado en dirigido; una por par no ordenado en no dirigido. Los bucles propios se permiten y se explican. Pesos en [0,10^12], hasta seis decimales; salida canónica como texto decimal. Los ejemplos son grafos didácticos, no mapas de calles medidas.

## Búsqueda

Entrada `{graph:<grafo>, source:"A", target:"F", trace:true}`. `vertice.codec.solve_json(text:str)->str` recibe exclusivamente JSON y retorna JSON serializable, sin NaN/Infinity. `solve_payload(payload:dict)->dict` expone lo mismo para servidor y pruebas. Errores de validación producen `ValidationError` con mensaje en español; no evalúa código del usuario.

Resultado `{status:"ok"|"no_path", source, target, path:[ids], edge_path:[ids], cost:<texto|null>, distances:{id:<texto|null>}, settled:[ids], trace:[eventos], stats:{settled,relaxations,heap_pushes,heap_pops,stale_pops}}`. Distancias no asentadas son tentativas. `no_path` tiene ruta vacía y costo null. El empate se resuelve de forma reproducible recorriendo vecinos ordenados por ID y una cola `(coste,id)`; no se promete ruta lexicográficamente mínima global. Parada al asentar el destino.

Cada evento tiene `step` consecutivo desde 0, `kind` en `initialize`, `settle`, `consider`, `relax`, `stale`, `finish`; campos adicionales cuando aplican: `node`, `source`, `target`, `edge`, `old_cost`, `new_cost`, `cost`, `status`. No incluye copias completas de la cola en cada evento. El nodo asentado se retira de la frontera visible; `relax` actualiza su costo conocido. `finish` incluye estado. Trazas acotadas por tamaño del grafo. Sin tiempos variables dentro del resultado determinista.

## Interfaz del motor para la web

El coordinador entrega `web/engine.js` que exporta `solveGraph(payload, {signal}={}) -> Promise<resultado>` e `engineStatus() -> {mode,state,label}` y emite eventos `vertice-engine` con el estado. Modo local usa API Python; modo publicado usa el mismo paquete Python con Pyodide en Web Worker. El adaptador no implementa Dijkstra en JavaScript. El worker incluye identificador de solicitud; la UI invalida una respuesta si el grafo cambió. El front puede importar desde el inicio este contrato, sin esperar al motor real.

Coordinador sirve `GET /api/health`, `POST /api/solve` y estáticos en localhost:8770. No se intenta descubrir una API local desde un dominio público. Los ejemplos se entregan en `web/data/examples.json` como array `[{id,name,description,graph,source,target}]`. La UI puede proponer su ejemplo inicial y coordinarlo.
