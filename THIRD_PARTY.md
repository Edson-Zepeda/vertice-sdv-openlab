# Componentes y procedencia

El código propio de VÉRTICE se distribuye bajo la licencia MIT de este repositorio. Los componentes siguientes conservan sus licencias originales.

| Componente | Versión o revisión | Licencia y fuente |
|---|---|---|
| Pyodide, sin modificaciones | 314.0.6 | MPL 2.0, `web/vendor/pyodide/LICENSE`; [fuente correspondiente](https://github.com/pyodide/pyodide/tree/314.0.6) |
| CPython incluido por Pyodide | 3.14.2 | `web/vendor/pyodide/CPYTHON-LICENSE`; [fuente correspondiente](https://github.com/python/cpython/tree/v3.14.2) |
| Manrope | Google Fonts `809e4d8b8d7e9364a914909bb777679606c178b8` | SIL Open Font License 1.1, `web/fonts/Manrope-OFL.txt` |
| DM Sans | Misma revisión de Google Fonts | SIL Open Font License 1.1, `web/fonts/DMSans-OFL.txt` |

`evidence/dependencies/` conserva URLs exactas, tamaños y SHA-256 de los componentes descargados. Los scripts de obtención fijan versión o revisión. Las fuentes de la web permanecen sin modificar; las instancias estáticas usadas al construir documentos conservan sus avisos.

El reto original se consultó desde el PDF suministrado por el usuario; no se redistribuye ese documento dentro de la aplicación. Se identifica por título, página y hash en `project.json`.

La narración del video es voz generada a partir del guion del proyecto. Las gráficas del video se componen con resultados de Python y mediciones conservadas; la captura del estudio proviene de la aplicación ejecutada. No se presenta ninguna escena como una prueba física de conducción.
