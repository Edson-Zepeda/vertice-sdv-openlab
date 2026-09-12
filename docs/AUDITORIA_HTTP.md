# Auditoría del servidor local

Se ejecutaron solicitudes HTTP reales contra un servidor efímero en `127.0.0.1`, con archivos sintéticos en una carpeta temporal. La auditoría no leyó archivos privados, no usó credenciales y no contactó servicios externos.

## Hallazgos iniciales

| ID | Prioridad | Solicitud reproducible | Antes | Después |
|---|---|---|---|---|
| HTTP-01 | P2 | Dos cabeceras Origin: una local y otra externa | Se usaba solo la primera; 200 | Se rechaza la ambigüedad; 403 |
| HTTP-02 | P2 | Dos Content-Type: application/json y text/plain | Se aceptaba el primero; 200 | Se exige un único tipo; 415 |
| HTTP-03 | P2 | HEAD del video con Range: bytes=0-15 | 206 con longitud parcial | 200, longitud completa y cuerpo vacío |
| HTTP-04 | P2 | GET con Range e If-Range que no coincide | Se devolvía una parte; 206 | Se devuelve la representación completa; 200 |
| HTTP-05 | P2 | Range: items=0-1, unidad desconocida | 416 | Se ignora la unidad no admitida; 200 |
| HTTP-06 | P2 | Iniciar otro LocalServer en el puerto del primero, en Windows | La revisión de interfaz detectó que SO_REUSEADDR permitía un segundo enlace | Socket exclusivo en Windows; el intento adicional falla sin afectar al primero |

La corrección de HEAD, unidades desconocidas e If-Range sigue las reglas de HTTP. Referencia primaria consultada: [RFC 9110, sección 14.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2) y [sección 13.1.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5). El servidor mantiene soporte de un solo intervalo de bytes; no pretende implementar multipart/byteranges.

## Resultado posterior

26 métodos aprobados y 127 solicitudes registradas por entorno, sin fallos, errores ni omisiones, en CPython 3.10.11, 3.11.9, 3.12.14 y 3.14.7. Son los mismos escenarios en cuatro intérpretes de un equipo Windows; no se ejecutó esta matriz en Linux ni en CI remoto.

La regresión final se ejecutó después de incorporar el control estructural del JSON y la llamada directa `solve_payload(load_json(text))` del servidor. `http.json` corresponde a CPython 3.11.9; `http_python310.json`, `http_python312.json` y `http_python314.json` contienen las otras versiones, con hashes actuales del servidor, núcleo y pruebas. `final_guard_matrix.json` comprueba la correspondencia de esas fuentes con las evidencias finales.

Se conservaron `http_before.json` y su registro antes de los primeros arreglos; los informes inmediatamente anteriores al control estructural quedaron como `http*_before_final_guard.json` y sus registros. La regresión de enlace exclusivo se añadió después del hallazgo independiente de la revisión de interfaz; no se atribuye su reproducción inicial al registro HTTP anterior.

La cobertura incluye Host faltante, incorrecto y duplicado; origen externo; rutas que intentan salir de web/; prohibición de listar directorios; MIME de Wasm, módulos JavaScript, subtítulos y video; HEAD; rangos abiertos, cerrados, sufijos, extremos y vacíos; longitud de cuerpo inválida, duplicada o excesiva; transferencia chunked; UTF-8 inválido; claves repetidas y JSON extremo.

Se comprobaron las 18 consultas compartidas tanto con traza como sin ella: el resultado HTTP coincide exactamente con la ejecución Python. `/api/validate` conserva `0.1` como texto exacto y rechaza `1000000000000.000001` y `1e-1000`; no se valida un número después de redondearlo en JavaScript.

Una carga cortada devolvió 400. Una conexión que dejó incompleto el cuerpo agotó el plazo y devolvió 408; mientras esperaba, otra solicitud a `/api/health` respondió 200. Esto comprueba una operación concurrente concreta, no una garantía general frente a ataques de saturación.

## Reproducir

```text
python scripts/verify_http.py
```

Los archivos de video y Wasm de esta suite son fixtures para el protocolo, no una prueba de reproducción del video final ni de ejecución de Pyodide. La experiencia real del navegador se verifica por separado. La ruta pública alojada externamente tampoco ejecuta este servidor local.
