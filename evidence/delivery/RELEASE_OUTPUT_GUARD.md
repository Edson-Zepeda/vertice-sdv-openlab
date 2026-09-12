# Protección del informe de verificación

Se reprodujo un defecto en `scripts/verify_release.py`: indicar el ZIP, su recibo o su checksum como `--output` reemplazaba ese archivo por el informe de una comprobación fallida. La reproducción usó exclusivamente archivos ficticios en una carpeta temporal externa al repositorio, con el acceso de red bloqueado. No se alteró ninguna entrega real.

La versión corregida resuelve las rutas, exige extensión `.json`, rechaza salidas dentro del directorio fuente y protege el ZIP y sus dos comprobantes antes de leer el paquete o contactar la red. También rechaza un archivo JSON que sea un enlace físico a un comprobante. La escritura utiliza la misma ruta resuelta que se validó.

## Evidencia

- Fuente anterior: `before/verify_release_output_guard.py.txt`.
- Reproducción: `release_output_guard_before.json`. Registra los hashes anteriores y posteriores de los tres archivos ficticios sobrescritos.
- Corrección: `release_output_guard_after.json`, `release_output_guard_python310.json` y `release_output_guard_python314.json`.
- Pruebas: `tests/test_release_output_guard.py`.

En Python 3.10.11, 3.11.9 y 3.14.7 se aprobaron los cuatro métodos ejecutables, con doce escenarios por intérprete, cero lecturas de contenido en los casos que deben rechazarse y cero llamadas de red. El quinto método, que necesita crear un enlace simbólico real, quedó omitido porque Windows no concede ese privilegio; no se presenta como aprobado. El enlace físico sí se creó y comprobó. Una salida JSON independiente pudo registrar correctamente una falla local y conservó intactos todos los archivos de entrada.

Estos controles verifican la protección del argumento de salida. No acreditan una publicación final ni repiten los 37 controles de la extracción del commit `407cc98`.
