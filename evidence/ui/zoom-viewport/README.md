# Corrección de controles al ampliar

Un nodo ampliado podía salir del SVG y bloquear los controles del editor. La causa era `overflow: visible` en `#graph`. Se cambió a `overflow: hidden` para recortar dibujo y área de interacción al viewport del grafo.

La prueba reproduce seis fallos con el estilo original y verifica después 192 comprobaciones sin fallos en seis escenarios: 390, 768 y 1440 píxeles; 90 y 150 nodos; 270 y 450 conexiones. Cada escenario importa y resuelve con Python real en el navegador, recorre la traza y pulsa zoom, herramientas y centrado con clicks ordinarios. También cambia de escritorio a móvil y repite la secuencia que falló. No se usa `force`, despacho sintético de eventos ni sustitución de resultados del motor.

`before.json` conserva los fallos; `after.json` registra la ejecución corregida. `audit.json` contiene hashes, capturas revisadas y una interrupción intermedia del verificador anterior a la aplicación del cambio. La prueba sostenida se registra por separado.

Reproducir con el servidor local activo y Playwright disponible:

```text
node scripts/verify_zoom_viewport.cjs
```
