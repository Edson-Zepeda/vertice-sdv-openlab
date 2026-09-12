# Publicación y comprobación de entrega

El [estudio público](https://edson-zepeda.github.io/vertice-sdv-openlab/) y la [página del proyecto](https://edson-zepeda.github.io/vertice-sdv-openlab/proyecto.html) se sirven desde GitHub Pages. El [repositorio](https://github.com/Edson-Zepeda/vertice-sdv-openlab) contiene la implementación y sus evidencias.

## Primera publicación comprobada

La rama `main`, revisión `407cc98f4fded8b00daa7e16c50ebc52dc9b7a5e`, contiene el proyecto. Su subárbol `web/` se publicó como raíz de `gh-pages`, revisión `2e0bc6e746ea70bb389e5f06218a9b72ca6d7443`. No se modificó el editor para adaptarlo a otra ruta.

La [comprobación pública](../evidence/publication/public-initial/qa.json) usa un contexto Chrome nuevo, sin autenticación ni recursos simulados. Sus 31 controles verificaron cálculo Python real, exploración de pasos, tamaño móvil, paridad con 18 consultas nativas, 22 archivos idénticos a la entrega local y reproducción del video después de cambiar de capítulo. El servidor público respondió HTTP 206 con los bytes solicitados del MP4. No se observaron solicitudes de recursos a otros dominios ni errores JavaScript.

Los 29 controles del motor son parte de esa comprobación; no se suman como si fueran otros 29 ensayos públicos independientes. La prueba acredita la revisión y los archivos indicados. Una publicación posterior necesita comprobar los archivos que cambien.

## Estado de GitHub Actions

El despliegue de Pages [terminó correctamente](https://github.com/Edson-Zepeda/vertice-sdv-openlab/actions/runs/34667691988). El flujo de pruebas [34667669209](https://github.com/Edson-Zepeda/vertice-sdv-openlab/actions/runs/34667669209) no inició ninguno de sus cuatro trabajos: GitHub informó un bloqueo de facturación de la cuenta. Las [anotaciones originales](../evidence/publication/ci-initial.json) conservan el motivo.

Por tanto, **no se acredita CI aprobado ni una ejecución de pruebas en Linux**. Las ejecuciones locales en Windows con Python 3.10, 3.11, 3.12 y 3.14 se documentan por separado en [COMPATIBILIDAD.md](COMPATIBILIDAD.md). Resolver el estado de la cuenta y volver a ejecutar el flujo es una acción externa pendiente; no se cambiaron opciones de pago.

## Volver a publicar

Desde un clon con el proyecto completo guardado en un commit:

```sh
git push origin main
git subtree split --prefix=web -b entrega-web
git push origin entrega-web:gh-pages
```

Usa un nombre de rama local nuevo para cada publicación. Si Git detecta una divergencia, revisa las revisiones; no fuerces una actualización sin entenderla. Pages debe usar la raíz de `gh-pages`, como registra [la configuración consultada](../evidence/publication/pages-created.json).

`web/.nojekyll` conserva los archivos estáticos sin el procesamiento de Jekyll, según la [documentación de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site#static-site-generators). GitHub no ejecuta el servidor Python de este proyecto: el navegador carga el núcleo mediante Pyodide.

Los enlaces de descarga completa se habilitan en `web/data/release.json` al preparar una versión y se comprueban antes de publicar la página que los expone. El ZIP final debe generarse desde el mismo commit de la versión; su recibo conserva revisión, tamaño y SHA-256. Un paquete de revisión anterior no sustituye esa comprobación final.
