# Compatibilidad y terminal

El núcleo y la terminal se probaron en cuatro versiones reales de CPython para Windows. No se dedujo compatibilidad únicamente a partir de la sintaxis.

| Entorno | Suite independiente | Terminal en copia limpia | HTTP local |
|---|---:|---:|---:|
| CPython 3.10.11, portátil oficial | 38/38 | 12/12 | 26/26 |
| CPython 3.11.9, instalado en el equipo | 38/38 | 12/12 | 26/26 |
| CPython 3.12.14, runtime disponible | 38/38 | 12/12 | 26/26 |
| CPython 3.14.7, portátil oficial | 38/38 | 12/12 | 26/26 |

Cada conjunto es el mismo en las versiones indicadas: no son más escenarios únicos. Las pruebas de terminal ejecutaron 27 comandos reales y dos comprobaciones del lanzador por entorno; las de HTTP registraron 127 solicitudes por entorno. El lanzador elige el Python disponible en el sistema; su salida registra que utilizó 3.11.9 en este equipo, incluso cuando la suite fue coordinada por otro intérprete. Todos los procesos se ejecutaron en el mismo equipo Windows; la tabla no acredita una ejecución en Linux ni en CI remoto.

## Copia limpia y conservación del trabajo

La suite copia las fuentes a una carpeta temporal con espacios y acentos, verifica SHA-256 y utiliza `python -S -m vertice.cli` para deshabilitar `site-packages`. Ejecuta crear, añadir, editar, borrar, validar y resolver; comprueba las rutas y costos resultantes y los códigos de salida. También verifica que un cambio inválido o la ausencia de `--overwrite` conserve el archivo anterior y no deje temporales.

El recorrido publicado en `docs/API.md` se ejecutó realmente. Un resultado sin ruta tiene código de salida 0, `path=[]` y `cost=null`. Los errores de entrada o de archivo tienen código 2 y no muestran un traceback. El texto UTF-8, las rutas con caracteres españoles y la salida JSON se verificaron en archivos y entrada estándar.

## Defecto encontrado antes del cierre

**CLI-01 · P1:** con la codificación heredada cp1252 de Windows, la entrada estándar decodificaba un JSON UTF-8 como texto local. Al editar desde `-`, la etiqueta `Café 🚗 你好` se guardaba como texto corrupto, sin marcar error. La evidencia `cli_before.json` conserva la reproducción: un fallo en diez métodos y 27 comandos.

La corrección lee los bytes de `sys.stdin.buffer`, aplica el límite de tamaño en bytes y decodifica explícitamente UTF-8. Las pruebas posteriores conservaron exactamente la etiqueta en las cuatro versiones, incluso forzando cp1252 en el proceso. El modo de texto para consumidores que proporcionen StringIO sigue disponible.

## Lanzador Windows

`Iniciar.cmd --check` comprueba las importaciones y sale sin abrir el navegador. `--port` se reenvía al servidor y `--no-open` permite arrancarlo sin abrir una pestaña. El doble clic mantiene la apertura normal. Si el puerto está ocupado, el lanzador devuelve el código 1 del servidor; no lo sustituye por el resultado de una pausa.

La revisión final del arranque y el puerto exclusivo forma parte de `cli_python*.json`. `launcher.json` extrae las dos comprobaciones de `cli_python311.json`, enlaza su hash y aclara que no representa otra ejecución. Las pruebas HTTP usan puertos efímeros y no interrumpen la instancia de la aplicación abierta por el usuario.

## Intérpretes temporales y evidencia

Los ZIP oficiales [Python 3.10.11](https://www.python.org/downloads/release/python-31011/) y [Python 3.14.7](https://www.python.org/downloads/release/python-3147/) se descargaron únicamente a `tmp/compatibility`, sin instalación, cambio de PATH ni registro. Se conservaron sus hashes y la comparación con las huellas publicadas en `portable_runtimes.json`. La configuración `_pth` se desactivó solo en esos intérpretes temporales para que `-m` cargara la copia limpia de trabajo; los procesos del producto mantuvieron `-S`.

3.10.11 es una versión binaria antigua utilizada exclusivamente para ensayar la serie mínima declarada; no es una recomendación de versión para instalar. Estos intérpretes no forman parte de la entrega. Para reproducir opcionalmente esa preparación: `python scripts/prepare_compatibility.py`.

Los resultados finales corresponden al control estructural de JSON integrado en el núcleo y a la llamada directa del servidor a ese núcleo. Se conservan como `independent*.json`, `cli_python*.json`, `http*.json` y sus registros. Las versiones anteriores están identificadas como `*_before_final_guard`; `final_guard_matrix.json` comprueba los hashes de los doce informes finales y sus fuentes.

La ejecución independiente de 38 métodos se reutilizó de la matriz real de `json_guard.json`, cuyo registro contiene cada método aprobado. `scripts/consolidate_regression.py` extrae esos resultados sin volver a ejecutar las pruebas; cada informe normalizado enlaza el registro y su hash. Los contadores de escenarios proceden de la instrumentación anterior de la misma suite determinista y del mismo algoritmo, ambos sin cambios: no se presentan como contadores capturados de nuevo por el recolector compartido.

Cada evidencia indica sus fuentes y ámbito. Las pruebas de CPython no sustituyen la verificación de Pyodide en el navegador, documentada por separado.
